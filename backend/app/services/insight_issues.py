"""insight issues domain queries."""

import json
import math
from datetime import timedelta
from sqlalchemy import desc, select
from backend.app.core.clock import iso_z
from backend.app.core.exceptions import AppError
from backend.app.persistence.models import Repository, RepositoryActivityEvent, RepositoryInsightRun
from backend.app.pipeline.collection_archive import iter_module_pages
from backend.app.pipeline.raw_archive import read_archive

from backend.app.services.insight_record_helpers import _select_insight_run, _archive_sources, _online_comments, METRIC_VERSION


def repository_closed_issues(session, repository_id, search=None, *, include_body=False, window_days=None):
    """从最新分析归档中安全地返回已关闭 Issue 的逐条记录。"""
    repository = session.get(Repository, repository_id)
    if repository is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "本地仓库不存在")
    if window_days is not None and window_days not in {30, 90, 180}:
        raise AppError(422, "VALIDATION_ERROR", "分析范围只支持 30、90 或 180 天")
    runs = session.scalars(select(RepositoryInsightRun).where(
        RepositoryInsightRun.repository_id == repository_id, RepositoryInsightRun.metric_version == METRIC_VERSION,
    ).order_by(desc(RepositoryInsightRun.analyzed_at), desc(RepositoryInsightRun.run_id))).all()
    run = _select_insight_run(runs, window_days)
    from backend.app.services.course_test_events import historical_records, prefer_historical
    if prefer_historical(session, repository_id, window_days or 90, run):
        historical = historical_records(session, repository_id, "issues", window_days=window_days, search=search, include_body=include_body)
        if historical is not None:
            return historical
    if run is None:
        return {
            "available": False, "coverage": {"state": "missing", "label": "尚无逐条数据", "detail": "请先采集深度活动数据"},
            "note": "尚无可读取的 Issue 采集归档。", "window_start": None, "window_end": None, "items": [],
        }

    task_ids, archive_paths, module_coverage = _archive_sources(run, "issues", "ISSUE_ARCHIVE_UNAVAILABLE", "Issue")

    scope_end = run.window_end
    scope_start = scope_end - timedelta(days=window_days) if window_days is not None else run.window_start
    events = session.scalars(select(RepositoryActivityEvent).where(
        RepositoryActivityEvent.repository_id == repository_id,
        RepositoryActivityEvent.event_type == "issue",
        RepositoryActivityEvent.source_task_id.in_(task_ids) if task_ids else RepositoryActivityEvent.source_task_id == "",
        RepositoryActivityEvent.closed_at.is_not(None),
        RepositoryActivityEvent.closed_at >= scope_start,
        RepositoryActivityEvent.closed_at < scope_end,
    )).all()
    event_by_id = {event.source_item_id: event for event in events}

    archive_found = False
    missing_archive = False
    items_by_id = {}
    try:
        for archive_path in archive_paths:
            if not isinstance(archive_path, str):
                continue
            try:
                archive = read_archive(archive_path)
            except FileNotFoundError:
                missing_archive = True
                continue
            archive_found = True
            for page in iter_module_pages(archive.get("issues")):
                if len(page) > 1000:
                    raise ValueError("invalid issue archive page")
                for raw_item in page:
                    if "pull_request" in raw_item:
                        continue
                    identifier = raw_item.get("id")
                    if type(identifier) is not int or str(identifier) not in event_by_id:
                        continue
                    number = raw_item.get("number")
                    if type(number) is not int or number <= 0:
                        continue
                    event = event_by_id[str(identifier)]
                    created_at = event.created_at
                    closed_at = event.closed_at
                    elapsed_days = (closed_at - created_at).total_seconds() / 86400 if created_at else None
                    item = {
                        "number": number,
                        "title": raw_item.get("title") if isinstance(raw_item.get("title"), str) else "（无标题）",
                        "created_at": iso_z(created_at),
                        "closed_at": iso_z(closed_at),
                        "duration_days": round(elapsed_days, 1) if elapsed_days is not None and math.isfinite(elapsed_days) and elapsed_days >= 0 else None,
                        "state": "closed",
                        "url": f"https://github.com/{repository.full_name}/issues/{number}",
                        "_closed_at": closed_at,
                    }
                    if include_body:
                        item["body"] = raw_item.get("body") if isinstance(raw_item.get("body"), str) else None
                        item["comments_count"] = raw_item.get("comments") if type(raw_item.get("comments")) is int and raw_item.get("comments") >= 0 else 0
                    items_by_id[str(identifier)] = item
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise AppError(503, "ISSUE_ARCHIVE_UNAVAILABLE", "Issue 采集归档损坏或不可读取，请重新采集仓库数据") from exc

    coverage_state = "partial" if module_coverage == "budget_exhausted" else module_coverage if module_coverage in {"complete", "partial"} else "missing"
    if not archive_found:
        coverage_state = "missing"
    elif missing_archive:
        coverage_state = "partial" if archive_found else "missing"
    coverage_labels = {"complete": "采集完整", "partial": "部分采集", "missing": "暂无逐条数据"}
    coverage_details = {
        "complete": "仅代表本次采集窗口和已设置的分页范围完整",
        "partial": "本次采集未覆盖全部 Issue 分页，列表可能不完整",
        "missing": "当前没有可读取的 Issue 归档，请重新采集深度活动数据",
    }
    available = archive_found
    if available and not missing_archive and coverage_state == "missing":
        coverage_state = "partial"
    if coverage_state == "missing":
        note = "当前采集没有可读取的 Issue 逐条归档，请重新采集深度活动数据。"
    else:
        note = "仅展示本次采集窗口内已关闭的 Issue；Pull Request 已排除，未采集的历史数据不会补造。"
        if missing_archive:
            note = "部分归档不可读取，当前列表可能不完整；请重新采集深度活动数据。"

    rows = list(items_by_id.values())
    rows.sort(key=lambda row: (row["_closed_at"], row["number"]), reverse=True)
    normalized_search = (search or "").strip().casefold()
    if normalized_search:
        rows = [row for row in rows if normalized_search in row["title"].casefold() or normalized_search in str(row["number"])]
    for row in rows:
        row.pop("_closed_at", None)
    return {
        "available": available,
        "coverage": {"state": coverage_state, "label": coverage_labels[coverage_state], "detail": coverage_details[coverage_state]},
        "note": note,
        "window_start": iso_z(scope_start),
        "window_end": iso_z(scope_end),
        "items": rows,
    }


