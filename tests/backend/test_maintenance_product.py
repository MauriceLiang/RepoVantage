import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from backend.app.core.clock import iso_z
from backend.app.integrations.github.client import GitHubClient
from backend.app.persistence.models import MaintenanceRun, MaintenanceWeek, Repository
from backend.app.pipeline.raw_archive import archive_json
from backend.app.services import maintenance
from backend.app.services.maintenance import PATTERN_DISPLAY_NAMES
from backend.app.services.maintenance import persist_maintenance
from backend.app.worker.maintenance import execute_maintenance_task
from backend.app.worker.queue import claim_next_task
from tests.backend.test_maintenance_collection import FakeGitHub

HEADERS = {"X-Internal-Api-Key": "test-internal-key"}
NOW = datetime(2026, 11, 9, 12)


def test_pattern_display_labels_preserve_model_names_and_clusters():
    assert PATTERN_DISPLAY_NAMES == {
        "持续活动型": "持续提交型",
        "集中活动型": "集中提交型",
        "阶段波动型": "提交波动型",
        "低活动型": "低提交活动型",
    }


def setup_settings(monkeypatch, root):
    settings = SimpleNamespace(raw_data_path=root, base_refresh_hours=24)
    monkeypatch.setattr(maintenance, "get_settings", lambda: settings)
    monkeypatch.setattr("backend.app.pipeline.raw_archive.get_settings", lambda: settings)
    monkeypatch.setattr(maintenance, "utc_now", lambda: NOW)


def seed(factory, root, *, status="complete", captured=NOW, lookback=12, observed_weeks=None):
    end = datetime(2026, 11, 9)
    observed_weeks = lookback if observed_weeks is None else observed_weeks
    start = end - timedelta(weeks=observed_weeks)
    weeks = [{"week_start_utc": iso_z(start + timedelta(weeks=i)), "week_end_exclusive_utc": iso_z(start + timedelta(weeks=i + 1)),
              "commits": i % 4, "prs_created": i % 3, "commit_coverage": "complete", "pr_created_coverage": "complete"}
             for i in range(observed_weeks)]
    if status == "partial":
        weeks[0]["commit_coverage"] = "partial"
    result = {"repository_id": 123, "status": status, "lookback_weeks": lookback,
              "history_start": iso_z(start), "history_end": iso_z(end), "captured_at": iso_z(captured),
              "requested_start": iso_z(end - timedelta(weeks=lookback)),
              "head_sha": "a" * 40, "weeks": weeks, "limitations": []}
    archive = archive_json(123, "run-1", f"maintenance-{lookback}w", result, root=root)
    with factory() as session:
        session.add(Repository(repository_id=123, full_name="example/repo", html_url="https://github.com/example/repo"))
        session.flush()
        persist_maintenance(session, "run-1", result, archive)
        session.commit()
    return result, archive


def test_api_uses_the_shared_course_features_and_keeps_independent_task_statuses(backend_client, monkeypatch, tmp_path):
    client, factory, _ = backend_client
    setup_settings(monkeypatch, tmp_path)
    result, archive = seed(factory, tmp_path)
    response = client.get("/api/v1/repositories/123/evaluation", headers=HEADERS)
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    pattern = payload["maintenance_pattern"]
    assert payload["metrics"] == []
    assert pattern["status"] == "available" and pattern["method"] == "machine_learning"
    assert pattern["feature_schema_version"] == "course-maintenance-12w-v1"
    assert pattern["display_name"] == PATTERN_DISPLAY_NAMES[pattern["pattern_name"]]
    assert pattern["evidence"]["commit_total_12w"] == sum(row["commits"] for row in result["weeks"])
    actual = payload["recent_activity_change"]
    assert actual["status"] == "available" and actual["method"] == "factual"
    assert actual["previous_4w_commits"] == sum(row["commits"] for row in result["weeks"][-8:-4])
    assert actual["recent_4w_commits"] == sum(row["commits"] for row in result["weeks"][-4:])
    assert actual["trend"] == "近期基本稳定"
    assert payload["activity_trend"]["horizon_weeks"] == 4
    assert payload["activity_trend"]["probabilities"] is None
    assert any("历史留仓回测" in note for note in payload["activity_trend"]["notes"])
    assert "activity_anomaly" not in payload
    (tmp_path / archive).unlink()
    pattern = client.get("/api/v1/repositories/123/evaluation", headers=HEADERS).json()["data"]["maintenance_pattern"]
    assert pattern["status"] == "insufficient_data" and pattern["reason_code"] == "source_archive_unavailable"


