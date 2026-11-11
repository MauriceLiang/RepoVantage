from datetime import datetime, timedelta
from types import SimpleNamespace

from backend.app.services import maintenance_collection
from backend.app.services.maintenance_collection import COURSE_MAINTENANCE_COMMIT_PAGE_BUDGET, collect_maintenance


class FakeGitHub:
    def __init__(self, *, partial=False, changed=False, empty=False, pr_partial=False, created_at="2020-01-01T00:00:00Z"):
        self.partial, self.changed, self.empty, self.pr_partial = partial, changed, empty, pr_partial
        self.created_at = created_at
        self.calls = []
        self.head_calls = 0
        self.pr_calls = []

    def get_repository_by_id(self, repository_id):
        return ({"id": repository_id, "private": False, "default_branch": "main", "created_at": self.created_at,
                 "pushed_at": "2026-11-01T00:00:00Z", "full_name": "example/repo"}, 200, None)

    def _request(self, method, path, *, params=None):
        self.calls.append((path, params))
        if path.endswith("/commits/main"):
            self.head_calls += 1
            sha = "b" * 40 if self.changed and self.head_calls == 2 else "a" * 40
            return SimpleNamespace(json=lambda: {"sha": sha})
        if path == "/search/issues":
            self.pr_calls.append(params["q"])
            is_cap_week = "2026-10-26..2026-11-01" in params["q"]
            count = 1000 if self.pr_partial and is_cap_week else 1 if is_cap_week and not self.empty else 0
            return SimpleNamespace(json=lambda: {"total_count": count, "incomplete_results": False})
        raise AssertionError(f"unexpected request {path}")

    def list_paginated_detailed(self, path, params, **kwargs):
        self.calls.append((path, params))
        row = [] if self.empty else [{"sha": "c" * 40, "commit": {"committer": {"date": "2026-10-30T12:00:00Z"}}}]
        if "on_page" in kwargs:
            kwargs["on_page"](SimpleNamespace(page_index=1, request_url=path, next_url=None, http_status=200,
                                                records=row, has_next=not self.partial))
        return SimpleNamespace(items=row, complete=not self.partial, error_code=None, pages_fetched=1,
                               has_next=self.partial)


class PageBudgetGitHub(FakeGitHub):
    def __init__(self, total_pages):
        super().__init__()
        self.total_pages = total_pages
        self.commit_pages = 0

    def list_paginated_detailed(self, path, params, *, max_pages, on_page, **kwargs):
        self.calls.append((path, params))
        self.commit_pages = min(self.total_pages, max_pages)
        records = []
        for index in range(self.commit_pages):
            rows = []
            if index == 0:
                rows = [{"sha": f"{index + 1:040x}", "commit": {"committer": {"date": "2026-10-30T12:00:00Z"}}}]
                records.extend(rows)
            has_next = index + 1 < self.total_pages
            on_page(SimpleNamespace(page_index=index + 1, request_url=path, next_url="next" if has_next else None,
                                    http_status=200, records=rows, has_next=has_next))
        complete = self.total_pages <= max_pages
        return SimpleNamespace(items=records, complete=complete, error_code=None,
                               pages_fetched=self.commit_pages, has_next=not complete)


def test_collection_defaults_to_twelve_weeks_and_aggregates_pr_counts(monkeypatch):
    monkeypatch.setattr(maintenance_collection, "utc_now", lambda: datetime(2026, 11, 9, 12))
    github = FakeGitHub()
    result = collect_maintenance(github, 1, end=datetime(2026, 11, 9))
    assert result["status"] == "complete" and len(result["weeks"]) == 12
    assert result["lookback_weeks"] == 12
    assert result["features"]["feature_schema_version"] == "course-maintenance-12w-v1"
    assert result["features"]["facts"]["commit_total"] == 1
    assert result["features"]["facts"]["pr_created_total"] == 1
    commit_query = next(params for path, params in github.calls if path.endswith("/commits"))
    assert commit_query == {"sha": "a" * 40, "since": "2026-08-17T00:00:00Z", "until": "2026-11-09T00:00:00Z"}
    assert len(github.pr_calls) == 12
    assert all("is:pr created:" in query for query in github.pr_calls)


