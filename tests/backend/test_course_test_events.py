import csv
import io
import json
import hashlib
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import func, select

from backend.app.persistence.models import CollectionTask, MaintenanceRun, RepositoryInsightRun
from backend.app.services import course_test_events, maintenance
from backend.app.services.course_research_dataset import import_course_research_bundle
from backend.app.services.insight_comparison import compare_insights
from backend.app.services.insights import repository_commit_activity, repository_insights


HEADERS = {"X-Internal-Api-Key": "test-internal-key"}
REPOSITORY_ID = 1007360921  # trymirai/uzu，固定留出测试组成员。


def test_historical_event_manifest_uses_canonical_id_and_keeps_archive_hashes():
    from backend.app.core.config import PROJECT_ROOT

    bundle = PROJECT_ROOT / "data/datasets/course-research-events-300-v1"
    manifest = json.loads((bundle / "dataset.json").read_text(encoding="utf-8"))
    archive = hashlib.sha256((bundle / "events.sqlite3.gz").read_bytes()).hexdigest()
    assert manifest["dataset_id"] == "course-research-events-300-v1"
    assert "course-test-events-v1" in manifest["legacy_dataset_ids"]
    assert manifest["archive_sha256"] == archive == "94651c54b8ded3f928564ff4a665e0e2d4807c7cd934ae16fa694898a326a64c"
    assert manifest["sqlite_sha256"] == "95b7a864c83a4bc09a534aa8232a90e13ad6e67ed7c40a66900cd65b1c8cb9c7"


