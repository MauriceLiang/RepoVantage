import hashlib
import json
import math
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4

from sqlalchemy import desc, or_, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from backend.app.analytics.insights import LIMITATIONS, calculate_insights
from backend.app.analytics.chart_data import build_chart_data
from backend.app.core.clock import iso_z, parse_github_datetime, utc_now
from backend.app.core.exceptions import AppError
from backend.app.persistence.models import Repository, RepositoryActivityEvent, RepositoryInsightRun
from backend.app.pipeline.collection_archive import iter_module_pages, iter_module_records
from backend.app.pipeline.event_normalizer import normalize_events
from backend.app.pipeline.raw_archive import read_archive
from backend.app.services.insight_record_helpers import METRIC_VERSION, _select_insight_run

from backend.app.services.insight_commits import repository_commit_activity
from backend.app.services.insight_issues import (
    repository_closed_issues, repository_closed_issue_chart_data,
    repository_closed_issue_detail, repository_closed_issue_online_detail,
)
from backend.app.services.insight_pulls import (
    repository_pull_requests, repository_pull_request_chart_data,
    repository_pull_request_detail, repository_pull_request_online_detail,
)
from backend.app.services.insight_releases import repository_release_detail

METRIC_VERSION = "insights-v1"
MODULES = ("commits", "issues", "pulls", "releases")
PAGE_LIMIT_NOTE = "已达到用户设置的接口页数预算；仍有后续页未采集，当前指标只反映已观察样本。"


def _insight_status(metrics: dict) -> str:
    """汇总模块覆盖状态；样本不足不等同于采集缺失或失败。"""
    states = {metric["quality"]["status"] for metric in metrics.values()}
    if not states or states == {"missing"}:
        return "missing"
    if states & {"partial", "missing", "failed"}:
        return "partial"
    return "ready"


def persist_insights(session: Session, repository_id: int, task_id: str, rows: dict, sources: dict, start, end, archive_paths: list[str], *, normalized_event_counts: dict | None = None, aggregate_from_store=False, version=METRIC_VERSION, origin="collection"):
    normalized, checked_sources = {}, {}
    for module in MODULES:
        if normalized_event_counts is None:
            normalized[module], counts = normalize_events(module, rows.get(module, []))
        else:
            normalized[module] = rows.get(module, [])
            counts = normalized_event_counts[module]
        source = {**sources.get(module, {"coverage": "not_collected"}), **counts}
        if (counts["rejected_records"] or counts["invalid_event_times"]) and source["coverage"] == "complete":
            source["coverage"] = "partial"
            source["error_code"] = "INVALID_EVENT_RECORDS"
        checked_sources[module] = source
    fingerprint_payload = json.dumps({"repository": repository_id, "task": task_id, "version": version, "start": iso_z(start), "end": iso_z(end), "events": normalized, "sources": checked_sources, "archives": archive_paths}, default=iso_z, sort_keys=True)
    fingerprint = hashlib.sha256(fingerprint_payload.encode()).hexdigest()
    existing = session.scalar(select(RepositoryInsightRun).where(RepositoryInsightRun.input_fingerprint == fingerprint))
    if existing:
        return json.loads(existing.result_json)
    now = utc_now()
    # 事件和分析运行在调用方的同一事务内保存。普通任务使用本次输入计算；
    # 增量采集或历史回填则在下方写入事件后，明确从本地去重事件库重新计算。
    for events in normalized.values():
        for offset in range(0, len(events), 250):
            batch = [{**e, "repository_id": repository_id, "source_task_id": task_id, "first_seen_at": now, "last_seen_at": now} for e in events[offset:offset + 250]]
            if batch:
                statement = insert(RepositoryActivityEvent).values(batch)
                mutable = {key: getattr(statement.excluded, key) for key in batch[0] if key not in {"repository_id", "event_type", "source_item_id", "first_seen_at"}}
                session.execute(statement.on_conflict_do_update(index_elements=["repository_id", "event_type", "source_item_id"], set_=mutable))
    source_task_ids = [task_id]
    if aggregate_from_store:
        normalized = _stored_window_events(session, repository_id, start, end)
        prior_runs = session.scalars(select(RepositoryInsightRun).where(
            RepositoryInsightRun.repository_id == repository_id,
            RepositoryInsightRun.metric_version == version,
            RepositoryInsightRun.window_end >= start,
            RepositoryInsightRun.window_start <= end,
        )).all()
        for prior in prior_runs:
            try:
                prior_task_ids = json.loads(prior.source_task_ids_json)
                prior_archives = json.loads(prior.source_archive_paths_json)
            except (TypeError, ValueError):
                continue
            if isinstance(prior_task_ids, list):
                source_task_ids.extend(item for item in prior_task_ids if isinstance(item, str))
            if isinstance(prior_archives, list):
                archive_paths.extend(item for item in prior_archives if isinstance(item, str))
        source_task_ids = list(dict.fromkeys(source_task_ids))
        archive_paths = list(dict.fromkeys(archive_paths))
        for source in checked_sources.values():
            source["calculation_basis"] = "local_unique_event_store"
    metrics = calculate_insights(normalized, checked_sources, start, end)
    status = _insight_status(metrics)
    limitations = list(LIMITATIONS)
    if any(source.get("limit_reached") for source in checked_sources.values()):
        limitations.append(PAGE_LIMIT_NOTE)
    if not archive_paths:
        limitations.append("原始归档不可用；本次统计及事件仍保留，但原始响应的可复核性下降。")
    observed_counts = _observed_event_counts(normalized, start, end)
    result = {"repository_id": repository_id, "run_id": str(uuid4()), "metric_version": version, "status": status, "window_start": iso_z(start), "window_end": iso_z(end), "timezone": "UTC", "analyzed_at": iso_z(now), "source_task_ids": source_task_ids, "source_archive_paths": archive_paths, "origin": origin, "sources": checked_sources, "insights": metrics, "observed_counts": observed_counts, "limitations": limitations}
    session.add(RepositoryInsightRun(run_id=result["run_id"], input_fingerprint=fingerprint, repository_id=repository_id, metric_version=version, window_start=start, window_end=end, analyzed_at=now, source_task_ids_json=json.dumps(source_task_ids), source_archive_paths_json=json.dumps(archive_paths), module_coverage_json=json.dumps(checked_sources), status=status, limitations_json=json.dumps(limitations, ensure_ascii=False), result_json=json.dumps(result, ensure_ascii=False)))
    session.flush()
    return result


