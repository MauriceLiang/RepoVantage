"""insight commits domain queries."""

import json
from collections import Counter
from datetime import date, datetime, time, timedelta
from sqlalchemy import desc, select
from backend.app.core.clock import iso_z
from backend.app.core.exceptions import AppError
from backend.app.persistence.models import Repository, RepositoryActivityEvent, RepositoryInsightRun
from backend.app.pipeline.collection_archive import iter_module_pages
from backend.app.pipeline.raw_archive import read_archive

from backend.app.services.insight_record_helpers import _select_insight_run, _archive_sources, METRIC_VERSION


def repository_commit_activity(session, repository_id, *, page=1, per_page=20, search=None, week_start: date | None = None, window_days: int | None = None):
    """从覆盖所选窗口的最新归档返回逐条 Commit 和汇总数据。"""
    repository = session.get(Repository, repository_id)
    if repository is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "本地仓库不存在")
    if window_days is not None and window_days not in {30, 90, 180}:
        raise AppError(422, "VALIDATION_ERROR", "分析范围只支持 30、90 或 180 天")
    runs = session.scalars(select(RepositoryInsightRun).where(
        RepositoryInsightRun.repository_id == repository_id,
        RepositoryInsightRun.metric_version == METRIC_VERSION,
    ).order_by(desc(RepositoryInsightRun.analyzed_at), desc(RepositoryInsightRun.run_id))).all()
    run = _select_insight_run(runs, window_days)
    from backend.app.services.course_test_events import historical_commit_activity, prefer_historical
    if prefer_historical(session, repository_id, window_days or 90, run):
        historical = historical_commit_activity(session, repository_id, page=page, per_page=per_page,
                                                search=search, week_start=week_start, window_days=window_days)
        if historical is not None:
            return historical
    if run is None:
        reason = f"当前没有覆盖所选 {window_days} 天的 Commit 采集归档。" if runs and window_days else "尚无可读取的 Commit 采集归档。"
        return {
            "available": False,
            "coverage": {"state": "missing", "label": "尚无逐条数据", "detail": reason},
            "note": reason,
            "window_start": None,
            "window_end": None,
            "commit_count": 0,
            "author_count": 0,
            "daily_counts": [],
            "authors": [],
            "author_distribution": [],
            "unidentified_commit_count": 0,
            "items": [],
            "total": 0,
        }

    task_ids, archive_paths, module_coverage = _archive_sources(run, "commits", "COMMIT_ARCHIVE_UNAVAILABLE", "Commit")

    scope_end = run.window_end
    scope_start = scope_end - timedelta(days=window_days) if window_days is not None else run.window_start
    # 后续采集可能更新事件的来源任务。下方以所选归档判断记录是否属于本次结果，
    # 事件库则提供对应时间戳。
    events = []
    if task_ids:
        events = session.scalars(select(RepositoryActivityEvent).where(
            RepositoryActivityEvent.repository_id == repository_id,
            RepositoryActivityEvent.event_type == "commit",
            RepositoryActivityEvent.event_at.is_not(None),
            RepositoryActivityEvent.event_at >= scope_start,
            RepositoryActivityEvent.event_at < scope_end,
        )).all()
    event_by_sha = {event.source_item_id: event for event in events}

    if week_start is not None:
        week_begin = datetime.combine(week_start, time.min)
        week_end = week_begin + timedelta(days=7)
        event_by_sha = {
            sha: event for sha, event in event_by_sha.items()
            if week_begin <= event.event_at < week_end
        }

    archive_found = False
    missing_archive = False
    records_by_sha = {}
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
            for page_items in iter_module_pages(archive.get("commits")):
                if len(page_items) > 1000:
                    raise ValueError("invalid commit archive page")
                for raw_item in page_items:
                    sha = raw_item.get("sha")
                    event = event_by_sha.get(sha) if isinstance(sha, str) else None
                    if event is None:
                        continue
                    commit = raw_item.get("commit") if isinstance(raw_item.get("commit"), dict) else {}
                    message = commit.get("message") if isinstance(commit.get("message"), str) else ""
                    title = message.splitlines()[0].strip()[:500] if message.strip() else "（无提交说明）"
                    github_author = raw_item.get("author") if isinstance(raw_item.get("author"), dict) else {}
                    git_author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
                    login = github_author.get("login") if isinstance(github_author.get("login"), str) else ""
                    git_name = git_author.get("name") if isinstance(git_author.get("name"), str) else ""
                    author = login or git_name or "匿名作者"
                    is_bot = github_author.get("type") == "Bot" or author.casefold().endswith("[bot]")
                    records_by_sha[sha] = {
                        "sha": sha,
                        "title": title,
                        "author": author,
                        "is_bot": is_bot,
                        "anonymous": not bool(login),
                        "date": iso_z(event.event_at),
                        "url": f"https://github.com/{repository.full_name}/commit/{sha}",
                        "_author_key": login.casefold() if login else (git_name.casefold() or "\0unidentified"),
                        "_author_identified": bool(login or git_name),
                    }
    except (OSError, ValueError, TypeError, json.JSONDecodeError, RecursionError) as exc:
        raise AppError(503, "COMMIT_ARCHIVE_UNAVAILABLE", "Commit 采集归档损坏或不可读取，请重新采集仓库数据") from exc

    coverage_state = "partial" if module_coverage == "budget_exhausted" else module_coverage if module_coverage in {"complete", "partial"} else "missing"
    if not archive_found:
        coverage_state = "missing"
    elif missing_archive:
        coverage_state = "partial"
    coverage_labels = {"complete": "采集完整", "partial": "部分采集", "missing": "暂无逐条数据"}
    coverage_details = {
        "complete": "完整仅代表本次采集范围与页数设置已完成，不代表 GitHub 全部历史",
        "partial": "采集未覆盖全部设置范围，明细可能不完整",
        "missing": "当前没有可读取的 Commit 归档，请重新采集仓库数据",
    }
    available = archive_found and coverage_state != "missing"

    records = list(records_by_sha.values())
    records.sort(key=lambda item: (item["date"], item["sha"]), reverse=True)
    daily = Counter(item["date"][:10] for item in records)
    author_groups = {}
    for item in records:
        key = item["_author_key"]
        group = author_groups.setdefault(key, {
            "author": item["author"], "commits": 0, "is_bot": item["is_bot"], "anonymous": item["anonymous"],
        })
        group["commits"] += 1
    authors = sorted(author_groups.values(), key=lambda item: (-item["commits"], item["author"].casefold()))[:20]
    identified_counts = Counter(item["_author_key"] for item in records if item["_author_identified"])
    unidentified_commits = sum(not item["_author_identified"] for item in records)
    author_distribution = Counter(identified_counts.values())

    normalized_search = (search or "").strip().casefold()
    filtered = [item for item in records if not normalized_search or normalized_search in item["title"].casefold() or normalized_search in item["author"].casefold() or normalized_search in item["sha"].casefold()]
    for item in records:
        item.pop("_author_key", None)
        item.pop("_author_identified", None)
    if week_start is not None:
        range_start, range_end = week_begin, week_end
    else:
        range_start, range_end = scope_start, scope_end
    if not available:
        note = "当前采集没有可读取的 Commit 逐条归档，请重新采集深度活动数据。"
    else:
        note = "只展示本次采集窗口内已归档的 Commit；SHA 去重，作者邮箱不会返回。"
        if coverage_state == "partial" or missing_archive:
            note = "部分采集归档缺失或未覆盖完整设置范围，当前明细可能不完整；未采集的历史数据不会补造。"
    return {
        "available": available,
        "coverage": {"state": coverage_state, "label": coverage_labels[coverage_state], "detail": coverage_details[coverage_state]},
        "note": note,
        "window_start": iso_z(range_start),
        "window_end": iso_z(range_end),
        "commit_count": len(records),
        "author_count": len(author_groups),
        "daily_counts": [{"date": day, "count": count} for day, count in sorted(daily.items())],
        "authors": authors,
        "author_distribution": [
            {"commits": commits, "authors": count}
            for commits, count in sorted(author_distribution.items())
        ],
        "unidentified_commit_count": unidentified_commits,
        "items": filtered[(page - 1) * per_page : page * per_page],
        "total": len(filtered),
    }


