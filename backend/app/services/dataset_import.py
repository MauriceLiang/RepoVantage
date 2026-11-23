"""校验并导入内置的脱敏精选数据包。"""

import gzip
import hashlib
import json
import logging
import re
import stat
import tempfile
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

from sqlalchemy import delete, desc, func, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.clock import iso_z, parse_github_datetime, utc_now
from backend.app.core.config import PROJECT_ROOT
from backend.app.core.exceptions import AppError
from backend.app.persistence.db import begin_immediate
from backend.app.persistence.models import (
    ActivityWindow,
    AnalysisResult,
    Dataset,
    DatasetImportJob,
    DatasetImportStagingRecord,
    DatasetRepository,
    ApplicationSetting,
    Repository,
    RepositoryActivityEvent,
    RepositoryInsightRun,
    RepositorySnapshot,
)
from backend.app.services.repositories import FEATURED_ID, LIBRARY_ID, repository_from_github


logger = logging.getLogger("repovantage.dataset_import")
from backend.app.services.dataset_import_common import (
    ALLOWED_FILES,
    BUNDLE_MAX_BYTES,
    BUNDLE_ROOT,
    CREDENTIAL_PATTERN,
    DATA_FILES,
    EMAIL_PATTERN,
    FEATURED_LIBRARY_SEEDED_KEY,
    HASH_LINE,
    MACHINE_PATH_PATTERN,
    MAX_RECORDS,
    MODULES,
    REQUIRED_FILES,
    SCHEMA_FILES,
    UNCOMPRESSED_MAX_BYTES,
    BundleError,
    _contains_sensitive_data,
    _json_object,
    _nonnegative_int,
    _positive_int,
)

