"""Collect only recent complete UTC weeks for the course ML feature contract."""
import re
from datetime import timedelta
from urllib.parse import quote

from backend.app.analytics.course_ml_features import build_weekly_features
from backend.app.core.clock import iso_z, parse_github_datetime, utc_now
from backend.app.core.exceptions import AppError

COURSE_MAINTENANCE_COMMIT_PAGE_BUDGET = 20


def _timestamp(value):
    return parse_github_datetime(value) if isinstance(value, str) else None


def _week_end(value):
    return value.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=value.weekday())


def _first_full_week(created):
    floor = _week_end(created)
    return floor if created == floor else floor + timedelta(weeks=1)


def _search_pr_count(github, full_name, start, end):
    last_date = (end - timedelta(days=1)).date()
    query = f"repo:{full_name} is:pr created:{start.date().isoformat()}..{last_date.isoformat()}"
    response = github._request("GET", "/search/issues", params={"q": query, "per_page": 1})
    payload = response.json()
    if (not isinstance(payload, dict) or type(payload.get("total_count")) is not int
            or payload["total_count"] < 0 or not isinstance(payload.get("incomplete_results"), bool)):
        raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub PR 周计数返回了无效数据")
    count = payload["total_count"]
    if payload["incomplete_results"] or count >= 1000:
        return count, "partial", "search_incomplete_or_1000_result_cap"
    return count, "true_zero" if count == 0 else "complete", None


