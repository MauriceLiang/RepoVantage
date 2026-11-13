import pytest

from backend.app.persistence.models import MaintenanceRun, Repository
from backend.app.pipeline.raw_archive import archive_json
from backend.app.services.maintenance import persist_maintenance
from tests.backend.test_comparison_export import seed_activity_comparison
from tests.backend.test_maintenance_product import seed as maintenance_seed, setup_settings


HEADERS = {"X-Internal-Api-Key": "test-internal-key"}


def body(**changes):
    value = {"repository_ids": [321, 322], "scenario": "选择服务端框架", "candidate_group": "同类框架",
             "candidates_confirmed": True, "window_days": 90, "allowed_languages": ["Python"], "allowed_licenses": ["MIT"],
             "weights": {"commits_weekly_mean": 3, "issue_median_hours": 1}}
    return {**value, **changes}


def seed(factory, **kwargs):
    seed_activity_comparison(factory, **kwargs)
    with factory() as session:
        for repository_id in (321, 322):
            session.get(Repository, repository_id).license_spdx = "MIT"
        session.commit()


def test_rule_ranking_uses_comparable_evidence_and_explicit_weights(backend_client):
    client, factory, _ = backend_client
    seed(factory)
    response = client.post("/api/v1/comparisons/selection", json=body(), headers=HEADERS)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "available" and data["method"] == "rule_based"
    assert data["scoring_version"] == "weighted-relative-v4"
    assert data["weights"] == {"commits_weekly_mean": 0.75, "issue_median_hours": 0.25}
    assert len(data["ranking"]) == 2 and len(data["sensitivity"]) == 2
    assert all(row["score"] == 50 for row in data["ranking"])
    assert all(sum(item["contribution"] for item in row["evidence"].values()) == 50 for row in data["ranking"])
    assert all(row["evidence"]["issue_median_hours"]["valid_samples"] >= 10 for row in data["ranking"])
    assert all(row["evidence"]["commits_weekly_mean"]["source_run_id"] for row in data["ranking"])
    assert "fixture/321" in data["report_markdown"] and "不是机器学习预测" in data["report_markdown"]
    assert "50.0/100" in data["report_markdown"] and "weighted-relative-v4" in data["report_markdown"]
    exported = client.post("/api/v1/reports/selection.md", json=body(), headers=HEADERS)
    assert exported.status_code == 200 and "综合分" in exported.text and "来源运行" in exported.text
    assert "不是机器学习预测" in exported.text and "fixture/321" in exported.text
    assert client.post("/api/v1/comparisons/selection", json=body()).status_code == 401


def test_weight_score_works_without_scenario_category_or_confirmation(backend_client):
    client, factory, _ = backend_client
    seed(factory)
    selection = {"repository_ids": [321, 322], "window_days": 90, "allowed_languages": [],
                 "allowed_licenses": [], "weights": {"commits_weekly_mean": 5}}
    response = client.post("/api/v1/comparisons/selection", json=selection, headers=HEADERS)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "available"
    assert data["scenario"] == "自定义权重对比"
    assert data["candidate_group"] == "当前所选仓库"
    assert len(data["ranking"]) == 2
    compatible = {**selection, "scenario": "自定义权重对比", "candidate_group": "当前所选仓库",
                  "candidates_confirmed": True, "weights": {"commits_weekly_mean": 5.37}}
    compatible_response = client.post("/api/v1/comparisons/selection", json=compatible, headers=HEADERS)
    assert compatible_response.status_code == 200, compatible_response.text
    assert compatible_response.json()["data"]["weights"] == {"commits_weekly_mean": 1.0}
    assert client.post("/api/v1/comparisons/selection", json={**selection, "weights": {"commits_weekly_mean": 10.1}}, headers=HEADERS).status_code == 422