def test_test_repository_displays_local_event_analysis_and_records(backend_client, tmp_path, monkeypatch):
    client, factory, github = backend_client
    archive_root = tmp_path / "raw # history"
    monkeypatch.setattr(maintenance, "get_settings", lambda: SimpleNamespace(raw_data_path=archive_root, base_refresh_hours=24))
    monkeypatch.setattr(course_test_events, "get_settings", lambda: SimpleNamespace(raw_data_path=archive_root))
    monkeypatch.setattr(github, "get_repository", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("不应访问 GitHub")))
    with factory() as session:
        import_course_research_bundle(session, archive_root=archive_root)
        tasks_before = session.scalar(select(func.count()).select_from(CollectionTask))

    detail = client.get(f"/api/v1/repositories/{REPOSITORY_ID}", headers=HEADERS)
    assert detail.status_code == 200
    assert detail.json()["data"]["repository"]["has_historical_data"] is True
    response = client.get(f"/api/v1/repositories/{REPOSITORY_ID}/insights?window_days=90", headers=HEADERS)
    assert response.status_code == 200
    result = response.json()["data"]
    assert result["origin"] == "course-test-events-v1"
    assert result["canonical_dataset_id"] == "course-research-events-300-v1"
    assert result["window_available"] is True
    assert (result["window_start"], result["window_end"]) == ("2026-08-07T10:31:37Z", "2026-11-05T10:31:37Z")
    assert result["observed_counts"]["commits_count"] == 285
    assert result["insights"]["issue_resolution"]["quality"]["coverage"] == "partial"
    assert result["insights"]["pr_merges"]["quality"]["valid_samples"] == 269
    assert result["insights"]["release_cadence"]["release_count"] == 38
    assert result["chart_data"]["commit_weekly"]
    window_counts = []
    for days in (30, 90, 180):
        response = client.get(f"/api/v1/repositories/{REPOSITORY_ID}/insights", params={"window_days": days}, headers=HEADERS)
        assert response.status_code == 200
        window = response.json()["data"]
        assert window["requested_window_days"] == days
        assert (datetime.fromisoformat(window["window_end"].replace("Z", "+00:00")) - datetime.fromisoformat(window["window_start"].replace("Z", "+00:00"))).days == days
        window_counts.append(window["observed_counts"]["commits_count"])
    assert window_counts[0] <= window_counts[1] <= window_counts[2]

    commits = client.get(f"/api/v1/repositories/{REPOSITORY_ID}/commits?window_days=90", headers=HEADERS).json()["data"]
    assert commits["available"] and commits["commit_count"] == 285
    assert commits["daily_counts"] and commits["items"][0]["is_bot"] is None
    issues = client.get(f"/api/v1/repositories/{REPOSITORY_ID}/issues?window_days=90", headers=HEADERS).json()["data"]
    assert issues["available"] and issues["coverage"]["state"] == "partial" and issues["total"] > 0
    assert "未保存标题" in issues["items"][0]["title"]
    issue = client.get(f"/api/v1/repositories/{REPOSITORY_ID}/issues/{issues['items'][0]['number']}", headers=HEADERS)
    assert issue.status_code == 200 and issue.json()["data"]["body"] is None
    pulls = client.get(f"/api/v1/repositories/{REPOSITORY_ID}/pull-requests?window_days=90", headers=HEADERS).json()["data"]
    assert pulls["available"] and pulls["total"] > 0 and pulls["items"][0]["comments_count"] is None
    pull = client.get(f"/api/v1/repositories/{REPOSITORY_ID}/pull-requests/{pulls['items'][0]['number']}", headers=HEADERS)
    assert pull.status_code == 200 and pull.json()["data"]["body"] is None
    utc_range = {"window_days": 90, "merged_from": "2026-09-30T16:00:00Z", "merged_to": "2026-10-07T16:00:00Z"}
    local_range = {"window_days": 90, "merged_from": "2026-10-01T00:00:00+08:00", "merged_to": "2026-10-08T00:00:00+08:00"}
    filtered = client.get(f"/api/v1/repositories/{REPOSITORY_ID}/pull-requests", params=utc_range, headers=HEADERS)
    local_filtered = client.get(f"/api/v1/repositories/{REPOSITORY_ID}/pull-requests", params=local_range, headers=HEADERS)
    assert filtered.status_code == local_filtered.status_code == 200
    assert filtered.json()["data"]["total"] > 0
    assert filtered.json()["data"]["items"] == local_filtered.json()["data"]["items"]
    assert all(utc_range["merged_from"] <= item["merged_at"] < utc_range["merged_to"] for item in filtered.json()["data"]["items"])
    release_id = result["insights"]["release_cadence"]["timeline"][0]["id"]
    release = client.get(f"/api/v1/repositories/{REPOSITORY_ID}/releases/{release_id}", headers=HEADERS)
    assert release.status_code == 200 and release.json()["data"]["body"] is None
    named_release = client.get(f"/api/v1/repositories/{REPOSITORY_ID}/releases/429413709", headers=HEADERS)
    assert named_release.status_code == 200 and named_release.json()["data"]["name"] == "0.6.15"
    with factory() as session:
        session.add(RepositoryInsightRun(
            run_id="older-analysis", input_fingerprint="older-analysis", repository_id=REPOSITORY_ID,
            metric_version="insights-v1", window_start=datetime(2020, 1, 1), window_end=datetime(2020, 2, 1),
            analyzed_at=datetime(2020, 2, 1), source_task_ids_json="[]", source_archive_paths_json="[]",
            module_coverage_json="{}", status="missing", limitations_json="[]", result_json="{}",
        ))
        session.commit()
    release_with_other_run = client.get(f"/api/v1/repositories/{REPOSITORY_ID}/releases/{release_id}", headers=HEADERS)
    assert release_with_other_run.status_code == 200 and release_with_other_run.json()["data"]["body"] is None

    with factory() as session:
        assert session.scalar(select(func.count()).select_from(CollectionTask)) == tasks_before
        session.delete(session.get(RepositoryInsightRun, "older-analysis"))
        session.delete(session.get(MaintenanceRun, f"course150-v1-{REPOSITORY_ID}"))
        session.commit()
    assert client.get(f"/api/v1/repositories/{REPOSITORY_ID}", headers=HEADERS).json()["data"]["repository"]["has_historical_data"] is False
    assert client.get(f"/api/v1/repositories/{REPOSITORY_ID}/insights?window_days=90", headers=HEADERS).json()["data"]["window_available"] is False