def test_partial_commit_coverage_and_changed_default_branch_fail_closed(monkeypatch):
    monkeypatch.setattr(maintenance_collection, "utc_now", lambda: datetime(2026, 11, 9, 12))
    for github in (FakeGitHub(partial=True), FakeGitHub(changed=True)):
        result = collect_maintenance(github, 1, end=datetime(2026, 11, 9))
        assert result["status"] == "partial" and result["features"] is None
        assert all(row["commit_coverage"] == "partial" for row in result["weeks"])


def test_partial_pr_search_does_not_remove_complete_commit_facts(monkeypatch):
    monkeypatch.setattr(maintenance_collection, "utc_now", lambda: datetime(2026, 11, 9, 12))
    result = collect_maintenance(FakeGitHub(pr_partial=True), 1, end=datetime(2026, 11, 9))
    assert result["status"] == "complete"
    assert result["features"] is not None
    assert all(row["commit_coverage"] in {"complete", "true_zero"} for row in result["weeks"])
    assert any(row["pr_created_coverage"] == "partial" for row in result["weeks"])
    assert result["features"]["facts"]["pr_created_total"] is None


def test_empty_complete_coverage_is_a_proven_zero(monkeypatch):
    monkeypatch.setattr(maintenance_collection, "utc_now", lambda: datetime(2026, 11, 9, 12))
    result = collect_maintenance(FakeGitHub(empty=True), 1, end=datetime(2026, 11, 9))
    assert result["status"] == "complete"
    assert result["features"]["facts"]["commit_total"] == 0
    assert all(row["commit_coverage"] == "true_zero" and row["pr_created_coverage"] == "true_zero" for row in result["weeks"])


def test_short_lived_repository_uses_only_existing_complete_weeks(monkeypatch):
    monkeypatch.setattr(maintenance_collection, "utc_now", lambda: datetime(2026, 11, 9, 12))
    github = FakeGitHub(created_at="2026-10-20T12:00:00Z")
    result = collect_maintenance(github, 1, end=datetime(2026, 11, 9), lookback_weeks=24)
    assert result["status"] == "complete"
    assert len(result["weeks"]) == 2
    assert result["history_start"] == "2026-10-26T00:00:00Z"
    assert result["features"]["pattern_features"] is None
    assert result["features"]["facts"]["commit_observed_weeks"] == 2


def test_recent_complete_local_event_cache_avoids_commit_pagination(monkeypatch):
    monkeypatch.setattr(maintenance_collection, "utc_now", lambda: datetime(2026, 11, 9, 12))
    github = FakeGitHub()
    starts = [datetime(2026, 8, 17) + timedelta(weeks=index) for index in range(12)]
    result = collect_maintenance(github, 1, end=datetime(2026, 11, 9), cached_commit_counts={start: index for index, start in enumerate(starts)},
                                 cached_commit_source_run_id="recent-insight", cached_commit_analyzed_at="2026-11-02T00:00:00Z")
    assert result["status"] == "complete"
    assert result["source_audits"]["commits"]["source_type"] == "existing_local_event_cache"
    assert result["source_audits"]["commits"]["source_run_id"] == "recent-insight"
    assert not any(path.endswith("/commits") for path, _ in github.calls)
    assert result["features"]["facts"]["commit_total"] == sum(range(12))
    assert result["source_audits"]["commits"]["page_budget"] == COURSE_MAINTENANCE_COMMIT_PAGE_BUDGET
    assert result["source_audits"]["commits"]["pages_fetched"] == 0
    assert result["request_estimate"]["commit_cache_hit"] is True


def test_course_commit_page_budget_completes_twenty_pages_and_stops_past_budget(monkeypatch):
    monkeypatch.setattr(maintenance_collection, "utc_now", lambda: datetime(2026, 11, 9, 12))
    for total_pages, expected_status, expected_budget_exhausted in (
            (20, "complete", False), (21, "partial", True)):
        github = PageBudgetGitHub(total_pages)
        result = collect_maintenance(github, 1, end=datetime(2026, 11, 9))
        commit_audit = result["source_audits"]["commits"]
        assert result["status"] == expected_status
        assert commit_audit["page_budget"] == 20
        assert commit_audit["pages_fetched"] == 20
        assert commit_audit["budget_exhausted"] is expected_budget_exhausted
        assert github.commit_pages == 20
        assert result["request_estimate"]["commit_pages"] == 20
        assert result["request_estimate"]["total"] == 35
        if expected_budget_exhausted:
            assert "pagination_incomplete" in result["coverage_reasons"]["commits"]
            assert result["features"] is None
            assert all(row["commit_coverage"] == "partial" for row in result["weeks"])