def test_missing_metric_keeps_candidate_and_uses_neutral_score(backend_client):
    client, factory, _ = backend_client
    seed(factory, missing_first_issues=True)
    selection = body(weights={"issue_median_hours": 1})
    response = client.post("/api/v1/comparisons/selection", json=selection, headers=HEADERS)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "available"
    assert {row["repository_id"] for row in data["ranking"]} == {321, 322}
    rows = {row["repository_id"]: row for row in data["ranking"]}
    missing = rows[321]["evidence"]["issue_median_hours"]
    assert missing["value"] is None and missing["missing_policy"] == "neutral_50"
    assert missing["normalized"] == 0.5 and missing["contribution"] == 50
    assert rows[322]["evidence"]["issue_median_hours"]["missing_policy"] == "observed"
    assert "当前候选综合分并列" in data["report_markdown"]
    assert "无有效样本（中性 50 分）" in data["report_markdown"]
    assert any("中性 50 分" in note for note in data["notes"])


def test_small_observed_issue_samples_are_used_in_score(backend_client):
    client, factory, _ = backend_client
    seed(factory, issue_repeats=1)
    response = client.post("/api/v1/comparisons/selection", json=body(weights={"issue_median_hours": 1}), headers=HEADERS)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "available" and len(data["ranking"]) == 2
    for row in data["ranking"]:
        evidence = row["evidence"]["issue_median_hours"]
        assert evidence["valid_samples"] == 2
        assert evidence["value"] == 48 and evidence["missing_policy"] == "observed"


def test_partial_online_metric_uses_its_observed_samples(backend_client):
    client, factory, _ = backend_client
    seed(factory, partial_issues=True)
    response = client.post("/api/v1/comparisons/selection", json=body(weights={"issue_median_hours": 1}), headers=HEADERS)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "available" and len(data["ranking"]) == 2
    partial_row = next(row for row in data["ranking"] if row["repository_id"] == 321)
    evidence = partial_row["evidence"]["issue_median_hours"]
    assert evidence["valid_samples"] >= 1 and evidence["value"] is not None
    assert evidence["quality"] == "partial" and evidence["missing_policy"] == "observed"


def test_hard_constraints_still_exclude_candidates(backend_client):
    client, factory, _ = backend_client
    seed(factory)
    with factory() as session:
        session.get(Repository, 322).license_spdx = "GPL-3.0"
        session.commit()
    response = client.post("/api/v1/comparisons/selection", json=body(), headers=HEADERS)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "insufficient_data" and data["ranking"] == []
    reasons = {row["repository_id"]: " ".join(row["reasons"]) for row in data["excluded"]}
    assert "许可证" in reasons[322]


@pytest.mark.parametrize("offset", [20, 100])
def test_noncomparable_windows_fall_back_to_individual_windows(backend_client, offset):
    client, factory, _ = backend_client
    seed(factory, second_offset=offset, empty_issues=True)
    response = client.post("/api/v1/comparisons/selection", json=body(), headers=HEADERS)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "available" and len(data["ranking"]) == 2
    assert data["comparison_basis"]["scope"] == "repository_windows"
    assert data["comparison_basis"]["shared_window"] is None
    assert any("不代表同期表现" in note for note in data["notes"])
    assert all(row["evidence"]["issue_median_hours"]["missing_policy"] == "neutral_50" for row in data["ranking"])
    assert all(row["evidence"]["commits_weekly_mean"]["missing_policy"] == "observed" for row in data["ranking"])


def test_repositories_without_analysis_still_have_all_weighted_scores(backend_client):
    client, factory, _ = backend_client
    with factory() as session:
        session.add_all([Repository(repository_id=id, full_name=f"fixture/{id}", html_url=f"https://github.com/fixture/{id}") for id in (321, 322)])
        session.commit()
    response = client.post("/api/v1/comparisons/selection", json=body(
        allowed_languages=[], allowed_licenses=[],
        weights={"commits_weekly_mean": 1, "issue_median_hours": 1, "pr_median_hours": 1, "release_interval_days": 1},
    ), headers=HEADERS)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "available" and len(data["ranking"]) == 2 and not data["excluded"]
    for row in data["ranking"]:
        assert row["score"] == 50
        assert len(row["evidence"]) == 4
        assert all(item["value"] is None and item["missing_policy"] == "neutral_50" for item in row["evidence"].values())


