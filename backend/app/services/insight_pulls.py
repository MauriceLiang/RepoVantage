"""insight pulls domain queries."""

import json
import math
from datetime import datetime, timedelta, timezone
from sqlalchemy import desc, select
from backend.app.core.clock import iso_z, parse_github_datetime
from backend.app.core.exceptions import AppError
from backend.app.persistence.models import Repository, RepositoryActivityEvent, RepositoryInsightRun
from backend.app.pipeline.collection_archive import iter_module_pages
from backend.app.pipeline.raw_archive import read_archive

from backend.app.services.insight_record_helpers import _select_insight_run, _archive_sources, _online_comments, METRIC_VERSION


def repository_pull_requests(session, repository_id, search=None, *, include_body=False, merged_from=None, merged_to=None, window_days=None):
    """返回最新分析归档中保存的已关闭 Pull Request。"""
    # 图表点选传入 UTC 左闭右开区间；兼容未带时区的查询值并统一成 UTC。
    merged_from = merged_from.replace(tzinfo=timezone.utc) if merged_from and merged_from.tzinfo is None else merged_from
    merged_to = merged_to.replace(tzinfo=timezone.utc) if merged_to and merged_to.tzinfo is None else merged_to
    merged_from = merged_from.astimezone(timezone.utc) if merged_from else None
    merged_to = merged_to.astimezone(timezone.utc) if merged_to else None
    if merged_from and merged_to and merged_from >= merged_to:
        raise AppError(422, "VALIDATION_ERROR", "PR 合并时间筛选的结束时间必须晚于开始时间")
    if window_days is not None and window_days not in {30, 90, 180}:
        raise AppError(422, "VALIDATION_ERROR", "分析范围只支持 30、90 或 180 天")

    repository = session.get(Repository, repository_id)
    if repository is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "本地仓库不存在")
    runs = session.scalars(select(RepositoryInsightRun).where(
        RepositoryInsightRun.repository_id == repository_id, RepositoryInsightRun.metric_version == METRIC_VERSION,
    ).order_by(desc(RepositoryInsightRun.analyzed_at), desc(RepositoryInsightRun.run_id))).all()
    run = _select_insight_run(runs, window_days)
    from backend.app.services.course_test_events import historical_records, prefer_historical
    if prefer_historical(session, repository_id, window_days or 90, run):
        historical = historical_records(session, repository_id, "pulls", window_days=window_days, search=search,
                                        include_body=include_body, merged_from=merged_from, merged_to=merged_to)
        if historical is not None:
            return historical
    if run is None:
        return {
            "available": False, "coverage": {"state": "missing", "label": "尚无逐条数据", "detail": "请先采集深度活动数据"},
            "note": "尚无可读取的 Pull Request 采集归档。", "window_start": None, "window_end": None, "items": [],
        }

    task_ids, archive_paths, module_coverage = _archive_sources(run, "pulls", "PULL_REQUEST_ARCHIVE_UNAVAILABLE", "Pull Request")

    scope_end = run.window_end
    scope_start = scope_end - timedelta(days=window_days) if window_days is not None else run.window_start
    events = session.scalars(select(RepositoryActivityEvent).where(
        RepositoryActivityEvent.repository_id == repository_id,
        RepositoryActivityEvent.event_type == "pull_request",
        RepositoryActivityEvent.source_task_id.in_(task_ids) if task_ids else RepositoryActivityEvent.source_task_id == "",
        RepositoryActivityEvent.closed_at.is_not(None),
        RepositoryActivityEvent.closed_at >= scope_start,
        RepositoryActivityEvent.closed_at < scope_end,
    )).all()
    event_by_id = {event.source_item_id: event for event in events}

    archive_found = False
    missing_archive = False
    pull_data_found = False
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
            pull_archive = archive.get("pulls")
            if pull_archive is None:
                continue
            pull_data_found = True
            for page in iter_module_pages(pull_archive):
                if len(page) > 1000:
                    raise ValueError("invalid pull request archive page")
                for raw_item in page:
                    identifier = raw_item.get("id")
                    if type(identifier) is not int or str(identifier) not in event_by_id:
                        continue
                    number = raw_item.get("number")
                    if type(number) is not int or number <= 0:
                        continue
                    event = event_by_id[str(identifier)]
                    created_at, closed_at, merged_at = event.created_at, event.closed_at, event.merged_at
                    duration_days = (merged_at - created_at).total_seconds() / 86400 if created_at and merged_at else None
                    item = {
                        "number": number,
                        "title": raw_item.get("title") if isinstance(raw_item.get("title"), str) else "（无标题）",
                        "created_at": iso_z(created_at),
                        "closed_at": iso_z(closed_at),
                        "merged_at": iso_z(merged_at),
                        "duration_days": round(duration_days, 1) if duration_days is not None and math.isfinite(duration_days) and duration_days >= 0 else None,
                        "state": "merged" if merged_at else "closed",
                        "draft": raw_item.get("draft") is True,
                        "comments_count": raw_item.get("comments") if type(raw_item.get("comments")) is int and raw_item.get("comments") >= 0 else 0,
                        "url": f"https://github.com/{repository.full_name}/pull/{number}",
                        "_sort_at": merged_at or closed_at,
                    }
                    if include_body:
                        item["body"] = raw_item.get("body") if isinstance(raw_item.get("body"), str) else None
                    items_by_id[str(identifier)] = item
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise AppError(503, "PULL_REQUEST_ARCHIVE_UNAVAILABLE", "Pull Request 采集归档损坏或不可读取，请重新采集仓库数据") from exc

    coverage_state = "partial" if module_coverage == "budget_exhausted" else module_coverage if module_coverage in {"complete", "partial"} else "missing"
    if not archive_found or not pull_data_found:
        coverage_state = "missing"
    elif missing_archive:
        coverage_state = "partial"
    coverage_labels = {"complete": "采集完整", "partial": "部分采集", "missing": "暂无逐条数据"}
    coverage_details = {
        "complete": "仅代表本次采集窗口和已设置的分页范围完整",
        "partial": "本次采集未覆盖全部 Pull Request 分页，列表可能不完整",
        "missing": "当前没有可读取的 Pull Request 归档，请重新采集深度活动数据",
    }
    available = pull_data_found and archive_found
    rows = list(items_by_id.values())
    rows.sort(key=lambda row: (row["_sort_at"] or datetime.min, row["number"]), reverse=True)
    if merged_from or merged_to:
        # 只有已合并 PR 才属于耗时分布图的样本；关闭未合并 PR 不应混入筛选结果。
        rows = [
            row for row in rows
            if row["merged_at"] is not None and row["duration_days"] is not None
            and (merged_at := parse_github_datetime(row["merged_at"])) is not None
            and (merged_from is None or merged_at >= merged_from.replace(tzinfo=None))
            and (merged_to is None or merged_at < merged_to.replace(tzinfo=None))
        ]
    normalized_search = (search or "").strip().casefold()
    if normalized_search:
        rows = [row for row in rows if normalized_search in row["title"].casefold() or normalized_search in str(row["number"])]
    for row in rows:
        row.pop("_sort_at", None)
    if not available:
        note = "当前采集没有可读取的 Pull Request 逐条归档，请重新采集深度活动数据。"
    else:
        note = "仅展示本次采集窗口内已关闭的 PR（包含已合并和关闭未合并）；Open PR 和未采集历史不会补造。"
        if coverage_state == "partial" or missing_archive:
            note = "部分采集归档缺失或未覆盖完整设置范围，当前 PR 列表可能不完整。"
    return {
        "available": available,
        "coverage": {"state": coverage_state, "label": coverage_labels[coverage_state], "detail": coverage_details[coverage_state]},
        "note": note,
        "window_start": iso_z(scope_start),
        "window_end": iso_z(scope_end),
        "items": rows,
    }


