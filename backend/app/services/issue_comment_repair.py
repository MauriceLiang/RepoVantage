"""逐 Issue 审计当前可见评论；历史缺失不能自动解释为负例。"""
from datetime import timedelta

from backend.app.core.clock import iso_z, parse_github_datetime, utc_now
from backend.app.core.exceptions import AppError
from backend.app.integrations.github.client import GitHubClient, validate_full_name


def collect_issue_comments(github: GitHubClient, repository: str, issue_number: int, analysis_as_of):
    """跟随分页采集可见评论并对账快照，不持久化评论正文。

    两次 Issue 快照和评论数量一致只能证明当前可见数据的有限一致性，
    不能证明过去未发生过后来删除的评论。因此历史负例始终保留为未知。
    """
    owner, repo = validate_full_name(repository)
    before = github.get_issue_detail(repository, issue_number)
    created_value = before.get("created_at")
    issue_created = parse_github_datetime(created_value) if isinstance(created_value, str) else None
    issue_author = before.get("user") if isinstance(before.get("user"), dict) else {}
    updated_value = before.get("updated_at")
    issue_updated = parse_github_datetime(updated_value) if isinstance(updated_value, str) else None
    if not issue_created or not issue_updated or type(before.get("id")) is not int or type(before.get("comments")) is not int or before["comments"] < 0:
        raise AppError(502, "GITHUB_UPSTREAM_ERROR", "Issue 快照缺少有效的身份、创建时间或评论数")
    if analysis_as_of > utc_now():
        raise ValueError("analysis_as_of 不能晚于采集时间")
    pages, raw_comments, visited_urls = [], [], set()

    def record_page(page):
        pages.append({"page": page.page_index, "request_url": page.request_url, "next_url": page.next_url,
                      "http_status": page.http_status, "observed_count": len(page.records), "has_next": page.has_next})
        raw_comments.extend(page.records)
        if page.request_url in visited_urls or (not page.records and page.has_next):
            raise AppError(502, "GITHUB_PAGINATION_INVALID", "GitHub 返回重复或无效的分页")
        visited_urls.add(page.request_url)
        if page.next_url in visited_urls:
            raise AppError(502, "GITHUB_PAGINATION_INVALID", "GitHub 分页出现循环")

    try:
        result = github.list_paginated_detailed(
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments", {}, on_page=record_page,
            collect_items=False, collect_raw_pages=False,
        )
        pagination_complete, pagination_error = result.complete, result.error_code
    except AppError as exc:
        pagination_complete, pagination_error = False, exc.code
    comments = []
    errors = []
    seen = set()
    for item in raw_comments:
        author = item.get("user") if isinstance(item.get("user"), dict) else {}
        comment_id = item.get("id")
        created = parse_github_datetime(item.get("created_at")) if isinstance(item.get("created_at"), str) else None
        updated = parse_github_datetime(item.get("updated_at")) if isinstance(item.get("updated_at"), str) else None
        if type(comment_id) is not int or comment_id in seen or not created or not updated or updated < created or created < issue_created:
            errors.append("invalid_or_duplicate_comment")
            continue
        seen.add(comment_id)
        comments.append({"comment_id": comment_id, "issue_number": issue_number, "created_at": iso_z(created),
                         "updated_at": iso_z(updated), "author_id": author.get("id") if type(author.get("id")) is int else None,
                         "author_type": author.get("type") if isinstance(author.get("type"), str) else None,
                         "author_association": item.get("author_association") if isinstance(item.get("author_association"), str) else None})
    try:
        after = github.get_issue_detail(repository, issue_number) if pagination_error != "GITHUB_RATE_LIMITED" else {}
    except AppError as exc:
        after = {}
        errors.append("post_snapshot_unavailable")
        if exc.code == "GITHUB_RATE_LIMITED":
            pagination_error = exc.code
    stable = all(before.get(key) == after.get(key) for key in ("id", "number", "created_at", "comments", "updated_at"))
    if not pagination_complete or pagination_error:
        errors.append("pagination_incomplete")
    if not stable:
        errors.append("issue_changed_during_collection")
    if len(comments) != after.get("comments"):
        errors.append("comment_count_mismatch")
    if type(issue_author.get("id")) is not int:
        errors.append("issue_author_unknown")
    after_author = after.get("user") if isinstance(after.get("user"), dict) else {}
    if after_author.get("id") != issue_author.get("id"):
        errors.append("issue_author_changed_or_unavailable")
    for comment in comments:
        if comment["author_id"] is None or comment["author_type"] not in {"User", "Bot"}:
            errors.append("comment_author_unknown")
            break
    issue_author_id = issue_author.get("id") if type(issue_author.get("id")) is int else None
    deadline = issue_created + timedelta(days=14)
    human_replies = [comment for comment in comments if comment["author_type"] == "User"
                     and comment["author_id"] is not None and issue_author_id is not None
                     and comment["author_id"] != issue_author_id
                     and parse_github_datetime(comment["created_at"]) <= min(deadline, analysis_as_of)]
    human_replies.sort(key=lambda comment: (comment["created_at"], comment["comment_id"]))
    mature = deadline <= analysis_as_of
    label = 1 if mature and human_replies and "issue_author_changed_or_unavailable" not in errors else None
    return {
        "repository": f"{owner}/{repo}", "issue_id": before["id"], "issue_number": issue_number,
        "issue_created_at": iso_z(issue_created), "issue_author_id": issue_author_id,
        "issue_author_type": issue_author.get("type") if isinstance(issue_author.get("type"), str) else None,
        "snapshot_updated_at": after.get("updated_at"), "snapshot_comment_count": after.get("comments"),
        "captured_at": iso_z(utc_now()), "analysis_as_of": iso_z(analysis_as_of),
        "coverage": "complete_current_snapshot" if not errors else "coverage_uncertain",
        "coverage_reasons": sorted(set(errors)), "pagination_error": pagination_error,
        "pages": pages, "comments": comments,
        "label_14d_non_author_non_bot": label,
        "label_reason": "observed_response" if label == 1 else "observation_not_mature" if not mature else "historical_negative_unverifiable",
        "limitations": ["当前可见评论及快照对账不能证明历史上不存在随后删除的评论。", "非作者评论不等于维护者回复；机器人依据 GitHub 用户类型排除。"],
    }