def _stored_window_events(session: Session, repository_id: int, start, end) -> dict[str, list[dict]]:
    ranges = {
        "commit": (RepositoryActivityEvent.event_at >= start) & (RepositoryActivityEvent.event_at < end),
        "issue": or_(
            (RepositoryActivityEvent.created_at >= start) & (RepositoryActivityEvent.created_at < end),
            (RepositoryActivityEvent.closed_at >= start) & (RepositoryActivityEvent.closed_at < end),
            (RepositoryActivityEvent.updated_at >= start) & (RepositoryActivityEvent.updated_at < end),
        ),
        "pull_request": or_(
            (RepositoryActivityEvent.created_at >= start) & (RepositoryActivityEvent.created_at < end),
            (RepositoryActivityEvent.closed_at >= start) & (RepositoryActivityEvent.closed_at < end),
            (RepositoryActivityEvent.merged_at >= start) & (RepositoryActivityEvent.merged_at < end),
            (RepositoryActivityEvent.updated_at >= start) & (RepositoryActivityEvent.updated_at < end),
        ),
        # 发布频率图支持回看全部本地已采集版本；下游指标仍自行按 365 天窗口计算。
        "release": RepositoryActivityEvent.published_at < end,
    }
    module_by_type = {"commit": "commits", "issue": "issues", "pull_request": "pulls", "release": "releases"}
    events = {module: [] for module in MODULES}
    for event_type, predicate in ranges.items():
        stored = session.scalars(select(RepositoryActivityEvent).where(
            RepositoryActivityEvent.repository_id == repository_id,
            RepositoryActivityEvent.event_type == event_type,
            predicate,
        )).all()
        module = module_by_type[event_type]
        events[module] = [{
            "event_type": item.event_type,
            "source_item_id": item.source_item_id,
            "source_task_id": item.source_task_id,
            "event_at": item.event_at,
            "created_at": item.created_at,
            "closed_at": item.closed_at,
            "merged_at": item.merged_at,
            "published_at": item.published_at,
            "updated_at": item.updated_at,
            "author_key": item.author_key,
            "is_draft": item.is_draft,
            "is_prerelease": item.is_prerelease,
        } for item in stored]
    return events