def collect_maintenance(github, repository_id, *, end=None, lookback_weeks=12,
                        max_pages=COURSE_MAINTENANCE_COMMIT_PAGE_BUDGET,
                        cached_commit_counts=None, cached_commit_source_run_id=None, cached_commit_analyzed_at=None):
    """Count recent Commit events and aggregate PR creation counts, preserving channel coverage."""
    if lookback_weeks not in {12, 24}:
        raise ValueError("lookback_weeks must be 12 or 24")
    now = utc_now()
    end = end or _week_end(now)
    if end != _week_end(end) or end > _week_end(now) or max_pages < 1:
        raise ValueError("结束时间必须是当前或更早的 UTC 完整周边界")
    requested_start = end - timedelta(weeks=lookback_weeks)
    profile, _, _ = github.get_repository_by_id(repository_id)
    created = _timestamp(profile.get("created_at")) if isinstance(profile, dict) else None
    branch = profile.get("default_branch") if isinstance(profile, dict) else None
    full_name = profile.get("full_name") if isinstance(profile, dict) else None
    if (not profile or profile.get("id") != repository_id or profile.get("private") is not False
            or created is None or not isinstance(full_name, str) or not full_name):
        raise AppError(502, "GITHUB_UPSTREAM_ERROR", "仓库资料不完整或身份不一致")
    actual_start = max(requested_start, _first_full_week(created))
    if actual_start >= end:
        return {"repository_id": repository_id, "full_name": full_name, "status": "insufficient_history",
                "lookback_weeks": lookback_weeks, "requested_start": iso_z(requested_start),
                "history_start": iso_z(actual_start), "history_end": iso_z(end), "captured_at": iso_z(now),
                "source_audits": {"commits": {"source_type": "unavailable"}, "prs_created": {"source_type": "github_search_counts"}},
                "coverage_reasons": {"commits": ["no_complete_week_since_repository_creation"]}, "weeks": [],
                "request_estimate": {"total": 1, "repository_profile": 1, "default_branch_checks": 0,
                                     "commit_pages": 0, "pr_week_searches": 0,
                                     "excludes_transport_retries": True},
                "limitations": ["仓库没有可观察的完整 UTC 周；没有用零值补齐建仓前历史。"]}

    starts = [actual_start + timedelta(weeks=index) for index in range(int((end - actual_start).days / 7))]
    errors = {"commits": [], "prs_created": []}
    source_audits = {"commits": {"source_type": "github_commits_endpoint", "page_budget": max_pages,
                                   "pages": [], "pages_fetched": 0, "budget_exhausted": False},
                     "prs_created": {"source_type": "github_search_counts", "weeks": []}}
    commit_counts = {start: 0 for start in starts}
    head = None
    default_branch_checks = 0
    commit_cache_used = False
    if isinstance(branch, str) and branch:
        default_branch_checks += 1
        head_response = github._request("GET", f"/repositories/{repository_id}/commits/{quote(branch, safe='')}")
        payload = head_response.json()
        head = payload.get("sha") if isinstance(payload, dict) else None
        if not isinstance(head, str) or not re.fullmatch(r"[a-fA-F0-9]{40}", head):
            raise AppError(502, "GITHUB_UPSTREAM_ERROR", "默认分支缺少可验证的提交 SHA")
        pushed_at = _timestamp(profile.get("pushed_at"))
        cache_at = _timestamp(cached_commit_analyzed_at)
        cache_usable = (isinstance(cached_commit_counts, dict) and isinstance(cached_commit_source_run_id, str)
                        and pushed_at is not None and cache_at is not None and pushed_at <= cache_at
                        and all(start in cached_commit_counts and type(cached_commit_counts[start]) is int
                                and cached_commit_counts[start] >= 0 for start in starts))
        if cache_usable:
            commit_cache_used = True
            commit_counts.update(cached_commit_counts)
            source_audits["commits"] = {"source_type": "existing_local_event_cache", "source_run_id": cached_commit_source_run_id,
                                        "cache_analyzed_at": iso_z(cache_at), "complete": True,
                                        "page_budget": max_pages, "pages_fetched": 0, "budget_exhausted": False,
                                        "pages": []}
        else:
            path = f"/repositories/{repository_id}/commits"

            def record(page):
                source_audits["commits"]["pages"].append({"page": page.page_index, "http_status": page.http_status,
                    "observed_count": len(page.records), "has_next": page.has_next, "request_url": page.request_url,
                    "next_url": page.next_url})

            def older_than_start(items):
                stamps = [_timestamp(((item.get("commit") or {}).get("committer") or {}).get("date"))
                          or _timestamp(((item.get("commit") or {}).get("author") or {}).get("date")) for item in items]
                return bool(stamps and all(stamp is not None and stamp < actual_start for stamp in stamps))

            result = github.list_paginated_detailed(path, {"sha": head, "since": iso_z(actual_start), "until": iso_z(end)},
                                                   max_pages=max_pages, on_page=record, collect_raw_pages=False,
                                                   stop_after_page=older_than_start)
            source_audits["commits"].update({"complete": result.complete, "error_code": result.error_code,
                                             "pages_fetched": result.pages_fetched,
                                             "budget_exhausted": not result.complete and result.has_next
                                             and result.pages_fetched >= max_pages})
            if result.error_code:
                errors["commits"].append(result.error_code)
            if not result.complete:
                errors["commits"].append("pagination_incomplete")
            seen = set()
            for item in result.items:
                sha = item.get("sha")
                commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
                committer = commit.get("committer") if isinstance(commit.get("committer"), dict) else {}
                author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
                stamp = _timestamp(committer.get("date")) or _timestamp(author.get("date"))
                if not isinstance(sha, str) or not re.fullmatch(r"[a-fA-F0-9]{40}", sha) or sha in seen or stamp is None:
                    errors["commits"].append("invalid_or_duplicate_commit")
                    continue
                seen.add(sha)
                if actual_start <= stamp < end:
                    week = _week_end(stamp)
                    if week in commit_counts:
                        commit_counts[week] += 1
            if source_audits["commits"]["pages"] and source_audits["commits"]["pages"][-1]["observed_count"] == 100 and not source_audits["commits"]["pages"][-1]["has_next"]:
                errors["commits"].append("full_terminal_page_unverified")
            default_branch_checks += 1
            final_head_response = github._request("GET", f"/repositories/{repository_id}/commits/{quote(branch, safe='')}")
            final_payload = final_head_response.json()
            final_head = final_payload.get("sha") if isinstance(final_payload, dict) else None
            if final_head != head:
                errors["commits"].append("default_branch_head_changed_during_collection")
    else:
        errors["commits"].append("default_branch_unavailable")
        source_audits["commits"].update({"complete": False, "error_code": "default_branch_unavailable"})

    pr_counts = {start: 0 for start in starts}
    if errors["commits"] and any(value == "GITHUB_RATE_LIMITED" for value in errors["commits"]):
        errors["prs_created"].append("deferred_after_rate_limit")
    else:
        for start in starts:
            try:
                count, coverage, reason = _search_pr_count(github, full_name, start, start + timedelta(weeks=1))
            except AppError as exc:
                if exc.code == "GITHUB_RATE_LIMITED":
                    source_audits["prs_created"]["weeks"].append({"week_start_utc": iso_z(start), "error_code": exc.code})
                    errors["prs_created"].append(exc.code)
                    break
                coverage, reason, count = "partial", exc.code, 0
            pr_counts[start] = count
            source_audits["prs_created"]["weeks"].append({"week_start_utc": iso_z(start), "count": count,
                                                              "coverage": coverage, "reason": reason})
            if coverage == "partial":
                errors["prs_created"].append(reason or "pr_search_partial")
    for start in starts:
        if len(source_audits["prs_created"]["weeks"]) <= starts.index(start):
            source_audits["prs_created"]["weeks"].append({"week_start_utc": iso_z(start), "count": 0,
                                                              "coverage": "partial", "reason": "not_observed"})
            errors["prs_created"].append("not_observed")

    weeks = []
    for start in starts:
        commit_cover = "partial" if errors["commits"] else "true_zero" if commit_counts[start] == 0 else "complete"
        audit = next((row for row in source_audits["prs_created"]["weeks"] if row["week_start_utc"] == iso_z(start)), {})
        pr_cover = audit.get("coverage", "partial")
        weeks.append({"week_start_utc": iso_z(start), "week_end_exclusive_utc": iso_z(start + timedelta(weeks=1)),
                      "commits": commit_counts[start], "prs_created": pr_counts[start],
                      "commit_coverage": commit_cover, "pr_created_coverage": pr_cover})
    commit_complete = not errors["commits"]
    features = build_weekly_features(weeks) if commit_complete else None
    pr_search_requests = sum(1 for row in source_audits["prs_created"]["weeks"]
                             if row.get("reason") != "not_observed")
    request_estimate = {"total": 1 + default_branch_checks + source_audits["commits"].get("pages_fetched", 0)
                        + pr_search_requests,
                        "repository_profile": 1, "default_branch_checks": default_branch_checks,
                        "commit_pages": source_audits["commits"].get("pages_fetched", 0),
                        "pr_week_searches": pr_search_requests, "commit_cache_hit": commit_cache_used,
                        "excludes_transport_retries": True}
    source_audits["request_estimate"] = request_estimate
    return {"repository_id": repository_id, "full_name": full_name,
            "status": "complete" if commit_complete else "partial", "lookback_weeks": lookback_weeks,
            "requested_start": iso_z(requested_start), "history_start": iso_z(actual_start), "history_end": iso_z(end),
            "captured_at": iso_z(utc_now()), "snapshot_at": iso_z(now), "default_branch": branch, "head_sha": head,
            "request_estimate": request_estimate,
            "coverage_reasons": {key: sorted(set(value)) for key, value in errors.items()},
            "source_audits": source_audits, "weeks": weeks, "features": features,
            "limitations": ["Commit 口径为当前默认分支 SHA 可见记录，日期按 committer_date、缺失时回退 author_date。",
                            "PR 周计数来自按完整 UTC 周切片的 GitHub 搜索聚合；搜索不完整或达到 1,000 条上限时标记为 partial。",
                            "未读取 Release、Issue 评论、PR 正文或补丁；没有扫描完整仓库历史。"]}