def repository_pull_request_chart_data(session, repository_id, *, window_days=None):
    """为 PR 图表一次读取精简样本，避免分页请求重复扫描相同归档。"""
    result = repository_pull_requests(session, repository_id, window_days=window_days)
    records = result["items"]
    items = [
        {
            "merged_at": row["merged_at"],
            "duration_days": row["duration_days"],
            "state": row["state"],
            "comments_count": row["comments_count"],
        }
        for row in records[:1000]
    ]
    return {
        "available": result["available"],
        "coverage": result["coverage"],
        "note": result["note"],
        "window_start": result["window_start"],
        "window_end": result["window_end"],
        "items": items,
        "page_items": records[:10],
        "total": len(records),
        "complete": len(items) >= len(records),
    }


def repository_pull_request_detail(session, repository_id, pull_number):
    result = repository_pull_requests(session, repository_id, include_body=True)
    for item in result["items"]:
        if item["number"] == pull_number:
            return {key: item[key] for key in ("number", "title", "created_at", "closed_at", "merged_at", "duration_days", "state", "draft", "comments_count", "url", "body")}
    from backend.app.services.course_test_events import historical_records
    historical = historical_records(session, repository_id, "pulls", window_days=180, include_body=True)
    if historical:
        for item in historical["items"]:
            if item["number"] == pull_number:
                return item
    if not result["available"]:
        raise AppError(409, "PULL_REQUEST_ARCHIVE_UNAVAILABLE", result["note"])
    raise AppError(404, "RESOURCE_NOT_FOUND", "本次采集归档中没有该 Pull Request")



