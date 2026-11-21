"""Build-time course snapshot validation and additive import into the local analysis database."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path, PurePosixPath

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from backend.app.analytics.metrics import numeric_summary
from backend.app.core.clock import iso_z, parse_github_datetime, utc_now
from backend.app.core.config import PROJECT_ROOT, get_settings
from backend.app.core.exceptions import AppError
from backend.app.persistence.db import begin_immediate
from backend.app.persistence.models import (
    Dataset,
    DatasetRepository,
    MaintenanceRun,
    MaintenanceWeek,
    Repository,
    RepositorySnapshot,
)
from backend.app.services.repositories import LIBRARY_ID, STANDARD_TEST_ID, STANDARD_TEST_NAME

COURSE_RESEARCH_ID = "course-research-300-v1"
COURSE_RESEARCH_NAME = "300 仓库课程研究样本（历史快照）"
BUNDLE_ROOT = (PROJECT_ROOT / "data/datasets/course-research-300-v1").resolve()
ARCHIVE_RELATIVE = Path("course-research-300-v1/weeks.json.gz")
EXPECTED_SOURCE_SHA256 = "5a463e44da2260d943a7851c872277984552fba3034e12eb8d5bb14c7c2c148d"
ALLOWED_FILES = {
    "dataset.json", "repositories.json.gz", "weekly_features.json.gz",
    "split_manifest.json", "README.md", "DATA_NOTICE.md", "SHA256SUMS",
}
MAX_COMPRESSED_BYTES = 256 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_RECORDS = 1_000_000
EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
CREDENTIAL_PATTERN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+[A-Za-z0-9._-]{20,})", re.IGNORECASE)
MACHINE_PATH_PATTERN = re.compile(r"(?:/Users/[^\s\"<>]+|/private/var/[^\s\"<>]+|[A-Z]:\\Users\\[^\s\"<>]+)")


class CourseBundleError(ValueError):
    """课程数据包校验或导入失败。"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CourseBundleError(f"课程数据包 JSON 无法读取：{path.name}") from exc
    if not isinstance(value, dict):
        raise CourseBundleError(f"课程数据包 JSON 须为对象：{path.name}")
    return value


def _read_json_gzip(path: Path) -> list[dict]:
    if not path.is_file() or path.stat().st_size > MAX_COMPRESSED_BYTES:
        raise CourseBundleError(f"课程数据文件缺失或超过限制：{path.name}")
    content = bytearray()
    try:
        with gzip.open(path, "rb") as stream:
            while chunk := stream.read(1024 * 1024):
                content.extend(chunk)
                if len(content) > MAX_UNCOMPRESSED_BYTES:
                    raise CourseBundleError("课程数据包解压内容超过 1 GiB")
        value = json.loads(content)
    except (OSError, EOFError, UnicodeError, json.JSONDecodeError) as exc:
        raise CourseBundleError(f"课程数据压缩文件损坏：{path.name}") from exc
    if not isinstance(value, list) or len(value) > MAX_RECORDS or any(not isinstance(row, dict) for row in value):
        raise CourseBundleError(f"课程数据记录格式无效：{path.name}")
    return value


def _verify_checksums(root: Path) -> str:
    sums_path = root / "SHA256SUMS"
    try:
        lines = sums_path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise CourseBundleError("课程数据 SHA256SUMS 无法读取") from exc
    expected = {}
    for line in lines:
        match = re.fullmatch(r"([a-f0-9]{64})  (.+)", line)
        if not match:
            raise CourseBundleError("课程数据 SHA256SUMS 格式无效")
        digest, relative = match.groups()
        path = PurePosixPath(relative)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts) or "\\" in relative or relative in expected:
            raise CourseBundleError("课程数据 SHA256SUMS 含有重复或不安全路径")
        expected[relative] = digest
    expected_names = ALLOWED_FILES - {"SHA256SUMS"}
    if set(expected) != expected_names:
        raise CourseBundleError("课程数据 SHA256SUMS 文件清单不完整或包含额外文件")
    actual_files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual_files != ALLOWED_FILES:
        raise CourseBundleError("课程数据包目录包含缺失或未允许的文件")
    for relative, digest in expected.items():
        if _sha256(root / relative) != digest:
            raise CourseBundleError(f"课程数据校验和不匹配：{relative}")
    bundle_hash = hashlib.sha256(sums_path.read_bytes()).hexdigest()
    return bundle_hash


