from backend.app.services.course_ml_dashboard import course_machine_learning_evaluation


HEADERS = {"X-Internal-Api-Key": "test-internal-key"}


def test_course_machine_learning_dashboard_uses_frozen_holdout_artifacts(backend_client):
    client, _, _ = backend_client
    response = client.get("/api/v1/research/course-ml-evaluation", headers=HEADERS)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["dataset_version"] == "course-150-150-v1"
    assert data["m1"]["status"] == "candidate"
    assert sum(item["count"] for item in data["m1"]["cluster_counts"]) == 150
    assert data["m2"]["sample_count"] == 150
    assert sum(data["m2"]["actual_class_counts"].values()) == 150
    assert sum(sum(row) for row in data["m2"]["confusion_matrix"]) == 150
    assert data["m2"]["selected_candidate"]["model_id"] == "logistic_regression_c0.1_balanced"
    assert len(data["m2"]["baselines"]) == 2
    assert data["m3"]["timeline_available"] is False
    assert "逐周" in data["m3"]["timeline_reason"]


def test_course_machine_learning_dashboard_requires_internal_api_key(backend_client):
    client, _, _ = backend_client
    response = client.get("/api/v1/research/course-ml-evaluation")
    assert response.status_code == 401
