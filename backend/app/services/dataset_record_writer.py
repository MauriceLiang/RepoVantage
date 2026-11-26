"""Persist a validated dataset bundle in a single controlled database operation."""

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
    Repository,
    RepositoryActivityEvent,
    RepositoryInsightRun,
    RepositorySnapshot,
)
from backend.app.services.repositories import FEATURED_ID, LIBRARY_ID, repository_from_github

from backend.app.services.dataset_import_common import MODULES, BundleError, _positive_int, _nonnegative_int, _json_object


def _import_records(
    session: Session,
    metadata: dict[str, Any],
    records: dict[str, list[dict[str, Any]]],
    bundle_hash: str,
    *,
    task_id: str | None = None,
    worker_id: str | None = None,
    attempt: int | None = None,
    archive_paths: dict[int, str] | None = None,
) -> dict[str, int]:
    now = utc_now()
    source_task_id = task_id or f"bundle-{metadata['version']}-{bundle_hash[:12]}"
    begin_immediate(session)
    try:
        dataset = session.get(Dataset, FEATURED_ID)
        if dataset is not None:
            source_meta = _json_object(dataset.source_metadata_json)
            existing_hash = source_meta.get("bundle_hash")
            if existing_hash and existing_hash != bundle_hash:
                raise AppError(409, "DATASET_VERSION_CONFLICT", "featured-default 已导入其他数据包版本；请使用新的数据集版本")
            if dataset.type != "featured":
                raise AppError(409, "DATASET_VERSION_CONFLICT", "featured-default 已被其他数据集类型占用")
        if dataset is None:
            dataset = Dataset(dataset_id=FEATURED_ID, name="首页精选", type="featured", rules_version=metadata["version"], description="随项目分发的真实公开仓库精选数据")
            session.add(dataset)
            session.flush()
        library = session.get(Dataset, LIBRARY_ID)
        if library is None:
            library = Dataset(dataset_id=LIBRARY_ID, name="我的仓库", type="library", description="仅包含用户主动导入或添加的仓库")
            session.add(library)
            session.flush()
        dataset.rules_version = metadata["version"]
        dataset.frozen_at = parse_github_datetime(metadata["data_as_of"])
        dataset.source_metadata_json = json.dumps({
            "version": metadata["version"],
            "bundle_hash": bundle_hash,
            "complete": True,
            "data_as_of": metadata["data_as_of"],
            "schema_version": metadata["schema_version"],
            "imported_at": iso_z(now),
        }, ensure_ascii=False)

        repo_rows = {_positive_int(row["repository_id"]): row for row in records["repositories"]}
        membership_by_repo = {
            _positive_int(row["repository_id"]): row
            for row in records["memberships"]
        }
        for repository_id, row in repo_rows.items():
            by_id = session.get(Repository, repository_id)
            by_name = session.scalar(select(Repository).where(Repository.full_name == row["full_name"]))
            if by_id and by_id.full_name.casefold() != row["full_name"].casefold() or by_name and by_name.repository_id != repository_id:
                raise AppError(409, "DATASET_REPOSITORY_CONFLICT", f"仓库身份与本地记录冲突: {row['full_name']}")
            incoming_seen = parse_github_datetime(row.get("last_seen_at")) or parse_github_datetime(metadata["data_as_of"]) or now
            repo = by_id or by_name
            if repo is None or incoming_seen >= repo.last_seen_at:
                repo = repository_from_github(session, _repository_payload(row))
                repo.first_seen_at = parse_github_datetime(row.get("first_seen_at")) or repo.first_seen_at
                repo.last_seen_at = incoming_seen
        session.flush()

        counts = {"imported_count": 0, "already_present_count": 0, "snapshot_count": 0, "event_count": 0, "warning_count": 0, "skipped_count": 0}
        for repository_id in repo_rows:
            member = session.get(DatasetRepository, (FEATURED_ID, repository_id))
            if member is None:
                source_member = membership_by_repo[repository_id]
                session.add(DatasetRepository(
                    dataset_id=FEATURED_ID,
                    repository_id=repository_id,
                    added_at=parse_github_datetime(source_member.get("added_at")) or now,
                    selection_tier=source_member.get("selection_tier"),
                    inclusion_reason=source_member.get("inclusion_reason"),
                    selection_source="featured bundle v1",
                ))
                counts["imported_count"] += 1
            else:
                counts["already_present_count"] += 1

        for row in records["snapshots"]:
            repository_id = _positive_int(row["repository_id"])
            collected_at = parse_github_datetime(row.get("collected_at"))
            if collected_at is None:
                raise BundleError("快照 collected_at 无效")
            latest = session.scalar(select(RepositorySnapshot).where(RepositorySnapshot.repository_id == repository_id, RepositorySnapshot.valid.is_(True)).order_by(desc(RepositorySnapshot.collected_at), desc(RepositorySnapshot.id)).limit(1))
            if latest and latest.collected_at >= collected_at:
                counts["skipped_count"] += 1
                continue
            session.add(RepositorySnapshot(
                repository_id=repository_id,
                collected_at=collected_at,
                stars=_nonnegative_int(row.get("stars")),
                forks=_nonnegative_int(row.get("forks")),
                open_issues_and_pr_count=_nonnegative_int(row.get("open_issues_and_pr_count")),
                pushed_at=parse_github_datetime(row.get("pushed_at")),
                github_updated_at=parse_github_datetime(row.get("github_updated_at")),
                response_etag=row.get("response_etag") if isinstance(row.get("response_etag"), str) else None,
                source_http_status=row.get("source_http_status") if type(row.get("source_http_status")) is int else 200,
                source_archive_path=None,
                valid=True,
            ))
            counts["snapshot_count"] += 1

        _import_events(session, records, source_task_id, counts, now)
        _import_analysis(session, records["analysis"], counts)
        _import_coverage(session, records["coverage"], counts)
        _import_insights(session, records, source_task_id, counts, now, archive_paths)
        if len(records["analysis"]) < len(repo_rows) or len(records["insights"]) < len(repo_rows) or len(records["coverage"]) < len(repo_rows):
            counts["warning_count"] += 1
        if task_id:
            job = session.get(DatasetImportJob, task_id)
            if (
                job is None
                or job.status != "running"
                or worker_id is not None and job.lease_owner != worker_id
                or attempt is not None and job.attempt != attempt
                or job.lease_until is None
                or job.lease_until <= now
            ):
                raise AppError(409, "DATASET_IMPORT_TASK_STALE", "导入任务已失去执行权，不能提交数据")
            job.status = "succeeded"
            job.phase = None
            job.progress_kind = "records"
            job.progress_percent = 100
            job.processed_records = job.total_records or job.processed_records
            job.current_file = None
            job.message = "精选数据导入完成"
            job.result_json = json.dumps(counts, ensure_ascii=False)
            job.error_code = None
            job.error_message = None
            job.updated_at = now
            job.finished_at = now
            job.heartbeat_at = now
            job.lease_owner = None
            job.lease_until = None
            session.execute(delete(DatasetImportStagingRecord).where(DatasetImportStagingRecord.task_id == task_id))
        session.commit()
        return counts
    except Exception:
        session.rollback()
        raise