def test_all_300_use_local_events_and_observed_partial_metrics_can_be_weighted(backend_client, tmp_path, monkeypatch):
    client, factory, github = backend_client
    archive_root = tmp_path / "raw"
    monkeypatch.setattr(maintenance, "get_settings", lambda: SimpleNamespace(raw_data_path=archive_root, base_refresh_hours=24))
    monkeypatch.setattr(course_test_events, "get_settings", lambda: SimpleNamespace(raw_data_path=archive_root))
    monkeypatch.setattr(github, "get_repository", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("不应访问 GitHub")))
    with factory() as session:
        import_course_research_bundle(session, archive_root=archive_root)
        tasks_before = session.scalar(select(func.count()).select_from(CollectionTask))

    renovate, sglang = 76734068, 740303686
    renovate_data = client.get(f"/api/v1/repositories/{renovate}/insights?window_days=90", headers=HEADERS).json()["data"]
    sglang_data = client.get(f"/api/v1/repositories/{sglang}/insights?window_days=90", headers=HEADERS).json()["data"]
    assert renovate_data["origin"] == sglang_data["origin"] == "course-test-events-v1"
    assert renovate_data["insights"]["release_cadence"]["quality"]["status"] == "partial"
    assert renovate_data["insights"]["release_cadence"]["median_interval_days"] is not None
    assert sglang_data["insights"]["pr_merges"]["quality"]["status"] == "partial"
    assert sglang_data["insights"]["pr_merges"]["median_hours"] is not None

    selection = {"repository_ids": [renovate, sglang], "window_days": 90,
                 "weights": {"commits_weekly_mean": 1, "issue_median_hours": 1,
                             "pr_median_hours": 1, "release_interval_days": 1}}
    response = client.post("/api/v1/comparisons/selection", json=selection, headers=HEADERS)
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert result["status"] == "available" and len(result["ranking"]) == 2
    ranked = {row["repository_id"]: row for row in result["ranking"]}
    assert ranked[renovate]["evidence"]["release_interval_days"]["quality"] == "partial"
    assert ranked[sglang]["evidence"]["pr_median_hours"]["quality"] == "partial"
    assert all(0 <= row["score"] <= 100 for row in result["ranking"])

    exported = client.get("/api/v1/exports/research-insights.csv", params={
        "dataset_id": "course-research-300-v1", "analysis_mode": "course",
    }, headers=HEADERS)
    assert exported.status_code == 200
    overall = {row["指标"]: row for row in csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig"))) if row["统计层级"] == "总体"}
    assert all(int(overall[label]["有效样本"]) > 0 for label in ("Issue 关闭耗时 P50", "PR 合并耗时 P50", "正式 Release 间隔 P50"))

    zero_activity = 527591471
    response = client.post("/api/v1/comparisons/selection", json={
        "repository_ids": [zero_activity, REPOSITORY_ID], "window_days": 90,
        "weights": {"commits_weekly_mean": 1},
    }, headers=HEADERS)
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert result["status"] == "available" and len(result["ranking"]) == 2
    assert next(row for row in result["ranking"] if row["repository_id"] == zero_activity)["evidence"]["commits_weekly_mean"]["value"] == 0
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(CollectionTask)) == tasks_before


def test_partial_online_run_does_not_hide_snapshot_but_newer_ready_run_is_used(backend_client, tmp_path, monkeypatch):
    _client, factory, _github = backend_client
    archive_root = tmp_path / "raw"
    monkeypatch.setattr(maintenance, "get_settings", lambda: SimpleNamespace(raw_data_path=archive_root, base_refresh_hours=24))
    monkeypatch.setattr(course_test_events, "get_settings", lambda: SimpleNamespace(raw_data_path=archive_root))
    with factory() as session:
        import_course_research_bundle(session, archive_root=archive_root)
        end = datetime(2026, 11, 12)
        source = {module: {"coverage": "complete", "observed_records": 0, "rejected_records": 0, "invalid_event_times": 0}
                  for module in ("commits", "issues", "pulls", "releases")}
        run = RepositoryInsightRun(
            run_id="newer-run", input_fingerprint="newer-run", repository_id=REPOSITORY_ID,
            metric_version="insights-v1", window_start=end - timedelta(days=90), window_end=end,
            analyzed_at=end, source_task_ids_json="[]", source_archive_paths_json="[]",
            module_coverage_json=json.dumps(source), status="partial", limitations_json="[]",
            result_json=json.dumps({"origin": "collection"}),
        )
        session.add(run)
        session.commit()
        assert repository_insights(session, REPOSITORY_ID, 90)["origin"] == "course-test-events-v1"
        assert repository_commit_activity(session, REPOSITORY_ID, window_days=90)["commit_count"] == 285
        run.status = "ready"
        session.flush()
        assert repository_insights(session, REPOSITORY_ID, 90)["origin"] == "collection"
        comparison = compare_insights(session, [REPOSITORY_ID, 76734068], "same_period", 90)
        assert comparison["comparison_basis"]["status"] == "comparable"
        assert all(row["source_kind"] == "course_research_historical_snapshot" for row in comparison["repositories"])
        session.commit()
        from tests.backend.test_comparison_export import seed_activity_comparison
        seed_activity_comparison(factory)
        for mode in ("same_period", "individual_periods"):
            mixed = compare_insights(session, [REPOSITORY_ID, 321], mode, 90)
            assert mixed["repositories"][0]["source_kind"] == "course_research_historical_snapshot"