def test_invalid_selection_configuration_is_rejected(backend_client):
    client, _, _ = backend_client
    assert client.post("/api/v1/comparisons/selection", json=body(weights={}), headers=HEADERS).status_code == 422
    assert client.post("/api/v1/comparisons/selection", json=body(repository_ids=[321, 321]), headers=HEADERS).status_code == 422
    assert client.post("/api/v1/comparisons/selection", json=body(weights={"commits_weekly_mean": 10.1}), headers=HEADERS).status_code == 422
    assert client.post("/api/v1/comparisons/selection", json=body(weights={"commits_weekly_mean": 1e308, "pr_median_hours": 1e308}), headers=HEADERS).status_code == 422


def test_commit_score_uses_logarithmic_diminishing_returns_and_cost_metrics_reverse():
    import math
    from backend.app.services.selection import _relative_score, _score_input

    commit_low = _score_input("commits_weekly_mean", 1)
    commit_high = _score_input("commits_weekly_mean", 99)
    middle_commit_score = _relative_score("commits_weekly_mean", 9, commit_low, commit_high)
    raw_linear_score = (9 - 1) / (99 - 1)
    expected = (math.log(10) - math.log(2)) / (math.log(100) - math.log(2))
    assert middle_commit_score == pytest.approx(expected)
    assert middle_commit_score > raw_linear_score
    assert _relative_score("issue_median_hours", 1, 1, 3) == 1
    assert _relative_score("issue_median_hours", 3, 1, 3) == 0
    assert _relative_score("issue_median_hours", 2, 2, 2) == 0.5


def test_feedback_requires_consent_and_current_comparable_selection_and_can_be_deleted(backend_client):
    client, factory, _ = backend_client
    seed(factory)
    selection = body()
    result = client.post("/api/v1/comparisons/selection", json=selection, headers=HEADERS).json()["data"]
    feedback = {"selection": selection, "result_signature": result["result_signature"], "chosen_repository_id": 321,
                "choice_kind": "preference", "reason": "适合当前场景", "consent": True}
    assert client.post("/api/v1/feedback/selection", json={**feedback, "consent": False}, headers=HEADERS).status_code == 422
    assert client.post("/api/v1/feedback/selection", json={**feedback, "chosen_repository_id": 999}, headers=HEADERS).status_code == 409
    assert client.post("/api/v1/feedback/selection", json={**feedback, "result_signature": "0" * 64}, headers=HEADERS).status_code == 409
    assert client.post("/api/v1/feedback/selection", json=feedback).status_code == 401
    response = client.post("/api/v1/feedback/selection", json=feedback, headers=HEADERS)
    assert response.status_code == 200, response.text
    created = response.json()["data"]
    assert created["chosen_repository_id"] == 321 and created["review_status"] == "pending"
    assert client.get("/api/v1/feedback/selection", headers=HEADERS).json()["data"] == [created]
    assert client.delete(f"/api/v1/feedback/selection/{created['feedback_id']}", headers=HEADERS).status_code == 204
    assert client.get("/api/v1/feedback/selection", headers=HEADERS).json()["data"] == []
    assert client.delete(f"/api/v1/feedback/selection/{created['feedback_id']}", headers=HEADERS).status_code == 404


def test_feedback_rejects_comparison_changed_after_display(backend_client):
    client, factory, _ = backend_client
    seed(factory)
    selection = body()
    result = client.post("/api/v1/comparisons/selection", json=selection, headers=HEADERS).json()["data"]
    with factory() as session:
        session.get(Repository, 321).license_spdx = "GPL-3.0"
        session.commit()
    response = client.post("/api/v1/feedback/selection", headers=HEADERS, json={
        "selection": selection, "result_signature": result["result_signature"], "chosen_repository_id": 321,
        "choice_kind": "preference", "reason": "", "consent": True,
    })
    assert response.status_code == 409
    assert client.get("/api/v1/feedback/selection", headers=HEADERS).json()["data"] == []