def test_partial_observations_remain_visible_and_changed_week_never_create_model_results(backend_client, monkeypatch, tmp_path):
    client, factory, _ = backend_client
    setup_settings(monkeypatch, tmp_path)
    result, _ = seed(factory, tmp_path, status="partial")
    with factory() as session:
        run = session.get(MaintenanceRun, "run-1")
        run.captured_at = NOW - timedelta(days=2)
        session.commit()
    observation = client.get("/api/v1/repositories/123/evaluation", headers=HEADERS).json()["data"]["maintenance_pattern"]
    assert observation["reason_code"] == "incomplete_commits_coverage"
    assert observation["evidence"]["commit_complete_weeks"] == 11
    with factory() as session:
        run = session.get(MaintenanceRun, "run-1")
        run.captured_at = NOW
        session.commit()
    partial = client.get("/api/v1/repositories/123/evaluation", headers=HEADERS).json()["data"]
    assert partial["maintenance_pattern"]["status"] == "insufficient_data"
    assert partial["maintenance_pattern"]["evidence"]["commit_complete_weeks"] == 11
    assert partial["maintenance_pattern"]["evidence"]["commit_observed_partial_lower_bound"] == sum(row["commits"] for row in result["weeks"])
    assert partial["maintenance_pattern"]["evidence"]["commit_partial_weeks"] == 1
    assert partial["activity_trend"]["status"] == "partial_data"
    assert partial["recent_activity_change"]["status"] == "available"
    with factory() as session:
        run = session.get(MaintenanceRun, "run-1")
        run.status = "complete"
        week = session.scalar(select(MaintenanceWeek).where(MaintenanceWeek.run_id == "run-1"))
        week.commits += 1
        session.commit()
    assert client.get("/api/v1/repositories/123/evaluation", headers=HEADERS).json()["data"]["maintenance_pattern"]["reason_code"] == "source_integrity_mismatch"


def test_worker_collects_twelve_weeks_and_reuses_fresh_cache(backend_client, monkeypatch, tmp_path):
    client, factory, _ = backend_client
    setup_settings(monkeypatch, tmp_path)
    monkeypatch.setattr("backend.app.services.maintenance_collection.utc_now", lambda: NOW)
    with factory() as session:
        session.add(Repository(repository_id=123, full_name="example/repo", html_url="https://github.com/example/repo"))
        session.commit()
    response = client.post("/api/v1/repositories/123/maintenance-collection", headers=HEADERS)
    assert response.status_code == 202, response.text
    task_id = response.json()["data"]["task_id"]
    assert client.post("/api/v1/repositories/123/maintenance-collection", headers=HEADERS).json()["data"]["task_id"] == task_id
    with factory() as session:
        claimed = claim_next_task(session, "worker-test", 600)
        assert claimed.task_id == task_id and claimed.scope_kind == "maintenance"
    execute_maintenance_task(factory, task_id, FakeGitHub())
    with factory() as session:
        run = session.get(MaintenanceRun, task_id)
        assert run is not None and run.status == "complete"
        assert len(session.scalars(select(MaintenanceWeek).where(MaintenanceWeek.run_id == task_id)).all()) == 12
    payload = client.get("/api/v1/repositories/123/evaluation", headers=HEADERS).json()["data"]
    assert payload["maintenance_pattern"]["method"] == "machine_learning"
    assert payload["maintenance_pattern"]["source_run_id"] == task_id
    task = client.get(f"/api/v1/tasks/{task_id}", headers=HEADERS)
    assert task.status_code == 200 and task.json()["data"]["scope_kind"] == "maintenance"
    cached = client.post("/api/v1/repositories/123/maintenance-collection", headers=HEADERS)
    assert cached.status_code == 200
    assert cached.json()["data"]["status"] == "cached" and cached.json()["data"]["reused"] is True