def _observed_event_counts(events: dict[str, list[dict]], start, end) -> dict[str, int]:
    release_start = end - timedelta(days=365)

    def count(module, field, lower=start):
        return sum(1 for item in events[module] if item.get(field) is not None and lower <= item[field] < end)

    return {
        "commits_count": count("commits", "event_at"),
        "issues_opened_count": count("issues", "created_at"),
        "issues_closed_count": count("issues", "closed_at"),
        "pulls_opened_count": count("pulls", "created_at"),
        "pulls_merged_count": count("pulls", "merged_at"),
        "releases_count": count("releases", "published_at", release_start),
    }



def _display_commit_accounts(account_keys, archive_paths):
    """用原始 Commit 归档中的 GitHub login 显示稳定的账号 ID。"""
    unresolved = {key for key in account_keys if isinstance(key, str) and key.startswith("github:")}
    labels = {}
    if unresolved:
        for archive_path in archive_paths:
            if not unresolved:
                break
            if not isinstance(archive_path, str):
                continue
            try:
                archive = read_archive(archive_path)
                for page in iter_module_pages(archive.get("commits")):
                    if not unresolved:
                        break
                    for item in page:
                        author = item.get("author") if isinstance(item, dict) else None
                        if not isinstance(author, dict):
                            continue
                        author_id = author.get("id")
                        login = author.get("login")
                        key = f"github:{author_id}" if type(author_id) is int and author_id > 0 else None
                        if key in unresolved and isinstance(login, str) and login.strip():
                            labels[key] = login.strip()
                            unresolved.remove(key)
            except (OSError, ValueError, TypeError, RecursionError):
                # Label lookup is best effort; corrupt or expired archives must not break chart data.
                continue

    def display(key):
        if key in labels:
            return labels[key]
        if isinstance(key, str) and key.startswith("github:"):
            value = key.removeprefix("github:")
            return f"GitHub #{value}" if value.isdigit() else value or "未知账号"
        return key

    return [display(key) for key in account_keys]


