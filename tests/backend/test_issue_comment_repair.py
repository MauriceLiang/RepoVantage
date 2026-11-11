from datetime import datetime

import httpx

from backend.app.integrations.github.client import GITHUB_API, GitHubClient
from backend.app.services.issue_comment_repair import collect_issue_comments


AS_OF = datetime(2026, 11, 5)
NOW = datetime(2026, 11, 9)


def issue(count):
    return {"id": 9, "number": 7, "created_at": "2026-10-01T00:00:00Z", "updated_at": "2026-11-01T00:00:00Z", "comments": count, "user": {"id": 1, "type": "User"}}


def comment(comment_id, author_id, author_type, day):
    return {"id": comment_id, "created_at": f"2026-10-{day:02}T00:00:00Z", "updated_at": f"2026-10-{day:02}T00:00:00Z",
            "user": {"id": author_id, "type": author_type}, "body": "must not be stored", "author_association": "CONTRIBUTOR"}


def make_client(handler):
    return GitHubClient(httpx.Client(base_url=GITHUB_API, transport=httpx.MockTransport(handler)), unbounded=True)


def test_follows_pages_audits_counts_and_keeps_only_event_metadata(monkeypatch):
    monkeypatch.setattr("backend.app.services.issue_comment_repair.utc_now", lambda: NOW)
    def handler(request):
        if request.url.path.endswith("/comments"):
            if request.url.params.get("page") == "2":
                return httpx.Response(200, json=[comment(3, 2, "User", 4)])
            return httpx.Response(200, headers={"Link": f'<{GITHUB_API}/repos/a/b/issues/7/comments?page=2>; rel="next"'},
                                  json=[comment(1, 5, "Bot", 2), comment(2, 1, "User", 3)])
        return httpx.Response(200, json=issue(3))
    result = collect_issue_comments(make_client(handler), "a/b", 7, AS_OF)
    assert result["coverage"] == "complete_current_snapshot"
    assert result["label_14d_non_author_non_bot"] == 1
    assert [page["page"] for page in result["pages"]] == [1, 2]
    assert [row["comment_id"] for row in result["comments"]] == [1, 2, 3]
    assert all("body" not in row for row in result["comments"])


def test_no_current_comments_is_not_a_proven_historical_negative(monkeypatch):
    monkeypatch.setattr("backend.app.services.issue_comment_repair.utc_now", lambda: NOW)
    def handler(request):
        return httpx.Response(200, json=[] if request.url.path.endswith("/comments") else issue(0))
    result = collect_issue_comments(make_client(handler), "a/b", 7, AS_OF)
    assert result["coverage"] == "complete_current_snapshot"
    assert result["label_14d_non_author_non_bot"] is None
    assert result["label_reason"] == "historical_negative_unverifiable"


def test_rate_limit_preserves_partial_page_and_does_not_claim_completion(monkeypatch):
    monkeypatch.setattr("backend.app.services.issue_comment_repair.utc_now", lambda: NOW)
    def handler(request):
        if not request.url.path.endswith("/comments"):
            return httpx.Response(200, json=issue(2))
        if request.url.params.get("page") == "2":
            return httpx.Response(429, headers={"Retry-After": "30"}, json={"message": "rate limit"})
        return httpx.Response(200, headers={"Link": f'<{GITHUB_API}/repos/a/b/issues/7/comments?page=2>; rel="next"'}, json=[comment(1, 1, "User", 2)])
    result = collect_issue_comments(make_client(handler), "a/b", 7, AS_OF)
    assert result["coverage"] == "coverage_uncertain"
    assert result["pagination_error"] == "GITHUB_RATE_LIMITED"
    assert [row["comment_id"] for row in result["comments"]] == [1]
    assert result["label_14d_non_author_non_bot"] is None


def test_repeated_link_is_uncertain_and_terminates(monkeypatch):
    monkeypatch.setattr("backend.app.services.issue_comment_repair.utc_now", lambda: NOW)
    def handler(request):
        if request.url.path.endswith("/comments"):
            return httpx.Response(200, headers={"Link": f'<{request.url}>; rel="next"'}, json=[comment(1, 1, "User", 2)])
        return httpx.Response(200, json=issue(1))
    result = collect_issue_comments(make_client(handler), "a/b", 7, AS_OF)
    assert result["coverage"] == "coverage_uncertain"
    assert result["pagination_error"] == "GITHUB_PAGINATION_INVALID"
    assert len(result["pages"]) == 1


def test_mismatched_count_cannot_produce_negative(monkeypatch):
    monkeypatch.setattr("backend.app.services.issue_comment_repair.utc_now", lambda: NOW)
    def handler(request):
        return httpx.Response(200, json=[comment(1, 1, "User", 2)] if request.url.path.endswith("/comments") else issue(2))
    result = collect_issue_comments(make_client(handler), "a/b", 7, AS_OF)
    assert result["coverage"] == "coverage_uncertain"
    assert "comment_count_mismatch" in result["coverage_reasons"]
    assert result["label_14d_non_author_non_bot"] is None