def verify_course_research_bundle(source: Path = BUNDLE_ROOT) -> dict:
    root = source.expanduser().resolve()
    if not root.is_dir():
        raise CourseBundleError("300 仓库课程研究数据包未安装")
    compressed_bytes = sum(path.stat().st_size for path in root.rglob("*") if path.is_file())
    if compressed_bytes > MAX_COMPRESSED_BYTES:
        raise CourseBundleError("课程数据包超过 256 MiB")
    bundle_hash = _verify_checksums(root)
    for name in ("README.md", "DATA_NOTICE.md"):
        text = (root / name).read_text(encoding="utf-8")
        if EMAIL_PATTERN.search(text) or CREDENTIAL_PATTERN.search(text) or MACHINE_PATH_PATTERN.search(text):
            raise CourseBundleError("课程数据说明含邮箱、凭据或机器绝对路径")
    metadata = _read_json(root / "dataset.json")
    split = _read_json(root / "split_manifest.json")
    repositories = _read_json_gzip(root / "repositories.json.gz")
    weeks = _read_json_gzip(root / "weekly_features.json.gz")
    if (metadata.get("schema_version") != 1 or metadata.get("dataset_id") != COURSE_RESEARCH_ID
            or metadata.get("version") != COURSE_RESEARCH_ID or metadata.get("source_sha256") != EXPECTED_SOURCE_SHA256
            or metadata.get("split_version") != "course-150-150-v1" or metadata.get("split_counts") != {"train": 150, "test": 150}
            or split.get("source_sha256") != EXPECTED_SOURCE_SHA256
            or split.get("split_version") != metadata.get("split_version")
            or _sha256(root / "split_manifest.json") != metadata.get("split_manifest_sha256")):
        raise CourseBundleError("课程数据集元数据或冻结分组不匹配")
    repository_ids = [row.get("repository_id") for row in repositories]
    if (len(repositories) != 300 or any(type(value) is not int or value <= 0 for value in repository_ids)
            or len(set(repository_ids)) != 300 or split.get("train_count") != 150 or split.get("test_count") != 150):
        raise CourseBundleError("课程仓库清单须包含 300 个唯一稳定 ID")
    try:
        train = {int(value) for value in split.get("train_repository_ids", [])}
        test = {int(value) for value in split.get("test_repository_ids", [])}
    except (TypeError, ValueError) as exc:
        raise CourseBundleError("课程分组 ID 无效") from exc
    role_by_id = {value: "train" for value in train} | {value: "test" for value in test}
    if len(train) != 150 or len(test) != 150 or train & test or train | test != set(repository_ids):
        raise CourseBundleError("课程数据分组须互斥且完整覆盖 300 个仓库")
    if len(weeks) != 3600 or metadata.get("weekly_records") != len(weeks):
        raise CourseBundleError("课程周数据须包含 3,600 条仓库周记录")
    by_repository: dict[int, list[dict]] = {}
    for row in weeks:
        repository_id = row.get("repository_id")
        if repository_id not in role_by_id or row.get("sample_role") != role_by_id[repository_id]:
            raise CourseBundleError("课程周记录包含未知仓库或样本角色不匹配")
        if row.get("commit_coverage") not in {"complete", "true_zero", "partial", "failed", "not_applicable"}:
            raise CourseBundleError("Commit 覆盖状态无效")
        if row.get("pr_opened_coverage") not in {"complete", "true_zero", "partial", "failed", "not_applicable"}:
            raise CourseBundleError("PR opened 覆盖状态无效")
        if row.get("pr_merged_coverage") not in {"complete", "true_zero", "partial", "failed", "not_applicable"}:
            if row.get("pr_merged_coverage") != "partial_concurrent_change":
                raise CourseBundleError("PR merged 覆盖状态无效")
        for count_key, coverage_key in (("commits", "commit_coverage"), ("prs_opened", "pr_opened_coverage"), ("prs_merged", "pr_merged_coverage")):
            count = row.get(count_key)
            if count is not None and (type(count) is not int or count < 0):
                raise CourseBundleError(f"{count_key} 计数无效")
            if row[coverage_key] == "true_zero" and count != 0:
                raise CourseBundleError(f"{count_key} true_zero 状态与计数不一致")
        by_repository.setdefault(repository_id, []).append(row)
    repository_by_id = {row["repository_id"]: row for row in repositories}
    if set(by_repository) != set(repository_ids):
        raise CourseBundleError("课程仓库与周数据 ID 不匹配")
    for repository_id, rows in by_repository.items():
        rows.sort(key=lambda row: row["week_start_utc"])
        starts = [row["week_start_utc"] for row in rows]
        if (len(rows) != 12 or len(set(starts)) != 12
                or repository_by_id[repository_id].get("sample_role") != role_by_id[repository_id]
                or any(rows[index]["week_end_exclusive_utc"] != rows[index + 1]["week_start_utc"] for index in range(11))):
            raise CourseBundleError(f"仓库 {repository_id} 的 12 周窗口或角色无效")
    serialized = json.dumps([metadata, split, repositories, weeks], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if EMAIL_PATTERN.search(serialized) or CREDENTIAL_PATTERN.search(serialized) or MACHINE_PATH_PATTERN.search(serialized):
        raise CourseBundleError("课程数据记录含邮箱、凭据或机器绝对路径")
    return {"metadata": metadata, "split": split, "repositories": repositories,
            "weeks": weeks, "by_repository": by_repository, "role_by_id": role_by_id,
            "bundle_hash": bundle_hash, "bundle_root": root}


def _course_run_id(repository_id: int) -> str:
    return f"course150-v1-{repository_id}"


def course_research_dashboard(session: Session, dataset_id: str) -> dict:
    """Return only the pre-collected fields used by the overview charts."""
    dataset = session.get(Dataset, dataset_id)
    if dataset is None or dataset.type != "research" or dataset_id not in {COURSE_RESEARCH_ID, STANDARD_TEST_ID}:
        raise AppError(422, "VALIDATION_ERROR", "课程研究模式必须选择课程研究或标准测试数据集")
    try:
        source = json.loads(dataset.source_metadata_json or "{}")
    except (TypeError, ValueError):
        source = {}

    members = session.execute(
        select(DatasetRepository, Repository)
        .join(Repository, Repository.repository_id == DatasetRepository.repository_id)
        .where(
            DatasetRepository.dataset_id == dataset_id,
            DatasetRepository.exclusion_status.is_(None),
        )
        .order_by(DatasetRepository.repository_id)
    ).all()
    repository_ids = [member.repository_id for member, _repository in members]
    if not repository_ids:
        return {
            "dataset_id": dataset_id,
            "name": dataset.name,
            "repository_count": 0,
            "course_summary": {"data_as_of": source.get("data_as_of"), "weekly_records": 0,
                               "repositories_with_12_complete_commit_weeks": 0},
            "course_language_groups": [],
            "course_repositories": [],
        }

    latest_snapshots: dict[int, RepositorySnapshot] = {}
    for snapshot in session.scalars(
        select(RepositorySnapshot)
        .where(RepositorySnapshot.repository_id.in_(repository_ids), RepositorySnapshot.valid.is_(True))
        .order_by(desc(RepositorySnapshot.collected_at), desc(RepositorySnapshot.id))
    ).all():
        latest_snapshots.setdefault(snapshot.repository_id, snapshot)

    run_ids = [_course_run_id(repository_id) for repository_id in repository_ids]
    runs = {run.repository_id: run for run in session.scalars(
        select(MaintenanceRun).where(MaintenanceRun.run_id.in_(run_ids))
    ).all()}
    weeks_by_run: dict[str, list[MaintenanceWeek]] = {}
    weeks = session.scalars(
        select(MaintenanceWeek)
        .where(MaintenanceWeek.run_id.in_(run_ids))
        .order_by(MaintenanceWeek.run_id, MaintenanceWeek.week_start)
    ).all()
    for week in weeks:
        weeks_by_run.setdefault(week.run_id, []).append(week)

    rows = []
    language_groups: dict[str, dict[str, float | int]] = {}
    complete_commit_repositories = 0
    for member, repository in members:
        run = runs.get(member.repository_id)
        repository_weeks = weeks_by_run.get(run.run_id, []) if run else []
        complete_weeks = [week for week in repository_weeks if week.commit_coverage in {"complete", "true_zero"}]
        weekly_mean = None
        active_weeks = None
        if len(complete_weeks) == 12:
            complete_commit_repositories += 1
            weekly_mean = sum(week.commits for week in complete_weeks) / 12
            active_weeks = sum(week.commits > 0 for week in complete_weeks)
            group = language_groups.setdefault(repository.language or "未知", {"repository_count": 0, "commit_sample_count": 0, "weekly_commit_total": 0.0})
            group["commit_sample_count"] += 1
            group["weekly_commit_total"] += weekly_mean

        language = repository.language or "未知"
        group = language_groups.setdefault(language, {"repository_count": 0, "commit_sample_count": 0, "weekly_commit_total": 0.0})
        group["repository_count"] += 1
        snapshot = latest_snapshots.get(member.repository_id)
        rows.append({
            "repository_id": member.repository_id,
            "full_name": repository.full_name,
            "language": language,
            "sample_role": member.selection_tier,
            "weekly_commit_mean": weekly_mean,
            "active_weeks": active_weeks,
            "stars": snapshot.stars if snapshot else None,
            "forks": snapshot.forks if snapshot else None,
            "created_at": iso_z(repository.created_at) if repository.created_at else None,
        })

    groups = [{
        "language": language,
        "repository_count": int(values["repository_count"]),
        "commit_sample_count": int(values["commit_sample_count"]),
        "weekly_commit_mean": (float(values["weekly_commit_total"]) / int(values["commit_sample_count"]))
        if values["commit_sample_count"] else None,
    } for language, values in sorted(language_groups.items())]
    return {
        "dataset_id": dataset_id,
        "name": dataset.name,
        "repository_count": len(rows),
        "course_summary": {
            "data_as_of": source.get("data_as_of"),
            "weekly_records": len(weeks),
            "repositories_with_12_complete_commit_weeks": complete_commit_repositories,
        },
        "course_language_groups": groups,
        "course_repositories": rows,
    }


def course_research_atlas(session: Session, dataset_id: str = COURSE_RESEARCH_ID) -> dict:
    """Return the 300 course repositories and 12-week traces in bounded batch queries."""
    dataset = session.get(Dataset, dataset_id)
    if dataset is None or dataset.type != "research" or dataset_id != COURSE_RESEARCH_ID:
        raise AppError(422, "VALIDATION_ERROR", "仓库研究图谱只使用冻结的 300 仓库课程样本")
    try:
        source = json.loads(dataset.source_metadata_json or "{}")
    except (TypeError, ValueError):
        source = {}
    members = session.execute(
        select(DatasetRepository, Repository)
        .join(Repository, Repository.repository_id == DatasetRepository.repository_id)
        .where(DatasetRepository.dataset_id == dataset_id, DatasetRepository.exclusion_status.is_(None))
        .order_by(DatasetRepository.repository_id)
    ).all()
    repository_ids = [member.repository_id for member, _repository in members]
    run_ids = [_course_run_id(repository_id) for repository_id in repository_ids]
    runs = session.scalars(select(MaintenanceRun).where(MaintenanceRun.run_id.in_(run_ids))).all() if run_ids else []
    run_by_repository = {run.repository_id: run for run in runs}
    actual_run_ids = [run.run_id for run in runs]
    weeks = session.scalars(
        select(MaintenanceWeek)
        .where(MaintenanceWeek.run_id.in_(actual_run_ids))
        .order_by(MaintenanceWeek.run_id, MaintenanceWeek.week_start)
    ).all() if actual_run_ids else []
    weeks_by_run: dict[str, list[MaintenanceWeek]] = {}
    for week in weeks:
        weeks_by_run.setdefault(week.run_id, []).append(week)
    snapshots: dict[int, RepositorySnapshot] = {}
    if repository_ids:
        for snapshot in session.scalars(
            select(RepositorySnapshot)
            .where(RepositorySnapshot.repository_id.in_(repository_ids), RepositorySnapshot.valid.is_(True))
            .order_by(desc(RepositorySnapshot.collected_at), desc(RepositorySnapshot.id))
        ).all():
            snapshots.setdefault(snapshot.repository_id, snapshot)

    points, excluded = [], Counter()
    for member, repository in members:
        run = run_by_repository.get(member.repository_id)
        trace = weeks_by_run.get(run.run_id, []) if run else []
        if len(trace) != 12:
            excluded["week_records_not_12"] += 1
            continue
        complete = all(
            week.commit_coverage in {"complete", "true_zero"}
            and week.pr_created_coverage in {"complete", "true_zero"}
            for week in trace
        )
        if not complete:
            excluded["12_week_activity_coverage_incomplete"] += 1
            continue
        snapshot = snapshots.get(member.repository_id)
        points.append({
            "repository_id": member.repository_id,
            "full_name": repository.full_name,
            "language": repository.language or "未知",
            "sample_role": member.selection_tier,
            "stars": snapshot.stars if snapshot else None,
            "weekly_commit_mean": sum(week.commits for week in trace) / 12,
            "weekly_pr_open_mean": sum(week.prs_created for week in trace) / 12,
            "observation_window": {
                "start": iso_z(trace[0].week_start),
                "end_exclusive": iso_z(trace[-1].week_end),
                "weeks": 12,
            },
            "coverage": {"commits": "complete", "prs_opened": "complete"},
            "weekly_trace": [
                {"week_start": iso_z(week.week_start), "commits": week.commits, "prs_opened": week.prs_created}
                for week in trace
            ],
        })
    return {
        "dataset_id": dataset_id,
        "data_as_of": source.get("data_as_of"),
        "observation_window": source.get("observation_window"),
        "repository_count": len(members),
        "point_count": len(points),
        "excluded_count": len(members) - len(points),
        "excluded_reasons": dict(sorted(excluded.items())),
        "weekly_record_count": len(weeks),
        "coordinates": {
            "x": "12 周周均 Commit",
            "y": "12 周周均新开 PR",
            "stars": "仅为已核验快照的点大小上下文；缺失时不插补",
        },
        "points": points,
    }


def _standard_test_metadata(bundle: dict) -> dict:
    metadata = bundle["metadata"]
    test_ids = {repository_id for repository_id, role in bundle["role_by_id"].items() if role == "test"}
    test_weeks = [row for row in bundle["weeks"] if row["repository_id"] in test_ids]
    complete_commit_weeks = [row for row in test_weeks if row["commit_coverage"] in {"complete", "true_zero"}]
    complete_pr_opened_weeks = [row for row in test_weeks if row["pr_opened_coverage"] in {"complete", "true_zero"}]
    complete_pr_merged_weeks = [row for row in test_weeks if row["pr_merged_coverage"] in {"complete", "true_zero"}]
    return {
        **metadata,
        "dataset_id": STANDARD_TEST_ID,
        "dataset_name": STANDARD_TEST_NAME,
        "version": STANDARD_TEST_ID,
        "source_dataset_id": COURSE_RESEARCH_ID,
        "selected_sample_role": "test",
        "total_repositories": len(test_ids),
        "weekly_records": len(test_weeks),
        "repositories_with_12_complete_commit_weeks": sum(
            sum(row["repository_id"] == repository_id and row["commit_coverage"] in {"complete", "true_zero"} for row in test_weeks) == 12
            for repository_id in test_ids
        ),
        "coverage": {
            "commit_week_complete_or_true_zero": len(complete_commit_weeks),
            "commit_week_failed": sum(row["commit_coverage"] == "failed" for row in test_weeks),
            "commit_week_partial": sum(row["commit_coverage"] == "partial" for row in test_weeks),
            "commits_in_complete_or_true_zero_weeks": sum(row["commits"] or 0 for row in complete_commit_weeks),
            "pr_opened_week_complete_or_true_zero": len(complete_pr_opened_weeks),
            "pr_merged_week_complete_or_true_zero": len(complete_pr_merged_weeks),
            "pr_merged_week_partial_concurrent_change": sum(row["pr_merged_coverage"] == "partial_concurrent_change" for row in test_weeks),
            "prs_opened_in_complete_or_true_zero_weeks": sum(row["prs_opened"] or 0 for row in complete_pr_opened_weeks),
            "prs_merged_in_complete_or_true_zero_weeks": sum(row["prs_merged"] or 0 for row in complete_pr_merged_weeks),
        },
    }


def _ensure_standard_test_dataset(session: Session, bundle: dict) -> int:
    expected_ids = {repository_id for repository_id, role in bundle["role_by_id"].items() if role == "test"}
    dataset = session.get(Dataset, STANDARD_TEST_ID)
    if dataset is not None and dataset.type != "research":
        raise CourseBundleError(f"{STANDARD_TEST_ID} 已被其他数据集类型占用")
    existing = session.scalars(select(DatasetRepository).where(DatasetRepository.dataset_id == STANDARD_TEST_ID)).all()
    metadata = _standard_test_metadata(bundle)
    if existing:
        existing_ids = {member.repository_id for member in existing}
        current = {}
        if dataset and dataset.source_metadata_json:
            try:
                current = json.loads(dataset.source_metadata_json)
            except (TypeError, ValueError):
                current = {}
        if existing_ids != expected_ids or current.get("bundle_hash") != bundle["bundle_hash"]:
            raise CourseBundleError(f"{STANDARD_TEST_ID} 已含其他成员或版本；拒绝覆盖")
        for member in existing:
            member.selection_tier = "test"
            member.inclusion_reason = "固定 150/150 留仓测试组；作为应用标准样本，不参与模型训练"
            member.selection_source = COURSE_RESEARCH_ID
        added = 0
    else:
        if dataset is None:
            dataset = Dataset(dataset_id=STANDARD_TEST_ID, name=STANDARD_TEST_NAME, type="research")
            session.add(dataset)
        for repository_id in sorted(expected_ids):
            if session.get(Repository, repository_id) is None:
                raise CourseBundleError(f"标准测试样本缺少仓库资料：{repository_id}")
            session.add(DatasetRepository(
                dataset_id=STANDARD_TEST_ID,
                repository_id=repository_id,
                added_at=utc_now(),
                selection_tier="test",
                inclusion_reason="固定 150/150 留仓测试组；作为应用标准样本，不参与模型训练",
                selection_source=COURSE_RESEARCH_ID,
            ))
        added = len(expected_ids)
    assert dataset is not None
    dataset.name = STANDARD_TEST_NAME
    dataset.type = "research"
    dataset.rules_version = STANDARD_TEST_ID
    dataset.frozen_at = parse_github_datetime(metadata["data_as_of"])
    dataset.description = "机器学习标准测试数据；固定 150 个留出仓库，仅用于标准展示和留出评估，不用于训练。"
    dataset.source_metadata_json = json.dumps({**metadata, "bundle_hash": bundle["bundle_hash"]}, ensure_ascii=False)
    session.flush()
    return added


def _remove_course_library_memberships(session: Session) -> tuple[int, int]:
    """Keep the 300-repository ML cohort out of the user-facing repository library."""
    imported_members = session.scalars(select(DatasetRepository).where(
        DatasetRepository.dataset_id == LIBRARY_ID,
        DatasetRepository.selection_source == COURSE_RESEARCH_ID,
    )).all()
    for member in imported_members:
        session.delete(member)
    return 0, len(imported_members)


def _copy_archive(source: Path, archive_root: Path) -> str:
    archive_root = archive_root.expanduser().resolve()
    target = archive_root / ARCHIVE_RELATIVE
    target.parent.mkdir(parents=True, exist_ok=True)
    source_hash = _sha256(source)
    if target.exists():
        if _sha256(target) != source_hash:
            raise CourseBundleError(f"课程分析归档已存在且内容不同：{target}")
        return target.relative_to(archive_root).as_posix()
    with tempfile.NamedTemporaryFile(prefix=".course-weeks-", dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target.relative_to(archive_root).as_posix()


def import_course_research_bundle(session: Session, source: Path = BUNDLE_ROOT, *, archive_root: Path | None = None) -> dict:
    bundle = verify_course_research_bundle(source)
    metadata, repositories, weeks = bundle["metadata"], bundle["repositories"], bundle["weeks"]
    archive_root = archive_root or get_settings().raw_data_path
    archive_path = _copy_archive(bundle["bundle_root"] / "weekly_features.json.gz", archive_root)
    existing_count = session.scalar(select(func.count()).select_from(DatasetRepository).where(
        DatasetRepository.dataset_id == COURSE_RESEARCH_ID)) or 0
    dataset = session.get(Dataset, COURSE_RESEARCH_ID)
    if existing_count:
        current = {}
        if dataset and dataset.source_metadata_json:
            try:
                current = json.loads(dataset.source_metadata_json)
            except (TypeError, ValueError):
                current = {}
        if existing_count == 300 and current.get("bundle_hash") == bundle["bundle_hash"]:
            standard_added = _ensure_standard_test_dataset(session, bundle)
            library_added, library_removed = _remove_course_library_memberships(session)
            session.commit()
            return {"dataset_id": COURSE_RESEARCH_ID, "bundle_hash": bundle["bundle_hash"],
                    "repositories": 300, "standard_test_repositories_added": standard_added,
                    "library_memberships_added": library_added, "library_memberships_removed": library_removed,
                    "already_imported": True, "archive_path": archive_path}
        raise CourseBundleError("course-research-300-v1 已含其他成员或版本；拒绝覆盖")
    if dataset is not None and dataset.type != "research":
        raise CourseBundleError("course-research-300-v1 已被其他数据集类型占用")

    from backend.app.services.maintenance import _hash_source

    begin_immediate(session)
    now = utc_now()
    if dataset is None:
        dataset = Dataset(dataset_id=COURSE_RESEARCH_ID, name=COURSE_RESEARCH_NAME, type="research")
        session.add(dataset)
    dataset.name = COURSE_RESEARCH_NAME
    dataset.type = "research"
    dataset.rules_version = metadata["version"]
    dataset.frozen_at = parse_github_datetime(metadata["data_as_of"])
    dataset.description = "300 个仓库的固定课程研究历史快照；新在线采集数据优先。"
    dataset.source_metadata_json = json.dumps({**metadata, "bundle_hash": bundle["bundle_hash"]}, ensure_ascii=False)
    session.flush()

    counts = {"repositories": 0, "repository_records_created": 0, "library_memberships_added": 0,
              "snapshots_added": 0, "snapshots_skipped_newer": 0, "maintenance_runs_added": 0,
              "maintenance_weeks_added": 0}
    repositories_by_id = {row["repository_id"]: row for row in repositories}
    for repository_id in sorted(repositories_by_id):
        row = repositories_by_id[repository_id]
        profile_time = parse_github_datetime(row.get("fetched_at") or row.get("snapshot_at")) or parse_github_datetime(metadata["data_as_of"]) or now
        repository = session.get(Repository, repository_id)
        if repository is None:
            name_conflict = session.scalar(select(Repository.repository_id).where(Repository.full_name == row["full_name"]).limit(1))
            if name_conflict is not None:
                raise CourseBundleError(f"仓库名已对应其他稳定 ID，拒绝覆盖：{row['full_name']}")
            repository = Repository(
                repository_id=repository_id, full_name=row["full_name"], html_url=row["html_url"],
                description=row.get("description"), language=None if row.get("language") == "未知" else row.get("language"),
                topics_json=json.dumps(row.get("topics", []), ensure_ascii=False), license_spdx=row.get("license_spdx"),
                created_at=parse_github_datetime(row.get("created_at")), pushed_at=parse_github_datetime(row.get("pushed_at")),
                github_updated_at=parse_github_datetime(row.get("github_updated_at")), archived=bool(row.get("archived")),
                is_fork=bool(row.get("is_fork")), size_kb=row.get("size_kb"), first_seen_at=profile_time,
                last_seen_at=profile_time,
            )
            session.add(repository)
            session.flush()
            counts["repository_records_created"] += 1
        elif repository.full_name != row["full_name"]:
            # A newer local record may reflect a repository rename. Preserve it and its live fields.
            pass
        role = bundle["role_by_id"][repository_id]
        course_membership = session.get(DatasetRepository, (COURSE_RESEARCH_ID, repository_id))
        if course_membership is None:
            session.add(DatasetRepository(
                dataset_id=COURSE_RESEARCH_ID, repository_id=repository_id,
                added_at=profile_time, selection_tier=role,
                inclusion_reason="固定 150/150 课程回测样本；该角色仅说明实验分组",
                selection_source=COURSE_RESEARCH_ID,
            ))

        source_time = parse_github_datetime(row.get("snapshot_at") or row.get("fetched_at")) or profile_time
        latest_snapshot = session.scalar(select(RepositorySnapshot).where(
            RepositorySnapshot.repository_id == repository_id, RepositorySnapshot.valid.is_(True)
        ).order_by(desc(RepositorySnapshot.collected_at), desc(RepositorySnapshot.id)).limit(1))
        if latest_snapshot is None or latest_snapshot.collected_at < source_time:
            session.add(RepositorySnapshot(
                repository_id=repository_id, collected_at=source_time, stars=row.get("stars"), forks=row.get("forks"),
                open_issues_and_pr_count=None, pushed_at=parse_github_datetime(row.get("pushed_at")),
                github_updated_at=parse_github_datetime(row.get("github_updated_at")),
                response_etag=row.get("response_etag"), source_http_status=row.get("http_status") or 200,
                source_archive_path=archive_path, valid=True,
            ))
            counts["snapshots_added"] += 1
        else:
            counts["snapshots_skipped_newer"] += 1

        run_id = _course_run_id(repository_id)
        if session.get(MaintenanceRun, run_id) is None:
            normalized = []
            for item in bundle["by_repository"][repository_id]:
                commits = item.get("commits")
                prs = item.get("prs_opened")
                # The schema requires integer storage; coverage remains partial so this placeholder is never presented as a zero observation.
                normalized.append({
                    "week_start_utc": item["week_start_utc"],
                    "week_end_exclusive_utc": item["week_end_exclusive_utc"],
                    "commits": commits if commits is not None else 0,
                    "prs_created": prs if prs is not None else 0,
                    "commit_coverage": item["commit_coverage"],
                    "pr_created_coverage": item["pr_opened_coverage"],
                })
            history_start = parse_github_datetime(normalized[0]["week_start_utc"])
            history_end = parse_github_datetime(normalized[-1]["week_end_exclusive_utc"])
            commit_complete = all(row["commit_coverage"] in {"complete", "true_zero"} for row in normalized)
            details = {
                "dataset_id": COURSE_RESEARCH_ID,
                "data_source": "course_research_historical_snapshot",
                "data_as_of": metadata["data_as_of"],
                "split_version": metadata["split_version"],
                "sample_role": bundle["role_by_id"][repository_id],
                "source_data_sha256": metadata["source_sha256"],
                "archive_sha256": _sha256(bundle["bundle_root"] / "weekly_features.json.gz"),
                "snapshot_notice": "固定历史快照；不表示当前实时仓库活动。",
            }
            session.add(MaintenanceRun(
                run_id=run_id, repository_id=repository_id, status="complete" if commit_complete else "partial",
                history_start=history_start, history_end=history_end, captured_at=source_time,
                head_sha=None, source_sha256=_hash_source(normalized, None, iso_z(history_start), iso_z(history_end)),
                archive_path=archive_path, details_json=json.dumps(details, ensure_ascii=False),
            ))
            session.flush()
            for week in normalized:
                session.add(MaintenanceWeek(
                    run_id=run_id, week_start=parse_github_datetime(week["week_start_utc"]),
                    week_end=parse_github_datetime(week["week_end_exclusive_utc"]), commits=week["commits"],
                    prs_created=week["prs_created"], commit_coverage=week["commit_coverage"],
                    pr_created_coverage=week["pr_created_coverage"],
                ))
                counts["maintenance_weeks_added"] += 1
            counts["maintenance_runs_added"] += 1
        counts["repositories"] += 1
    counts["standard_test_repositories_added"] = _ensure_standard_test_dataset(session, bundle)
    counts["library_memberships_added"], counts["library_memberships_removed"] = _remove_course_library_memberships(session)
    session.commit()
    return {"dataset_id": COURSE_RESEARCH_ID, "bundle_hash": bundle["bundle_hash"],
            "already_imported": False, "archive_path": archive_path, **counts}


def course_research_insights(session: Session, dataset_id: str) -> dict:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None or dataset.type != "research" or dataset_id not in {COURSE_RESEARCH_ID, STANDARD_TEST_ID}:
        raise CourseBundleError("course analysis requires a course research dataset")
    try:
        source = json.loads(dataset.source_metadata_json or "{}")
    except (TypeError, ValueError):
        source = {}
    memberships = session.execute(
        select(DatasetRepository, Repository)
        .join(Repository, Repository.repository_id == DatasetRepository.repository_id)
        .where(DatasetRepository.dataset_id == dataset_id, DatasetRepository.exclusion_status.is_(None))
        .order_by(DatasetRepository.repository_id)
    ).all()
    repository_ids = [member.repository_id for member, _repository in memberships]
    latest_snapshots: dict[int, RepositorySnapshot] = {}
    for snapshot in session.scalars(select(RepositorySnapshot).where(
        RepositorySnapshot.repository_id.in_(repository_ids), RepositorySnapshot.valid.is_(True)
    ).order_by(desc(RepositorySnapshot.collected_at), desc(RepositorySnapshot.id))).all():
        latest_snapshots.setdefault(snapshot.repository_id, snapshot)
    run_ids = [_course_run_id(repository_id) for repository_id in repository_ids]
    runs_by_repository = {
        run.repository_id: run
        for run in session.scalars(select(MaintenanceRun).where(MaintenanceRun.run_id.in_(run_ids))).all()
    }
    weeks_by_run: dict[str, list[MaintenanceWeek]] = {}
    for week in session.scalars(
        select(MaintenanceWeek)
        .where(MaintenanceWeek.run_id.in_(run_ids))
        .order_by(MaintenanceWeek.run_id, MaintenanceWeek.week_start)
    ).all():
        weeks_by_run.setdefault(week.run_id, []).append(week)
    event_repository_ids = set(session.scalars(select(DatasetRepository.repository_id).where(
        DatasetRepository.dataset_id == COURSE_RESEARCH_ID,
        DatasetRepository.repository_id.in_(repository_ids),
        DatasetRepository.exclusion_status.is_(None),
    )).all()) if repository_ids else set()
    from backend.app.services.course_test_events import _snapshot, historical_metric_summary
    event_snapshot = _snapshot()
    event_connection = None
    event_manifest = None
    if event_snapshot is not None:
        path, event_manifest = event_snapshot
        try:
            event_connection = sqlite3.connect(f"{path.as_uri()}?mode=ro&immutable=1", uri=True)
            event_connection.row_factory = sqlite3.Row
        except (OSError, sqlite3.Error) as exc:
            raise AppError(503, "COURSE_TEST_EVENTS_UNAVAILABLE", "历史事件数据无法读取") from exc

    event_metrics = {
        "issue_median_hours": ("issue_resolution", "median_hours", "hours"),
        "pr_median_hours": ("pr_merges", "median_hours", "hours"),
        "release_interval_days": ("release_cadence", "median_interval_days", "days"),
    }
    metric_units = {"commits_weekly_mean": "commits/week", **{key: value[2] for key, value in event_metrics.items()}}
    rows, grouped = [], {}
    weekly_record_count = 0
    event_window_end = None
    for member, repository in memberships:
        snapshot = latest_snapshots.get(member.repository_id)
        run = runs_by_repository.get(member.repository_id)
        weeks = weeks_by_run.get(run.run_id, []) if run else []
        weekly_record_count += len(weeks)
        complete = [week for week in weeks if week.commit_coverage in {"complete", "true_zero"}]
        total = sum(week.commits for week in complete) if len(complete) == 12 else None
        active = sum(week.commits > 0 for week in complete) if len(complete) == 12 else None
        mean = total / 12 if total is not None else None
        language = repository.language or "未知"
        values = {"commits_weekly_mean": mean, "course_commit_total_12w": total, "course_active_weeks_12w": active}
        quality = {
            "commits_weekly_mean": {"status": "ready" if total is not None else "insufficient_data",
                                    "coverage": "complete" if total is not None else "partial",
                                    "valid_samples": 12 if total is not None else len(complete),
                                    "reason": None if total is not None else "最近 12 周 Commit 覆盖不完整"},
        }
        event_available = (
            event_connection is not None
            and member.repository_id in event_repository_ids
            and run is not None
        )
        event_result = historical_metric_summary(event_connection, event_manifest, member.repository_id, 90) if event_available else None
        if event_result and event_window_end is None:
            event_window_end = event_result["window_end"]
        for key, (metric_name, value_key, _unit) in event_metrics.items():
            metric = event_result["insights"].get(metric_name) if event_result else None
            event_quality = metric.get("quality", {}) if metric else {}
            value = metric.get(value_key) if metric and event_quality.get("status") in {"ready", "partial"} else None
            values[key] = value
            quality[key] = {
                "status": event_quality.get("status", "missing"),
                "coverage": event_quality.get("coverage", "not_collected"),
                "valid_samples": event_quality.get("valid_samples", 0),
                "reason": event_quality.get("reason") if value is not None else (
                    "窗口内没有可计算的有效记录" if event_result else "本地历史事件不可用"
                ),
            }
        row = {
            "repository_id": member.repository_id, "full_name": repository.full_name, "language": language,
            "stars": snapshot.stars if snapshot else None,
            "forks": snapshot.forks if snapshot else None,
            "created_at": iso_z(repository.created_at) if repository.created_at else None,
            "analyzed_at": iso_z(run.captured_at) if run else None,
            "window_start": iso_z(weeks[0].week_start) if len(weeks) == 12 else None,
            "window_end": iso_z(weeks[-1].week_end) if len(weeks) == 12 else None,
            "run_id": run.run_id if run else None,
            "sample_role": member.selection_tier,
            "values": values, "metric_quality": quality,
        }
        rows.append(row)
        grouped.setdefault(language, []).append(row)
    if event_connection is not None:
        event_connection.close()
    groups = [{"language": language, "n": len(grouped[language]),
               "metrics": {key: numeric_summary([row["values"][key] for row in grouped[language] if row["values"][key] is not None])
                           for key in metric_units}}
              for language in sorted(grouped)]
    eligible_count = sum(row["values"]["course_commit_total_12w"] is not None for row in rows)
    summary, metric_quality = {}, {}
    for key, unit in metric_units.items():
        available = [row["values"][key] for row in rows if row["values"][key] is not None]
        missing_count = len(rows) - len(available)
        missing_rate = missing_count / len(rows) if rows else None
        statuses = Counter(row["metric_quality"][key]["status"] for row in rows)
        reasons = Counter(row["metric_quality"][key]["reason"] or "窗口内没有可计算的有效记录"
                          for row in rows if row["values"][key] is None)
        summary[key] = {**numeric_summary(available), "missing_count": missing_count, "missing_rate": missing_rate, "unit": unit}
        metric_quality[key] = {"valid_samples": len(available), "missing_count": missing_count, "missing_rate": missing_rate,
                               "partial_count": sum(row["values"][key] is not None and row["metric_quality"][key]["status"] == "partial" for row in rows),
                               "status_counts": dict(sorted(statuses.items())),
                               "missing_reasons": [{"reason": reason, "count": count} for reason, count in sorted(reasons.items())]}
    paired_count = sum(row["values"]["issue_median_hours"] is not None and row["values"]["pr_median_hours"] is not None for row in rows)
    course_summary = {
        "data_as_of": source.get("data_as_of"),
        "observation_window": source.get("observation_window"),
        "event_window_end": event_window_end,
        "weekly_records": weekly_record_count,
        "repositories_with_12_complete_commit_weeks": eligible_count,
        "split_counts": source.get("split_counts", {"train": 0, "test": 0}),
        "selected_sample_role": source.get("selected_sample_role", "all"),
        "coverage": source.get("coverage", {}),
    }
    return {
        "dataset_id": dataset_id, "analysis_mode": "course",
        "dataset_status": "analyzable" if rows else "awaiting_collection",
        "population_scope": "course_research_historical_snapshot", "is_probability_sample": False,
        "dataset_version": source.get("version") or dataset.rules_version,
        "frozen_at": iso_z(dataset.frozen_at), "sample_size": len(rows), "analyzable_members": eligible_count,
        "source": source.get("source") or dataset.description,
        "metric_version": dataset_id, "summary": summary, "metric_quality": metric_quality,
        "groups": groups, "rows": rows,
        "correlation": {"n": paired_count, "coefficient": None, "p_value": None, "note": "本页提供描述性统计；部分指标依据已观察样本。"},
        "course_summary": course_summary,
        "limitations": [
            "这是固定历史快照，不是实时仓库状态；若存在更新的在线采集，仓库分析使用更新数据。",
            "提交趋势模型只输出未来四周类别；M1 反映提交模式，M3 是 MAD 统计提示。",
            "train/test 标签仅说明本次历史回测角色；测试组不是全新外部样本。",
            *( ["当前标准数据只包含固定的留出测试组；训练组仅保留在完整 300 仓库实验数据集中。"] if source.get("selected_sample_role") == "test" else [] ),
            "Commit 使用最近 12 个完整周；Issue、PR 使用事件快照中的 90 天窗口，Release 使用 365 天窗口。部分覆盖指标按已观察样本统计。",
        ],
    }