def repository_insights(session, repository_id, window_days=90):
    if session.get(Repository, repository_id) is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "本地仓库不存在")
    if window_days is not None and window_days not in {30, 90, 180}:
        raise AppError(422, "VALIDATION_ERROR", "分析范围只支持 30、90 或 180 天")

    runs = session.scalars(select(RepositoryInsightRun).where(
        RepositoryInsightRun.repository_id == repository_id,
        RepositoryInsightRun.metric_version == METRIC_VERSION,
    ).order_by(desc(RepositoryInsightRun.analyzed_at), desc(RepositoryInsightRun.run_id))).all()
    available_days = max(
        (max(0, int((run.window_end - run.window_start).total_seconds() // 86400)) for run in runs),
        default=0,
    )
    run = _select_insight_run(runs, window_days)
    if window_days is not None:
        from backend.app.services.course_test_events import historical_insights, prefer_historical
        if prefer_historical(session, repository_id, window_days, run):
            historical = historical_insights(session, repository_id, window_days)
            if historical is not None:
                return historical
    if run is None:
        reason = (
            f"当前尚无可用的事件级分析数据。请选择快速或完整窗口采集 {window_days or 90} 天范围后重试。"
            if not runs else
            f"当前数据最多覆盖 {available_days} 天，未覆盖所选的 {window_days or 90} 天。请选择快速或完整窗口采集该范围。"
        )
        return {
            "repository_id": repository_id, "run_id": None, "metric_version": METRIC_VERSION,
            "status": "missing", "window_start": None, "window_end": None, "timezone": "UTC",
            "analyzed_at": None,
            "source_task_ids": [], "source_archive_paths": [], "origin": None, "sources": {}, "insights": {},
            "requested_window_days": window_days, "window_available": False,
            "available_window_days": available_days, "window_reason": reason, "limitations": [reason],
            "calculation_basis": "current_local_event_store", "calculated_at": None,
            "event_source_task_ids": [], "observed_counts": {},
        }

    # 研究分析使用已保存的结果及其原始观察窗口。
    if window_days is None:
        return json.loads(run.result_json)

    end = run.window_end
    start = run.window_start if window_days is None else end - timedelta(days=window_days)
    try:
        sources = json.loads(run.module_coverage_json)
        source_task_ids = json.loads(run.source_task_ids_json)
        source_archive_paths = json.loads(run.source_archive_paths_json)
        limitations = json.loads(run.limitations_json)
    except (TypeError, ValueError) as exc:
        raise AppError(503, "INSIGHT_RUN_UNAVAILABLE", "分析运行的来源信息无法读取，请重新采集仓库数据") from exc
    if not isinstance(sources, dict):
        raise AppError(503, "INSIGHT_RUN_UNAVAILABLE", "分析运行缺少模块覆盖信息，请重新采集仓库数据")

    events = _stored_window_events(session, repository_id, start, end)
    metrics = calculate_insights(events, sources, start, end)
    status = _insight_status(metrics)
    result = json.loads(run.result_json)
    chart_data = build_chart_data(events, sources, start, end)
    archive_paths = source_archive_paths if isinstance(source_archive_paths, list) else []
    chart_data["commit_accounts"] = _display_commit_accounts(chart_data["commit_accounts"], archive_paths)
    result.update({
        "status": status,
        "window_start": iso_z(start),
        "window_end": iso_z(end),
        "source_task_ids": source_task_ids if isinstance(source_task_ids, list) else [],
        "source_archive_paths": source_archive_paths if isinstance(source_archive_paths, list) else [],
        "sources": sources,
        "insights": metrics,
        "chart_data": chart_data,
        "requested_window_days": window_days,
        "window_available": True,
        "available_window_days": available_days,
        "window_reason": None,
        "limitations": limitations if isinstance(limitations, list) else list(LIMITATIONS),
        "calculation_basis": "current_local_event_store",
        "calculated_at": iso_z(utc_now()),
        "event_source_task_ids": sorted({item["source_task_id"] for rows in events.values() for item in rows if item["source_task_id"]}),
        "observed_counts": _observed_event_counts(events, start, end),
    })
    return result


def repository_insights_for_window(session, repository_id, start, end, source_result):
    """针对明确且已有覆盖证明的观察窗口，重新计算已保存的事件。"""
    if session.get(Repository, repository_id) is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "本地仓库不存在")
    if start >= end:
        raise AppError(422, "VALIDATION_ERROR", "分析窗口必须晚于开始时间")
    if source_result.get("origin") == "course-test-events-v1":
        from backend.app.services.course_test_events import historical_insights
        historical = historical_insights(session, repository_id, source_result["requested_window_days"], start=start, end=end)
        if historical is None:
            raise AppError(503, "COURSE_TEST_EVENTS_UNAVAILABLE", "历史事件无法覆盖所选比较窗口")
        return historical
    try:
        sources = json.loads(json.dumps(source_result["sources"]))
        limitations = list(source_result.get("limitations", LIMITATIONS))
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError(503, "INSIGHT_RUN_UNAVAILABLE", "分析运行缺少模块覆盖信息，请重新采集仓库数据") from exc
    if not isinstance(sources, dict) or any(module not in sources for module in MODULES):
        raise AppError(503, "INSIGHT_RUN_UNAVAILABLE", "分析运行缺少模块覆盖信息，请重新采集仓库数据")

    release_start = end - timedelta(days=365)
    release_source = sources["releases"]
    requested_interval = release_source.get("requested_interval")
    release_coverage_proven = False
    if isinstance(requested_interval, list) and len(requested_interval) == 2:
        release_coverage_start = parse_github_datetime(requested_interval[0])
        release_coverage_end = parse_github_datetime(requested_interval[1])
        release_coverage_proven = (
            release_coverage_start is not None
            and release_coverage_end is not None
            and release_coverage_start <= release_start
            and release_coverage_end >= end
        )
    if release_source.get("coverage") == "complete" and not release_coverage_proven:
        release_source["coverage"] = "partial"
        release_source["error_code"] = "RELEASE_WINDOW_NOT_COVERED"

    events = _stored_window_events(session, repository_id, start, end)
    metrics = calculate_insights(events, sources, start, end)
    status = _insight_status(metrics)
    result = dict(source_result)
    result.update({
        "status": status,
        "window_start": iso_z(start),
        "window_end": iso_z(end),
        "sources": sources,
        "insights": metrics,
        "calculation_basis": "current_local_event_store_shared_window",
        "calculated_at": iso_z(utc_now()),
        "event_source_task_ids": sorted({item["source_task_id"] for rows in events.values() for item in rows if item.get("source_task_id")}),
        "observed_counts": _observed_event_counts(events, start, end),
        "limitations": limitations,
    })
    return result