def test_short_complete_repository_history_can_reuse_twelve_week_request_cache(backend_client, monkeypatch, tmp_path):
    client, factory, _ = backend_client
    setup_settings(monkeypatch, tmp_path)
    seed(factory, tmp_path, lookback=12, observed_weeks=4)
    response = client.post("/api/v1/repositories/123/maintenance-collection", headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "cached"
    assert response.json()["data"]["reused"] is True


def test_twelve_and_twenty_four_week_tasks_do_not_dedupe_each_other(backend_client):
    client, factory, _ = backend_client
    with factory() as session:
        session.add(Repository(repository_id=123, full_name="example/repo", html_url="https://github.com/example/repo"))
        session.commit()
    response12 = client.post("/api/v1/repositories/123/maintenance-collection?lookback_weeks=12", headers=HEADERS)
    assert response12.status_code == 202, response12.text
    task12 = response12.json()["data"]["task_id"]
    response24 = client.post("/api/v1/repositories/123/maintenance-collection?lookback_weeks=24", headers=HEADERS)
    assert response24.status_code == 202, response24.text
    task24 = response24.json()["data"]["task_id"]
    assert task12 != task24


def test_maintenance_collection_does_not_replace_basic_refresh(backend_client):
    client, factory, _ = backend_client
    with factory() as session:
        session.add(Repository(repository_id=123, full_name="example/repo", html_url="https://github.com/example/repo"))
        session.commit()
    maintenance_task = client.post("/api/v1/repositories/123/maintenance-collection", headers=HEADERS).json()["data"]["task_id"]
    response = client.post("/api/v1/repositories/123/refresh", headers=HEADERS, json={"depth": "basic", "force": True})
    assert response.status_code == 202, response.text
    assert response.json()["data"]["task_id"] != maintenance_task
    assert response.json()["data"]["reused"] is False


@pytest.mark.parametrize(("pages", "expected_status"), [(15, "succeeded"), (21, "partial")])
def test_high_volume_recent_collection_marks_page_cap_partial(backend_client, monkeypatch, tmp_path, pages, expected_status):
    client, factory, _ = backend_client
    setup_settings(monkeypatch, tmp_path)
    monkeypatch.setattr("backend.app.services.maintenance_collection.utc_now", lambda: NOW)
    with factory() as session:
        session.add(Repository(repository_id=123, full_name="example/repo", html_url="https://github.com/example/repo"))
        session.commit()
    task_id = client.post("/api/v1/repositories/123/maintenance-collection", headers=HEADERS).json()["data"]["task_id"]
    with factory() as session:
        assert claim_next_task(session, "worker-test", 600).task_id == task_id

    def github_response(request):
        path = request.url.path
        if path == "/repositories/123":
            return httpx.Response(200, json={"id": 123, "private": False, "default_branch": "main",
                                              "created_at": "2020-01-01T00:00:00Z", "full_name": "example/repo"})
        if path == "/repositories/123/commits/main":
            return httpx.Response(200, json={"sha": "a" * 40})
        if path == "/repositories/123/commits":
            page = int(request.url.params.get("page", "1"))
            headers = {"Link": f'<https://api.github.com/repositories/123/commits?page={page + 1}>; rel="next"'} if page < pages else {}
            item = {"sha": f"{page:040x}", "commit": {"committer": {"date": "2026-11-08T12:00:00Z"}}}
            return httpx.Response(200, headers=headers, json=[item])
        if path == "/search/issues":
            return httpx.Response(200, json={"total_count": 0, "incomplete_results": False, "items": []})
        raise AssertionError(f"unexpected GitHub path: {path}")

    with httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(github_response)) as http:
        execute_maintenance_task(factory, task_id, GitHubClient(client=http))
    task = client.get(f"/api/v1/tasks/{task_id}", headers=HEADERS).json()["data"]
    profile = client.get("/api/v1/repositories/123/evaluation", headers=HEADERS).json()["data"]["maintenance_pattern"]
    assert task["status"] == expected_status
    assert profile["evidence"]["commit_page_budget"] == 20
    assert profile["evidence"]["commit_pages_fetched"] == min(pages, 20)
    assert profile["evidence"]["github_request_estimate"] == min(pages, 20) + 15
    if expected_status == "succeeded":
        assert profile["evidence"]["commit_total_12w"] == 15
    else:
        assert profile["status"] == "insufficient_data"
        assert profile["reason_code"] == "maintenance_page_budget_exceeded"
        assert profile["evidence"]["commit_observed_partial_lower_bound"] == 20
        assert client.get("/api/v1/repositories/123/evaluation", headers=HEADERS).json()["data"]["activity_trend"]["status"] == "partial_data"
    with factory() as session:
        details = json.loads(session.get(MaintenanceRun, task_id).details_json)
        assert details["request_estimate"]["commit_pages"] == min(pages, 20)


def test_clear_repository_data_also_removes_maintenance_runs_and_weeks(backend_client, monkeypatch, tmp_path):
    client, factory, _ = backend_client
    setup_settings(monkeypatch, tmp_path)
    seed(factory, tmp_path)
    monkeypatch.setattr("backend.app.services.repository_data.get_settings", lambda: SimpleNamespace(raw_data_path=tmp_path))
    monkeypatch.setattr("backend.app.pipeline.collection_archive.COLLECTED_ROOT", tmp_path / "pages")
    response = client.post("/api/v1/repositories/data/clear", headers=HEADERS, json={"repository_ids": [123]})
    assert response.status_code == 200 and response.json()["data"]["repositories"][0]["maintenance_runs"] == 1
    with factory() as session:
        assert session.get(MaintenanceRun, "run-1") is None
        assert session.scalars(select(MaintenanceWeek).where(MaintenanceWeek.run_id == "run-1")).all() == []
    assert not (tmp_path / "123").exists()