def _import_events(session: Session, records, source_task_id: str, counts: dict[str, int], now) -> None:
    types = {"commits": "commit", "issues": "issue", "pulls": "pull_request", "releases": "release"}
    fields = ("event_at", "created_at", "closed_at", "merged_at", "published_at", "updated_at", "first_seen_at", "last_seen_at")
    for module in MODULES:
        rows = records[f"events/{module}"]
        for offset in range(0, len(rows), 500):
            batch = rows[offset:offset + 500]
            identity_keys = []
            for row in batch:
                repository_id = _positive_int(row.get("repository_id"))
                item_id = row.get("source_item_id")
                if repository_id is None or not isinstance(item_id, str) or not item_id or len(item_id) > 64 or row.get("event_type") != types[module]:
                    raise BundleError(f"events/{module} 包含无效事件 ID 或类型")
                identity_keys.append((repository_id, item_id))
            key_set = set(identity_keys)
            existing_rows = session.scalars(
                select(RepositoryActivityEvent).where(
                    RepositoryActivityEvent.event_type == types[module],
                    tuple_(RepositoryActivityEvent.repository_id, RepositoryActivityEvent.source_item_id).in_(identity_keys),
                )
            ).all() if identity_keys else []
            existing_by_key = {
                (event.repository_id, event.source_item_id): event
                for event in existing_rows
                if (event.repository_id, event.source_item_id) in key_set
            }
            new_events = []
            for row in batch:
                repository_id = _positive_int(row.get("repository_id"))
                item_id = row["source_item_id"]
                event = existing_by_key.get((repository_id, item_id))
                incoming_last_seen = parse_github_datetime(row.get("last_seen_at")) or now
                if event and event.last_seen_at >= incoming_last_seen:
                    counts["skipped_count"] += 1
                    continue
                values = {name: parse_github_datetime(row.get(name)) for name in fields}
                values.update({
                    "repository_id": repository_id,
                    "event_type": types[module],
                    "source_item_id": item_id,
                    "author_key": row.get("author_key") if isinstance(row.get("author_key"), str) else None,
                    "is_draft": row.get("is_draft") if type(row.get("is_draft")) is bool else None,
                    "is_prerelease": row.get("is_prerelease") if type(row.get("is_prerelease")) is bool else None,
                    "source_task_id": source_task_id,
                })
                if event:
                    for key, value in values.items():
                        setattr(event, key, value)
                else:
                    new_events.append(RepositoryActivityEvent(**values))
                counts["event_count"] += 1
            if new_events:
                session.add_all(new_events)
            session.flush()