def repository_pull_request_online_detail(session, repository_id, pull_number, github):
    repository_pull_request_detail(session, repository_id, pull_number)
    repository = session.get(Repository, repository_id)
    raw_pull = github.get_pull_request_detail(repository.full_name, pull_number)
    raw_user = raw_pull.get("user") if isinstance(raw_pull.get("user"), dict) else {}
    raw_labels = raw_pull.get("labels") if isinstance(raw_pull.get("labels"), list) else []
    labels = [label["name"] for label in raw_labels if isinstance(label, dict) and isinstance(label.get("name"), str)]
    comment_count = raw_pull.get("comments") if type(raw_pull.get("comments")) is int and raw_pull.get("comments") >= 0 else 0
    comments, comments_complete, comments_error = _online_comments(
        comment_count, lambda: github.list_pull_request_comments_detailed(repository.full_name, pull_number), "Pull Request"
    )

    merged_at = raw_pull.get("merged_at") if isinstance(raw_pull.get("merged_at"), str) else None
    raw_state = raw_pull.get("state")
    state = "merged" if merged_at else raw_state if raw_state in {"open", "closed"} else "closed"
    return {
        "number": pull_number,
        "title": raw_pull.get("title") if isinstance(raw_pull.get("title"), str) else "（无标题）",
        "body": raw_pull.get("body") if isinstance(raw_pull.get("body"), str) else None,
        "state": state,
        "author": raw_user.get("login") if isinstance(raw_user.get("login"), str) else None,
        "labels": labels,
        "created_at": raw_pull.get("created_at") if isinstance(raw_pull.get("created_at"), str) else None,
        "closed_at": raw_pull.get("closed_at") if isinstance(raw_pull.get("closed_at"), str) else None,
        "merged_at": merged_at,
        "updated_at": raw_pull.get("updated_at") if isinstance(raw_pull.get("updated_at"), str) else None,
        "url": raw_pull.get("html_url") if isinstance(raw_pull.get("html_url"), str) else f"https://github.com/{repository.full_name}/pull/{pull_number}",
        "comments_count": comment_count,
        "comments": comments,
        "comments_complete": comments_complete,
        "comments_error": comments_error,
    }