def test_maintenance_evidence_matches_report_without_changing_rule_ranking(backend_client, monkeypatch, tmp_path):
    client, factory, _ = backend_client
    seed(factory)
    setup_settings(monkeypatch, tmp_path)
    original = client.post("/api/v1/comparisons/selection", json=body(), headers=HEADERS).json()["data"]
    result, _ = maintenance_seed(factory, tmp_path)
    with factory() as session:
        for repository_id in (321, 322):
            source = {**result, "repository_id": repository_id}
            run_id = f"maintenance-{repository_id}"
            archive = archive_json(repository_id, run_id, "maintenance", source, root=tmp_path)
            persist_maintenance(session, run_id, source, archive)
        session.commit()

    response = client.post("/api/v1/comparisons/selection", json=body(), headers=HEADERS)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["ranking"] == original["ranking"]
    assert data["maintenance"]["common_window"] == {"start": result["history_start"], "end": result["history_end"]}
    for row in data["maintenance"]["repositories"]:
        repository_id = row["repository_id"]
        pattern = client.get(f"/api/v1/repositories/{repository_id}/evaluation", headers=HEADERS).json()["data"]["maintenance_pattern"]
        assert row["pattern"] == pattern
        assert pattern["method"] == "machine_learning"
        assert pattern["display_name"] in {"持续提交型", "集中提交型", "提交波动型", "低提交活动型"}
        assert row["recent_activity_change"]["status"] == "available"
        assert pattern["source_run_id"] in data["report_markdown"]
        assert str(pattern["evidence"]["commit_total_12w"]) in data["report_markdown"]
        assert "最近 4 周实际变化" in data["report_markdown"]
        assert "未来 4 周活动趋势预测（M2）" in data["report_markdown"]
        assert pattern["display_name"] in data["report_markdown"]
        assert "近期活动异常提示（MAD 规则）" in data["report_markdown"]
        assert "未发现明显异常" in data["report_markdown"]
    exported = client.post("/api/v1/reports/selection.md", json=body(), headers=HEADERS)
    assert exported.status_code == 200 and exported.text == data["report_markdown"]
    assert "不参与规则得分" in exported.text
    assert "## 数据口径与适用性说明" in exported.text
    assert "## 技术选型辅助结论（规则与证据分别说明）" in exported.text
    assert "当前候选综合分并列" in exported.text
    assert "M1、M2 与 M3 只作为近期维护行为证据，不参与规则排名" in exported.text
    with factory() as session:
        session.delete(session.get(MaintenanceRun, 'maintenance-322'))
        session.commit()
    partial = client.post("/api/v1/comparisons/selection", json=body(), headers=HEADERS).json()["data"]
    rows = {row['repository_id']: row['pattern'] for row in partial['maintenance']['repositories']}
    assert partial['ranking'] == original['ranking'] and partial['maintenance']['common_window'] is None
    assert rows[321]['evidence'] and rows[322]['reason_code'] == 'not_collected'
    assert 'maintenance-321' in partial['report_markdown']
    assert '最近 4 周实际变化（统计事实）无法判定' in partial['report_markdown']
    assert '暂不提供未来 4 周活动趋势预测（M2）' in partial['report_markdown']
    assert '尚未采集维护活动数据' in partial['report_markdown']


def test_report_distinguishes_zero_default_branch_commits_from_positive_pr_activity(backend_client, monkeypatch, tmp_path):
    client, factory, _ = backend_client
    seed(factory)
    setup_settings(monkeypatch, tmp_path)
    result, _ = maintenance_seed(factory, tmp_path)
    for repository_id in (321, 322):
        weeks = [{**row, "commits": 0, "prs_created": 314 if index == 11 else 0}
                 for index, row in enumerate(result["weeks"])]
        source = {**result, "repository_id": repository_id, "weeks": weeks}
        run_id = f"hello-world-{repository_id}"
        archive = archive_json(repository_id, run_id, "maintenance", source, root=tmp_path)
        with factory() as session:
            persist_maintenance(session, run_id, source, archive)
            session.commit()

    data = client.post("/api/v1/comparisons/selection", json=body(), headers=HEADERS).json()["data"]
    assert data["status"] == "available"
    for row in data["maintenance"]["repositories"]:
        assert row["pattern"]["evidence"]["commit_total_12w"] == 0
        assert row["pattern"]["display_name"] == "低提交活动型"
        assert row["pattern"]["evidence"]["pr_created_total_12w"] == 314
    assert "低提交活动型" in data["report_markdown"]
    assert "最近 12 周默认分支 Commit 0" in data["report_markdown"]
    assert "同期 PR 创建量为 314（覆盖完整）；这不代表仓库没有 PR 或社区协作活动。" in data["report_markdown"]