def _import_analysis(session: Session, rows: list[dict], counts: dict[str, int]) -> None:
    for row in rows:
        repository_id = _positive_int(row.get("repository_id"))
        source_collected_at = parse_github_datetime(row.get("source_collected_at"))
        kind = row.get("analysis_kind")
        if source_collected_at is None or kind not in {"basic", "deep"} or not isinstance(row.get("metrics"), dict):
            raise BundleError("analysis.jsonl.gz 包含无效分析记录")
        existing = session.scalar(select(AnalysisResult).where(AnalysisResult.repository_id == repository_id, AnalysisResult.analysis_kind == kind, AnalysisResult.source_collected_at == source_collected_at).limit(1))
        latest = session.scalar(select(AnalysisResult).where(AnalysisResult.repository_id == repository_id, AnalysisResult.analysis_kind == kind).order_by(desc(AnalysisResult.source_collected_at)).limit(1))
        if existing or (latest and latest.source_collected_at > source_collected_at):
            counts["skipped_count"] += 1
            continue
        session.add(AnalysisResult(
            repository_id=repository_id,
            analysis_kind=kind,
            metric_version=str(row.get("metric_version") or "metrics-v1")[:50],
            window_start=parse_github_datetime(row.get("window_start")),
            window_end=parse_github_datetime(row.get("window_end")),
            source_collected_at=source_collected_at,
            calculated_at=parse_github_datetime(row.get("calculated_at")) or source_collected_at,
            coverage=row.get("coverage") if row.get("coverage") in {"complete", "partial"} else "partial",
            metrics_json=json.dumps(row["metrics"], ensure_ascii=False),
            limitations_json=json.dumps(row.get("limitations") if isinstance(row.get("limitations"), list) else [], ensure_ascii=False),
            valid_sample_size=_nonnegative_int(row.get("valid_sample_size")),
        ))


def _import_coverage(session: Session, rows: list[dict], counts: dict[str, int]) -> None:
    for row in rows:
        repository_id = _positive_int(row.get("repository_id"))
        collected_at = parse_github_datetime(row.get("collected_at"))
        start = parse_github_datetime(row.get("window_start"))
        end = parse_github_datetime(row.get("window_end"))
        if collected_at is None or start is None or end is None or start >= end:
            raise BundleError("coverage.jsonl.gz 包含无效时间窗口")
        existing = session.scalar(select(ActivityWindow).where(ActivityWindow.repository_id == repository_id, ActivityWindow.depth == "deep", ActivityWindow.window_start == start, ActivityWindow.window_end == end, ActivityWindow.collected_at == collected_at).limit(1))
        if existing:
            counts["skipped_count"] += 1
            continue
        latest = session.scalar(select(ActivityWindow).where(ActivityWindow.repository_id == repository_id).order_by(desc(ActivityWindow.collected_at)).limit(1))
        if latest and latest.collected_at > collected_at:
            counts["skipped_count"] += 1
            continue
        module_coverage = row.get("modules") if isinstance(row.get("modules"), dict) else {}
        session.add(ActivityWindow(
            repository_id=repository_id,
            depth="deep",
            window_start=start,
            window_end=end,
            commits_count=_nonnegative_int(row.get("commits_count")),
            issues_opened_count=_nonnegative_int(row.get("issues_opened_count")),
            issues_closed_count=_nonnegative_int(row.get("issues_closed_count")),
            pulls_opened_count=_nonnegative_int(row.get("pulls_opened_count")),
            pulls_merged_count=_nonnegative_int(row.get("pulls_merged_count")),
            releases_count=_nonnegative_int(row.get("releases_count")),
            coverage=row.get("coverage") if row.get("coverage") in {"complete", "partial"} else "partial",
            collected_at=collected_at,
            details_json=json.dumps({"coverage_by_module": module_coverage}, ensure_ascii=False),
            source_archive_path=None,
        ))


