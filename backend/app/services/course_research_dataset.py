"""Build-time course snapshot validation and additive import into the local analysis database."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from backend.app.core.clock import iso_z, parse_github_datetime, utc_now
from backend.app.core.config import PROJECT_ROOT, get_settings
from backend.app.persistence.db import begin_immediate
from backend.app.persistence.models import (
    Dataset,
    DatasetRepository,
    MaintenanceRun,
    MaintenanceWeek,
    Repository,
    RepositorySnapshot,
)
from backend.app.services.repositories import LIBRARY_ID

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
            return {"dataset_id": COURSE_RESEARCH_ID, "bundle_hash": bundle["bundle_hash"],
                    "repositories": 300, "already_imported": True, "archive_path": archive_path}
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
        for dataset_id, role in ((COURSE_RESEARCH_ID, bundle["role_by_id"][repository_id]), (LIBRARY_ID, None)):
            membership = session.get(DatasetRepository, (dataset_id, repository_id))
            if membership is None:
                session.add(DatasetRepository(
                    dataset_id=dataset_id, repository_id=repository_id,
                    added_at=profile_time, selection_tier=role,
                    inclusion_reason=("固定 150/150 课程回测样本；该角色仅说明实验分组" if dataset_id == COURSE_RESEARCH_ID else None),
                    selection_source="course-research-300-v1",
                ))
                if dataset_id == LIBRARY_ID:
                    counts["library_memberships_added"] += 1

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
    session.commit()
    return {"dataset_id": COURSE_RESEARCH_ID, "bundle_hash": bundle["bundle_hash"],
            "already_imported": False, "archive_path": archive_path, **counts}


def course_research_insights(session: Session, dataset_id: str) -> dict:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None or dataset.type != "research" or dataset_id != COURSE_RESEARCH_ID:
        raise CourseBundleError("course analysis requires course-research-300-v1 research dataset")
    try:
        source = json.loads(dataset.source_metadata_json or "{}")
    except (TypeError, ValueError):
        source = {}
    memberships = session.scalars(select(DatasetRepository).where(
        DatasetRepository.dataset_id == dataset_id, DatasetRepository.exclusion_status.is_(None)
    ).order_by(DatasetRepository.repository_id)).all()
    rows, grouped = [], {}
    for member in memberships:
        repository = session.get(Repository, member.repository_id)
        if repository is None:
            continue
        run = session.get(MaintenanceRun, _course_run_id(member.repository_id))
        weeks = session.scalars(select(MaintenanceWeek).where(
            MaintenanceWeek.run_id == run.run_id
        ).order_by(MaintenanceWeek.week_start)).all() if run else []
        complete = [week for week in weeks if week.commit_coverage in {"complete", "true_zero"}]
        total = sum(week.commits for week in complete) if len(complete) == 12 else None
        active = sum(week.commits > 0 for week in complete) if len(complete) == 12 else None
        mean = total / 12 if total is not None else None
        language = repository.language or "未知"
        grouped.setdefault(language, []).append(mean)
        rows.append({
            "repository_id": member.repository_id, "full_name": repository.full_name, "language": language,
            "analyzed_at": iso_z(run.captured_at) if run else None,
            "window_start": iso_z(weeks[0].week_start) if len(weeks) == 12 else None,
            "window_end": iso_z(weeks[-1].week_end) if len(weeks) == 12 else None,
            "run_id": run.run_id if run else None,
            "sample_role": member.selection_tier,
            "values": {"commits_weekly_mean": mean, "issue_median_hours": None,
                       "pr_median_hours": None, "release_interval_days": None,
                       "course_commit_total_12w": total, "course_active_weeks_12w": active},
            "metric_quality": {
                "commits_weekly_mean": {"status": "ready" if total is not None else "insufficient_data",
                                         "coverage": "complete" if total is not None else "partial",
                                         "valid_samples": 12 if total is not None else len(complete),
                                         "reason": None if total is not None else "最近 12 周 Commit 覆盖不完整"},
                "issue_median_hours": {"status": "missing", "coverage": "not_collected", "valid_samples": 0, "reason": "本课程数据包不含 Issue 事件"},
                "pr_median_hours": {"status": "missing", "coverage": "not_collected", "valid_samples": 0, "reason": "周级 PR 数量不包含合并耗时事件"},
                "release_interval_days": {"status": "missing", "coverage": "not_collected", "valid_samples": 0, "reason": "本课程数据包不含 Release 事件"},
            },
        })
    languages = sorted(grouped)
    groups = [{"language": language, "n": len(grouped[language]),
               "metrics": {"commits_weekly_mean": {"count": sum(value is not None for value in grouped[language]),
                                                     "mean": (sum(value for value in grouped[language] if value is not None) / max(1, sum(value is not None for value in grouped[language]))) if any(value is not None for value in grouped[language]) else None,
                                                     "median": None, "std": None},
                           "issue_median_hours": {"count": 0, "mean": None, "median": None, "std": None},
                           "pr_median_hours": {"count": 0, "mean": None, "median": None, "std": None},
                           "release_interval_days": {"count": 0, "mean": None, "median": None, "std": None}}}
              for language in languages]
    eligible_count = sum(row["values"]["course_commit_total_12w"] is not None for row in rows)
    missing_reasons = [{"reason": "本课程数据包不含 Issue 事件", "count": len(rows)}]
    summary = {
        "commits_weekly_mean": {"count": eligible_count, "mean": (sum(row["values"]["commits_weekly_mean"] for row in rows if row["values"]["commits_weekly_mean"] is not None) / eligible_count) if eligible_count else None,
                                "median": None, "std": None, "missing_count": len(rows) - eligible_count,
                                "missing_rate": (len(rows) - eligible_count) / len(rows) if rows else None, "unit": "commits/week"},
        "issue_median_hours": {"count": 0, "mean": None, "median": None, "std": None,
                               "missing_count": len(rows), "missing_rate": 1.0 if rows else None, "unit": "hours"},
        "pr_median_hours": {"count": 0, "mean": None, "median": None, "std": None,
                            "missing_count": len(rows), "missing_rate": 1.0 if rows else None, "unit": "hours"},
        "release_interval_days": {"count": 0, "mean": None, "median": None, "std": None,
                                  "missing_count": len(rows), "missing_rate": 1.0 if rows else None, "unit": "days"},
    }
    metric_quality = {
        "commits_weekly_mean": {"valid_samples": eligible_count, "missing_count": len(rows) - eligible_count,
                                "missing_rate": (len(rows) - eligible_count) / len(rows) if rows else None,
                                "status_counts": {"ready": eligible_count, "insufficient_data": len(rows) - eligible_count},
                                "missing_reasons": ([{"reason": "最近 12 周 Commit 覆盖不完整", "count": len(rows) - eligible_count}] if eligible_count < len(rows) else [])},
    }
    for key, reason in (("issue_median_hours", "本课程数据包不含 Issue 事件"),
                        ("pr_median_hours", "周级 PR 数量不包含合并耗时事件"),
                        ("release_interval_days", "本课程数据包不含 Release 事件")):
        metric_quality[key] = {"valid_samples": 0, "missing_count": len(rows),
                               "missing_rate": 1.0 if rows else None, "status_counts": {"missing": len(rows)},
                               "missing_reasons": [{"reason": reason, "count": len(rows)}] if rows else []}
    course_summary = {
        "data_as_of": source.get("data_as_of"),
        "observation_window": source.get("observation_window"),
        "weekly_records": source.get("weekly_records", 0),
        "repositories_with_12_complete_commit_weeks": source.get("repositories_with_12_complete_commit_weeks", 0),
        "split_counts": source.get("split_counts", {"train": 0, "test": 0}),
        "coverage": source.get("coverage", {}),
    }
    return {
        "dataset_id": dataset_id, "analysis_mode": "course",
        "dataset_status": "analyzable" if rows else "awaiting_collection",
        "population_scope": "course_research_historical_snapshot", "is_probability_sample": False,
        "dataset_version": source.get("version") or dataset.rules_version,
        "frozen_at": iso_z(dataset.frozen_at), "sample_size": len(rows), "analyzable_members": eligible_count,
        "source": source.get("source") or dataset.description,
        "metric_version": "course-research-300-v1", "summary": summary, "metric_quality": metric_quality,
        "groups": groups, "rows": rows,
        "correlation": {"n": 0, "coefficient": None, "p_value": None, "note": "课程数据仅含周级提交聚合，不含 Issue / PR 耗时配对事件"},
        "course_summary": course_summary,
        "limitations": [
            "这是固定历史快照，不是实时仓库状态；若存在更新的在线采集，仓库分析使用更新数据。",
            "提交趋势模型只输出未来四周类别；M1 反映提交模式，M3 是 MAD 统计提示。",
            "train/test 标签仅说明本次历史回测角色；测试组不是全新外部样本。",
            "数据包不包含 Issue / PR 合并耗时或 Release 事件，因此这些指标明确显示缺失。",
        ],
    }
