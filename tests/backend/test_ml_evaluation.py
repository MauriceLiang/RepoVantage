from datetime import datetime, timedelta
from types import SimpleNamespace

from backend.app.core.clock import iso_z
from backend.app.persistence.models import Repository
from backend.app.pipeline.raw_archive import archive_json
from backend.app.services import maintenance
from backend.app.services.maintenance import persist_maintenance

HEADERS = {"X-Internal-Api-Key": "test-internal-key"}
NOW = datetime(2026, 11, 9, 12)


def seed(factory, monkeypatch, *, commits=None, pr_coverage="complete", week_count=12):
    monkeypatch.setattr("backend.app.services.maintenance.utc_now", lambda: NOW)
    monkeypatch.setattr("backend.app.services.maintenance.get_settings", lambda: SimpleNamespace(base_refresh_hours=24, raw_data_path=monkeypatch.tmp_path))
    start = datetime(2026, 11, 9) - timedelta(weeks=week_count)
    commits = commits or [4, 5, 6, 4, 5, 6, 4, 5, 6, 4, 8, 12]
    weeks = []
    for index, count in enumerate(commits):
        lower = start + timedelta(weeks=index)
        pr_count = index % 3
        weeks.append({"week_start_utc": iso_z(lower), "week_end_exclusive_utc": iso_z(lower + timedelta(weeks=1)),
                      "commits": count, "prs_created": pr_count,
                      "commit_coverage": "true_zero" if count == 0 else "complete",
                      "pr_created_coverage": "partial" if pr_coverage != "complete" else "true_zero" if pr_count == 0 else "complete"})
    result = {"repository_id": 123, "status": "complete", "lookback_weeks": week_count,
              "history_start": iso_z(start), "history_end": iso_z(datetime(2026, 11, 9)), "captured_at": iso_z(NOW),
              "head_sha": "a" * 40, "weeks": weeks, "limitations": []}
    archive = archive_json(123, "evaluation", "maintenance", result, root=monkeypatch.tmp_path)
    with factory() as session:
        session.add(Repository(repository_id=123, full_name="example/project", html_url="https://github.com/example/project"))
        session.flush()
        persist_maintenance(session, "evaluation", result, archive)
        session.commit()


def test_recent_complete_data_exposes_three_independent_course_tasks(backend_client, monkeypatch, tmp_path):
    client, factory, _ = backend_client
    monkeypatch.tmp_path = tmp_path
    seed(factory, monkeypatch)
    response = client.get("/api/v1/repositories/123/evaluation", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["metrics"] == []
    assert data["maintenance_pattern"]["feature_schema_version"] == "course-maintenance-12w-v1"
    assert data["activity_trend"]["horizon_weeks"] == 4
    assert data["activity_trend"]["probabilities"] is None
    assert data["activity_anomaly"]["status"] == "baseline_only"
    assert client.get("/api/v1/repositories/123/evaluation").status_code == 401


def test_low_activity_keeps_facts_and_suppresses_trend_prediction(backend_client, monkeypatch, tmp_path):
    client, factory, _ = backend_client
    monkeypatch.tmp_path = tmp_path
    seed(factory, monkeypatch, commits=[0] * 12)
    data = client.get("/api/v1/repositories/123/evaluation", headers=HEADERS).json()["data"]
    assert data["maintenance_pattern"]["evidence"]["commit_total_12w"] == 0
    assert data["maintenance_pattern"]["evidence"]["commit_active_weeks_12w"] == 0
    assert data["activity_trend"]["status"] == "insufficient_data"
    assert data["activity_trend"]["reason_code"] == "low_activity_scope"


def test_pr_coverage_is_optional_for_commit_based_facts(backend_client, monkeypatch, tmp_path):
    client, factory, _ = backend_client
    monkeypatch.tmp_path = tmp_path
    seed(factory, monkeypatch, pr_coverage="partial")
    pattern = client.get("/api/v1/repositories/123/evaluation", headers=HEADERS).json()["data"]["maintenance_pattern"]
    assert pattern["status"] == "available"
    assert pattern["coverage"]["commits"] == "complete"
    assert pattern["coverage"]["pull_requests_created"] == "partial_or_unavailable"
    assert "pr_created_total_12w" not in pattern["evidence"]


def test_model_status_lists_only_the_three_frozen_course_tasks(backend_client):
    client, _, _ = backend_client
    response = client.get("/api/v1/models/status", headers=HEADERS)
    assert response.status_code == 200
    models = response.json()["data"]["models"]
    assert [item["model_id"] for item in models] == ["M1-maintenance-pattern", "M2-activity-trend", "M3-activity-anomaly"]
    assert models[0]["status"] in {"available", "model_unavailable"}
    assert models[1]["status"] in {"available", "model_unavailable"}
    assert models[2]["status"] == "baseline_only"
