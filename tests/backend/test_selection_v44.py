from sqlalchemy import func, select

from backend.app.persistence.models import (
    DatasetRepository,
    SelectionCapabilityEvidence,
    SelectionMetricSnapshot,
    SelectionScenario,
    SelectionScenarioCandidate,
    SelectionSnapshotRelease,
)
from backend.app.services.course_research_dataset import import_course_research_bundle
from backend.app.services.dataset_import import import_featured_bundle
from backend.app.services.selection_v44 import ensure_selection_v44


HEADERS = {"X-Internal-Api-Key": "test-internal-key"}


def _prepare_v44(factory, tmp_path):
    with factory() as session:
        import_featured_bundle(session)
        import_course_research_bundle(session, archive_root=tmp_path / "raw")
        ensure_selection_v44(session)


def test_v44_seed_is_idempotent_and_does_not_change_course_split(backend_client, tmp_path):
    _client, factory, _github = backend_client
    with factory() as session:
        import_featured_bundle(session)
        import_course_research_bundle(session, archive_root=tmp_path / "raw")
        split_before = session.execute(
            select(DatasetRepository.selection_tier, func.count())
            .where(DatasetRepository.dataset_id == "course-research-300-v1")
            .group_by(DatasetRepository.selection_tier)
        ).all()
        ensure_selection_v44(session)
        counts_after_first = (
            session.scalar(select(func.count()).select_from(SelectionScenario)),
            session.scalar(select(func.count()).select_from(SelectionScenarioCandidate)),
            session.scalar(select(func.count()).select_from(SelectionMetricSnapshot)),
            session.scalar(select(func.count()).select_from(SelectionSnapshotRelease)),
            session.scalar(select(func.count()).select_from(SelectionCapabilityEvidence)),
        )
        ensure_selection_v44(session)
        counts_after_second = (
            session.scalar(select(func.count()).select_from(SelectionScenario)),
            session.scalar(select(func.count()).select_from(SelectionScenarioCandidate)),
            session.scalar(select(func.count()).select_from(SelectionMetricSnapshot)),
            session.scalar(select(func.count()).select_from(SelectionSnapshotRelease)),
            session.scalar(select(func.count()).select_from(SelectionCapabilityEvidence)),
        )
        split_after = session.execute(
            select(DatasetRepository.selection_tier, func.count())
            .where(DatasetRepository.dataset_id == "course-research-300-v1")
            .group_by(DatasetRepository.selection_tier)
        ).all()

    assert counts_after_first == counts_after_second == (4, 18, 55, 4, 4)
    assert split_before == split_after == [("test", 150), ("train", 150)]


def test_selection_api_keeps_scenarios_separate_and_marks_supplements_pending(backend_client, tmp_path):
    client, factory, _github = backend_client
    _prepare_v44(factory, tmp_path)
    catalog = client.get("/api/v1/selection/scenarios", headers=HEADERS)
    assert catalog.status_code == 200
    assert [item["slug"] for item in catalog.json()["data"]["scenarios"]] == [
        "go-http-api", "python-api", "jvm-services", "frontend-ui",
    ]

    go = client.get("/api/v1/selection/scenarios/go-http-api", headers=HEADERS)
    assert go.status_code == 200
    candidates = go.json()["data"]["candidates"]
    assert {item["full_name"] for item in candidates} == {
        "gin-gonic/gin", "labstack/echo", "gofiber/fiber", "go-chi/chi",
    }
    chi = next(item for item in candidates if item["full_name"] == "go-chi/chi")
    assert chi["metric_collection_status"] == "pending_collection"
    assert chi["metrics_ready"] is False
    assert all(value is None for value in chi["metrics"].values())
    viz = client.get("/api/v1/selection/scenarios/go-http-api/viz", headers=HEADERS).json()["data"]
    assert viz["ranking_available"] is False
    assert len(viz["candidates"]) == 4
    assert sum(candidate["weekly_activity"] is not None for candidate in viz["candidates"]) == 3
    fiber = next(item for item in candidates if item["full_name"] == "gofiber/fiber")
    assert fiber["capabilities"][0]["capability_key"] == "net_http_middleware"
    assert fiber["capabilities"][0]["status"] == "conditional"
    assert "adaptor.md" in fiber["capabilities"][0]["evidence_url"]

    references = client.get("/api/v1/selection/references", headers=HEADERS)
    assert references.status_code == 200
    assert {item["full_name"] for item in references.json()["data"]["references"]} == {
        "django/django", "BurntSushi/ripgrep", "sharkdp/bat", "sharkdp/fd",
    }