@contextmanager
def _bundle_directory(source: Path) -> Iterator[Path]:
    source = source.expanduser().resolve()
    if source.is_dir():
        yield source
        return
    if not source.is_file() or not zipfile.is_zipfile(source):
        raise BundleError("数据包目录或 ZIP 不存在或格式无效")
    if source.stat().st_size > BUNDLE_MAX_BYTES:
        raise BundleError("精选数据包超过 256 MiB 限制")
    with tempfile.TemporaryDirectory(prefix="repovantage-bundle-") as temporary:
        root = Path(temporary)
        total_size = 0
        count = 0
        seen_names = set()
        try:
            with zipfile.ZipFile(source) as archive:
                for item in archive.infolist():
                    name = item.filename
                    path_name = name[:-1] if item.is_dir() and name.endswith("/") else name
                    parts = path_name.split("/")
                    if not path_name or name.startswith("/") or any(part in {"", ".", ".."} for part in parts) or "\\" in name or "\x00" in name or ":" in name:
                        raise BundleError("ZIP 包含不安全的文件路径")
                    if name in seen_names:
                        raise BundleError("ZIP 包含重复的文件路径")
                    seen_names.add(name)
                    mode = item.external_attr >> 16
                    file_type = stat.S_IFMT(mode)
                    if item.is_dir():
                        if file_type not in {0, stat.S_IFDIR}:
                            raise BundleError("ZIP 包含不允许的文件类型")
                        continue
                    count += 1
                    if count > 10_000:
                        raise BundleError("ZIP 文件数量超过限制")
                    if file_type not in {0, stat.S_IFREG}:
                        raise BundleError("ZIP 只允许包含普通文件")
                    total_size += item.file_size
                    if total_size > UNCOMPRESSED_MAX_BYTES or item.file_size > UNCOMPRESSED_MAX_BYTES:
                        raise BundleError("ZIP 解压大小超过限制")
                    target = root.joinpath(*parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    copied = 0
                    with archive.open(item) as src, target.open("wb") as dst:
                        while chunk := src.read(1024 * 1024):
                            copied += len(chunk)
                            if copied > item.file_size or copied > UNCOMPRESSED_MAX_BYTES:
                                raise BundleError("ZIP 实际解压大小超过声明或限制")
                            dst.write(chunk)
                    if copied != item.file_size:
                        raise BundleError("ZIP 文件实际大小与目录声明不一致")
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            raise BundleError("ZIP 数据包无法安全读取") from exc
        yield root


def verify_dataset_bundle(source: Path) -> dict[str, Any]:
    with _bundle_directory(source) as root:
        metadata, records, bundle_hash = _load_bundle(root)
        return {
            "available": True,
            "dataset_id": metadata["dataset_id"],
            "version": metadata["version"],
            "total_repositories": metadata["total_repositories"],
            "data_as_of": metadata["data_as_of"],
            "bundle_hash": bundle_hash,
            "record_counts": {name: len(rows) for name, rows in records.items()},
        }


def featured_status(session: Session) -> dict[str, Any]:
    imported = _featured_imported_repository_count(session)
    status: dict[str, Any] = {
        "available": False,
        "dataset_id": FEATURED_ID,
        "version": None,
        "total_repositories": 0,
        "imported_repositories": imported,
        "data_as_of": None,
        "bundle_hash": None,
        "reason": None,
        "already_current": False,
        "imported_version": None,
        "imported_bundle_hash": None,
        "imported_at": None,
        "verification_status": "unknown",
        "last_verification": None,
        "active_task": None,
        "latest_task": None,
    }
    try:
        manifest, bundle_hash, signature = _lightweight_bundle_info(BUNDLE_ROOT)
    except (BundleError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        status["reason"] = str(exc)
    else:
        status.update({
            "available": True,
            "dataset_id": manifest["dataset_id"],
            "version": manifest["version"],
            "total_repositories": manifest["total_repositories"],
            "data_as_of": manifest["data_as_of"],
            "bundle_hash": bundle_hash,
        })
        verification = session.get(ApplicationSetting, "featured_bundle_verification")
        cached = _json_object(verification.setting_value) if verification else {}
        if cached.get("signature") == signature and cached.get("bundle_hash") == bundle_hash:
            status["verification_status"] = "verified"
            status["last_verification"] = cached
        else:
            status["verification_status"] = "pending"
            status["last_verification"] = cached or None

    dataset = session.get(Dataset, FEATURED_ID)
    imported_meta = _json_object(dataset.source_metadata_json) if dataset else {}
    status["imported_version"] = imported_meta.get("version")
    status["imported_bundle_hash"] = imported_meta.get("bundle_hash")
    status["imported_at"] = imported_meta.get("imported_at")
    status["already_current"] = bool(
        status["available"]
        and _featured_bundle_is_current(imported_meta, status["bundle_hash"], imported, status["total_repositories"])
    )
    status["imported_repositories"] = imported
    active_job = session.scalar(
        select(DatasetImportJob)
        .where(DatasetImportJob.dataset_id == FEATURED_ID, DatasetImportJob.status.in_(("queued", "running")))
        .order_by(desc(DatasetImportJob.created_at))
        .limit(1)
    )
    latest_job = active_job or session.scalar(select(DatasetImportJob).order_by(desc(DatasetImportJob.created_at)).limit(1))
    status["active_task"] = _dataset_job_summary(active_job) if active_job else None
    status["latest_task"] = _dataset_job_summary(latest_job) if latest_job else None
    return status


def _featured_imported_repository_count(session: Session) -> int:
    return int(session.scalar(
        select(func.count(func.distinct(DatasetRepository.repository_id)))
        .join(RepositorySnapshot, RepositorySnapshot.repository_id == DatasetRepository.repository_id)
        .where(DatasetRepository.dataset_id == FEATURED_ID, RepositorySnapshot.valid.is_(True))
    ) or 0)


def _featured_bundle_is_current(
    imported_meta: dict[str, Any],
    bundle_hash: str | None,
    imported_repositories: int,
    total_repositories: int,
) -> bool:
    return (
        imported_meta.get("bundle_hash") == bundle_hash
        and imported_meta.get("complete", True) is not False
        and imported_repositories >= total_repositories
    )


def invalidate_featured_import_for_repositories(session: Session, repository_ids: list[int]) -> set[int]:
    featured_ids = set(session.scalars(
        select(DatasetRepository.repository_id).where(
            DatasetRepository.dataset_id == FEATURED_ID,
            DatasetRepository.repository_id.in_(repository_ids),
        )
    ).all())
    if not featured_ids:
        return set()

    session.execute(
        delete(DatasetRepository).where(
            DatasetRepository.dataset_id == FEATURED_ID,
            DatasetRepository.repository_id.in_(featured_ids),
        )
    )
    dataset = session.get(Dataset, FEATURED_ID)
    if dataset:
        imported_meta = _json_object(dataset.source_metadata_json)
        if imported_meta:
            imported_meta["complete"] = False
            dataset.source_metadata_json = json.dumps(imported_meta, ensure_ascii=False)
    return featured_ids


def queue_featured_import(session: Session, idempotency_key: str | None = None) -> dict[str, Any]:
    if idempotency_key:
        previous = session.scalar(select(DatasetImportJob).where(DatasetImportJob.idempotency_key == idempotency_key))
        if previous:
            return _queue_response(previous)
    status = featured_status(session)
    if not status["available"]:
        raise AppError(409, "DATASET_BUNDLE_UNAVAILABLE", status["reason"] or "精选数据包不可用")
    if status["already_current"]:
        return {
            "task_id": None,
            "dataset_id": FEATURED_ID,
            "version": status["version"],
            "bundle_hash": status["bundle_hash"],
            "status": "succeeded",
            "already_current": True,
        }

    begin_immediate(session)
    if idempotency_key:
        existing_by_key = session.scalar(select(DatasetImportJob).where(DatasetImportJob.idempotency_key == idempotency_key))
        if existing_by_key:
            session.commit()
            return _queue_response(existing_by_key)
    dataset = session.get(Dataset, FEATURED_ID)
    imported_meta = _json_object(dataset.source_metadata_json) if dataset else {}
    if _featured_bundle_is_current(
        imported_meta,
        status["bundle_hash"],
        _featured_imported_repository_count(session),
        status["total_repositories"],
    ):
        session.commit()
        return {
            "task_id": None,
            "dataset_id": FEATURED_ID,
            "version": status["version"],
            "bundle_hash": status["bundle_hash"],
            "status": "succeeded",
            "already_current": True,
        }
    active = session.scalar(
        select(DatasetImportJob)
        .where(
            DatasetImportJob.dataset_id == FEATURED_ID,
            DatasetImportJob.bundle_hash == status["bundle_hash"],
            DatasetImportJob.status.in_(("queued", "running")),
        )
        .limit(1)
    )
    if active:
        session.commit()
        return _queue_response(active)

    job = DatasetImportJob(
        task_id=str(uuid.uuid4()),
        dataset_id=FEATURED_ID,
        bundle_version=str(status["version"]),
        bundle_hash=str(status["bundle_hash"]),
        status="queued",
        phase="validating",
        progress_kind="indeterminate",
        message="等待导入 Worker",
        idempotency_key=idempotency_key,
        staging_state_json="{}",
    )
    session.add(job)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        active = session.scalar(
            select(DatasetImportJob)
            .where(
                DatasetImportJob.dataset_id == FEATURED_ID,
                DatasetImportJob.bundle_hash == status["bundle_hash"],
                DatasetImportJob.status.in_(("queued", "running")),
            )
            .limit(1)
        )
        if active:
            return _queue_response(active)
        raise
    return _queue_response(job)


def _queue_response(job: DatasetImportJob) -> dict[str, Any]:
    return {
        "task_id": job.task_id,
        "dataset_id": job.dataset_id,
        "version": job.bundle_version,
        "bundle_hash": job.bundle_hash,
        "status": job.status,
        "already_current": False,
    }


def _dataset_job_summary(job: DatasetImportJob | None) -> dict[str, Any] | None:
    if job is None:
        return None
    return {
        "task_id": job.task_id,
        "status": job.status,
        "phase": job.phase,
        "progress_percent": job.progress_percent,
        "progress_kind": job.progress_kind,
        "processed_records": job.processed_records,
        "total_records": job.total_records,
        "current_file": job.current_file,
        "message": job.message,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "created_at": iso_z(job.created_at),
        "updated_at": iso_z(job.updated_at),
        "finished_at": iso_z(job.finished_at),
        "result": _json_object(job.result_json),
        "retry_of": job.retry_of,
        "version": job.bundle_version,
        "bundle_hash": job.bundle_hash,
    }


def _lightweight_bundle_info(root: Path) -> tuple[dict[str, Any], str, str]:
    if not root.is_dir():
        raise BundleError("内置精选数据包尚未生成。请先准备 data/datasets/featured-v1/。")
    required = ALLOWED_FILES | {"SHA256SUMS"}
    missing = sorted(relative for relative in required if not (root / relative).is_file())
    if missing:
        raise BundleError(f"内置精选数据包文件缺失: {', '.join(missing[:5])}")
    manifest_path = root / "dataset.json"
    sums_path = root / "SHA256SUMS"
    if manifest_path.stat().st_size > 1_000_000 or sums_path.stat().st_size > 2_000_000:
        raise BundleError("数据包元信息超过大小限制")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("dataset_id") != FEATURED_ID
        or manifest.get("schema_version") != 1
        or not isinstance(manifest.get("version"), str)
        or type(manifest.get("total_repositories")) is not int
        or parse_github_datetime(manifest.get("data_as_of")) is None
    ):
        raise BundleError("精选数据包 manifest 无效")
    sums_bytes = sums_path.read_bytes()
    bundle_hash = hashlib.sha256(sums_bytes).hexdigest()
    signature_parts = []
    for relative in sorted(required):
        stat_result = (root / relative).stat()
        signature_parts.append(f"{relative}:{stat_result.st_size}:{stat_result.st_mtime_ns}")
    signature = hashlib.sha256("\n".join(signature_parts).encode()).hexdigest()
    return manifest, bundle_hash, signature


def record_bundle_verification(session: Session, record_counts: dict[str, int]) -> None:
    _manifest, bundle_hash, signature = _lightweight_bundle_info(BUNDLE_ROOT)
    now = iso_z(utc_now())
    payload = json.dumps({
        "bundle_hash": bundle_hash,
        "signature": signature,
        "verified_at": now,
        "record_counts": record_counts,
    }, ensure_ascii=False)
    setting = session.get(ApplicationSetting, "featured_bundle_verification")
    if setting is None:
        setting = ApplicationSetting(setting_key="featured_bundle_verification", setting_value=payload)
        session.add(setting)
    else:
        setting.setting_value = payload
        setting.updated_at = utc_now()
    session.commit()


def import_featured_bundle(session: Session, source: Path | None = None) -> dict[str, Any]:
    source = BUNDLE_ROOT if source is None else source
    try:
        with _bundle_directory(source) as root:
            metadata, records, bundle_hash = _load_bundle(root)
            result = _import_records(session, metadata, records, bundle_hash)
    except BundleError as exc:
        raise AppError(409, "DATASET_BUNDLE_UNAVAILABLE", str(exc)) from exc
    logger.info(json.dumps({"event": "featured_dataset_imported", "dataset_id": FEATURED_ID, "version": metadata["version"], "bundle_hash": bundle_hash, **result}, separators=(",", ":"), sort_keys=True))
    return {"dataset_id": FEATURED_ID, "version": metadata["version"], "bundle_hash": bundle_hash, **result}


def featured_bundle_archive() -> tuple[Path, str]:
    archive = BUNDLE_ROOT.with_suffix(".zip")
    try:
        directory_status = verify_dataset_bundle(BUNDLE_ROOT)
        archive_status = verify_dataset_bundle(archive)
    except (BundleError, OSError) as exc:
        raise AppError(409, "DATASET_BUNDLE_UNAVAILABLE", "精选数据包 ZIP 缺失或校验失败，请重新导出") from exc
    if archive_status["bundle_hash"] != directory_status["bundle_hash"] or archive_status["version"] != directory_status["version"]:
        raise AppError(409, "DATASET_BUNDLE_UNAVAILABLE", "精选数据包 ZIP 与内置目录版本不一致，请重新导出")
    filename = f"repovantage-dataset-{directory_status['version']}.zip"
    return archive, filename


def dataset_coverage(session: Session, dataset_id: str) -> dict[str, Any]:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "数据集不存在")
    memberships = session.scalars(select(DatasetRepository).where(DatasetRepository.dataset_id == dataset_id).order_by(DatasetRepository.repository_id)).all()
    rows = []
    for membership in memberships:
        repo = session.get(Repository, membership.repository_id)
        window = session.scalar(select(ActivityWindow).where(ActivityWindow.repository_id == membership.repository_id).order_by(desc(ActivityWindow.collected_at)).limit(1))
        details = _json_object(window.details_json) if window else {}
        rows.append({
            "repository_id": membership.repository_id,
            "full_name": repo.full_name if repo else None,
            "coverage": window.coverage if window else "not_collected",
            "window_start": iso_z(window.window_start) if window else None,
            "window_end": iso_z(window.window_end) if window else None,
            "collected_at": iso_z(window.collected_at) if window else None,
            "modules": details.get("coverage_by_module", {}),
        })
    return {"dataset_id": dataset_id, "items": rows}



# Retain patchable module-level entry points used by the API and the dataset worker.
from backend.app.services.dataset_bundle_reader import _load_bundle
from backend.app.services.dataset_record_writer import _import_records