def _import_insights(
    session: Session,
    records,
    source_task_id: str,
    counts: dict[str, int],
    now,
    archive_paths: dict[int, str] | None = None,
) -> None:
    repository_reader = getattr(records, "for_repository", None)
    details_by_repo: dict[int, dict[str, list[dict]]] | None = None
    if not callable(repository_reader):
        details_by_repo = {}
        for module in MODULES:
            for detail in records[f"details/{module}"]:
                repository_id = _positive_int(detail.get("repository_id"))
                if repository_id is None or not isinstance(detail.get("item"), dict):
                    raise BundleError("详情归档记录无效")
                details_by_repo.setdefault(repository_id, {name: [] for name in MODULES})[module].append(detail["item"])

    for row in records["insights"]:
        repository_id = _positive_int(row["repository_id"])
        analyzed_at = parse_github_datetime(row.get("analyzed_at"))
        start = parse_github_datetime(row.get("window_start"))
        end = parse_github_datetime(row.get("window_end"))
        if analyzed_at is None or start is None or end is None or start >= end:
            raise BundleError("insights.jsonl.gz 包含无效分析窗口")
        fingerprint = hashlib.sha256(f"{FEATURED_ID}:{row.get('metric_version')}:{repository_id}:{analyzed_at.isoformat()}:{row.get('window_end')}".encode()).hexdigest()
        if session.get(RepositoryInsightRun, str(uuid.uuid5(uuid.NAMESPACE_URL, fingerprint))) or session.scalar(select(RepositoryInsightRun.run_id).where(RepositoryInsightRun.input_fingerprint == fingerprint).limit(1)):
            counts["skipped_count"] += 1
            continue
        if callable(repository_reader):
            details = {}
            for module in MODULES:
                detail_rows = repository_reader(f"details/{module}", repository_id)
                details[module] = []
                for detail in detail_rows:
                    if _positive_int(detail.get("repository_id")) != repository_id or not isinstance(detail.get("item"), dict):
                        raise BundleError("详情归档记录无效")
                    details[module].append(detail["item"])
        else:
            details = (details_by_repo or {}).get(repository_id, {name: [] for name in MODULES})
        sources = row.get("sources") if isinstance(row.get("sources"), dict) else {}
        safe_archive = {module: {"pages": [details[module]]} for module in MODULES}
        safe_archive["_meta"] = {"schema_version": 2, "sources": sources, "window_start": iso_z(start), "window_end": iso_z(end)}
        from backend.app.pipeline.raw_archive import archive_json

        archive_path = (archive_paths or {}).get(repository_id)
        if archive_path is None:
            archive_path = archive_json(repository_id, source_task_id, "activity", safe_archive)
        run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, fingerprint))
        result_json = row.get("result") if isinstance(row.get("result"), dict) else {}
        result_json = dict(result_json)
        result_json.update({"repository_id": repository_id, "run_id": run_id, "analyzed_at": iso_z(analyzed_at), "source_task_ids": [source_task_id], "source_archive_paths": [archive_path], "origin": "featured_bundle_import", "sources": sources})
        module_coverage = row.get("module_coverage") if isinstance(row.get("module_coverage"), dict) else sources
        session.add(RepositoryInsightRun(
            run_id=run_id,
            input_fingerprint=fingerprint,
            repository_id=repository_id,
            metric_version=str(row.get("metric_version") or "insights-v1")[:50],
            window_start=start,
            window_end=end,
            analyzed_at=analyzed_at,
            source_task_ids_json=json.dumps([source_task_id]),
            source_archive_paths_json=json.dumps([archive_path]),
            module_coverage_json=json.dumps(module_coverage, ensure_ascii=False),
            status=row.get("status") if row.get("status") in {"ready", "partial", "failed"} else "partial",
            limitations_json=json.dumps(row.get("limitations") if isinstance(row.get("limitations"), list) else [], ensure_ascii=False),
            result_json=json.dumps(result_json, ensure_ascii=False),
        ))


def _repository_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("repository_id"),
        "full_name": row.get("full_name"),
        "html_url": row.get("html_url"),
        "description": row.get("description"),
        "language": row.get("language"),
        "topics": row.get("topics") if isinstance(row.get("topics"), list) else [],
        "license": {"spdx_id": row.get("license_spdx")} if row.get("license_spdx") else None,
        "created_at": row.get("created_at"),
        "pushed_at": row.get("pushed_at"),
        "updated_at": row.get("github_updated_at"),
        "archived": row.get("archived") is True,
        "fork": row.get("is_fork") is True,
        "private": False,
        "size": row.get("size_kb"),
    }