def repository_closed_issue_chart_data(session, repository_id, *, window_days=None):
    """为 Issue 图表一次返回精简样本，避免前端分页反复扫描同一归档。"""
    result = repository_closed_issues(session, repository_id, window_days=window_days)
    records = result["items"]
    items = [
        {"closed_at": row["closed_at"], "duration_days": row["duration_days"]}
        for row in records[:1000]
    ]
    return {
        "available": result["available"],
        "coverage": result["coverage"],
        "note": result["note"],
        "window_start": result["window_start"],
        "window_end": result["window_end"],
        "items": items,
        "total": len(records),
        "complete": len(items) >= len(records),
    }



def repository_closed_issue_detail(session, repository_id, issue_number):
    result = repository_closed_issues(session, repository_id, include_body=True)
    for item in result["items"]:
        if item["number"] == issue_number:
            return {key: item[key] for key in ("number", "title", "created_at", "closed_at", "duration_days", "state", "url", "body", "comments_count")}
    from backend.app.services.course_test_events import historical_records
    historical = historical_records(session, repository_id, "issues", window_days=180, include_body=True)
    if historical:
        for item in historical["items"]:
            if item["number"] == issue_number:
                return item
    if not result["available"]:
        raise AppError(409, "ISSUE_ARCHIVE_UNAVAILABLE", result["note"])
    raise AppError(404, "RESOURCE_NOT_FOUND", "本次采集归档中没有该已关闭 Issue")


def repository_closed_issue_online_detail(session, repository_id, issue_number, github):
    repository_closed_issue_detail(session, repository_id, issue_number)
    repository = session.get(Repository, repository_id)
    raw_issue = github.get_issue_detail(repository.full_name, issue_number)
    raw_user = raw_issue.get("user") if isinstance(raw_issue.get("user"), dict) else {}
    raw_labels = raw_issue.get("labels") if isinstance(raw_issue.get("labels"), list) else []
    labels = [label["name"] for label in raw_labels if isinstance(label, dict) and isinstance(label.get("name"), str)]
    comment_count = raw_issue.get("comments") if type(raw_issue.get("comments")) is int and raw_issue.get("comments") >= 0 else 0
    comments, comments_complete, comments_error = _online_comments(
        comment_count, lambda: github.list_issue_comments_detailed(repository.full_name, issue_number), "Issue"
    )

    raw_state = raw_issue.get("state")
    return {
        "number": issue_number,
        "title": raw_issue.get("title") if isinstance(raw_issue.get("title"), str) else "（无标题）",
        "body": raw_issue.get("body") if isinstance(raw_issue.get("body"), str) else None,
        "state": raw_state if raw_state in {"open", "closed"} else "closed",
        "author": raw_user.get("login") if isinstance(raw_user.get("login"), str) else None,
        "labels": labels,
        "created_at": raw_issue.get("created_at") if isinstance(raw_issue.get("created_at"), str) else None,
        "closed_at": raw_issue.get("closed_at") if isinstance(raw_issue.get("closed_at"), str) else None,
        "updated_at": raw_issue.get("updated_at") if isinstance(raw_issue.get("updated_at"), str) else None,
        "url": raw_issue.get("html_url") if isinstance(raw_issue.get("html_url"), str) else f"https://github.com/{repository.full_name}/issues/{issue_number}",
        "comments_count": comment_count,
        "comments": comments,
        "comments_complete": comments_complete,
        "comments_error": comments_error,
    }

