import httpx

from backend.app.integrations.github.client import GITHUB_API, GitHubClient
from scripts.collect_ml_holdout import collect_repo


def candidate():
    return {"repository_id": 42, "selected_full_name": "a/b", "stratum": "Python:0-999"}


def profile():
    return {"id": 42, "full_name": "a/b", "created_at": "2020-01-01T00:00:00Z", "private": False, "default_branch": "main"}


def event(sha, when):
    return {"sha": sha, "commit": {"committer": {"date": when}, "author": {"date": when}}, "message": "not retained"}


def client(handler):
    return GitHubClient(httpx.Client(base_url=GITHUB_API, transport=httpx.MockTransport(handler)))


def test_holdout_collects_half_open_weeks_and_sanitizes_events():
    def handler(request):
        if request.url.path.endswith("/commits"):
            return httpx.Response(200, json=[event("c", "2026-11-02T00:00:00Z"), event("b", "2026-10-05T00:00:00Z"), event("a", "2026-07-13T00:00:00Z")])
        return httpx.Response(200, json=profile())
    result = collect_repo(client(handler), candidate(), 10)
    assert result["status"] == "complete_current_snapshot"
    assert result["weekly_commits"][0] == 1 and result["weekly_commits"][12] == 1
    assert sum(result["weekly_commits"]) == 2
    assert all("message" not in item for item in result["events"])


def test_page_budget_or_full_terminal_page_does_not_count_as_complete():
    def paginated(request):
        if request.url.path.endswith("/commits"):
            return httpx.Response(200, headers={"Link": f'<{GITHUB_API}/repositories/42/commits?page=2>; rel="next"'}, json=[event("a", "2026-10-05T00:00:00Z")])
        return httpx.Response(200, json=profile())
    result = collect_repo(client(paginated), candidate(), 1)
    assert result["status"] == "coverage_uncertain"
    assert "pagination_incomplete" in result["coverage_reasons"]

    def full(request):
        if request.url.path.endswith("/commits"):
            return httpx.Response(200, json=[event(str(i), "2026-10-05T00:00:00Z") for i in range(100)])
        return httpx.Response(200, json=profile())
    result = collect_repo(client(full), candidate(), 10)
    assert result["status"] == "coverage_uncertain"
    assert "full_terminal_page_unverified" in result["coverage_reasons"]


def test_branch_created_too_late_is_not_zero_activity():
    def handler(_request):
        return httpx.Response(200, json={**profile(), "created_at": "2026-08-01T00:00:00Z"})
    result = collect_repo(client(handler), candidate(), 10)
    assert result["status"] == "not_applicable"
    assert "weekly_commits" not in result
