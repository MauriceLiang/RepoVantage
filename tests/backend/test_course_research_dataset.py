from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.clock import iso_z
from backend.app.persistence.db import Base
from backend.app.persistence.models import (
    DatasetRepository,
    MaintenanceRun,
    MaintenanceWeek,
    Repository,
    RepositorySnapshot,
)
from backend.app.pipeline.raw_archive import archive_json
from backend.app.schemas.ml_evaluation import SelectionRequest, SelectionWeights
from backend.app.services import maintenance
from backend.app.services.course_research_dataset import (
    BUNDLE_ROOT,
    COURSE_RESEARCH_ID,
    course_research_insights,
    import_course_research_bundle,
    verify_course_research_bundle,
)
from backend.app.services.insight_comparison import compare_insights
from backend.app.services.ml_evaluation import repository_evaluation
from backend.app.services.repositories import ensure_default_datasets
from backend.app.services.selection import selection_markdown, selection_report


def _isolated_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'course.db'}")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def test_course_bundle_import_is_additive_and_supports_analysis_comparison_and_report(tmp_path, monkeypatch):
    bundle = verify_course_research_bundle(BUNDLE_ROOT)
    assert len(bundle["repositories"]) == 300
    assert len(bundle["weeks"]) == 3600
    assert bundle["metadata"]["source_sha256"] == "5a463e44da2260d943a7851c872277984552fba3034e12eb8d5bb14c7c2c148d"

    archive_root = tmp_path / "raw"
    monkeypatch.setattr(maintenance, "get_settings", lambda: SimpleNamespace(raw_data_path=archive_root, base_refresh_hours=24))
    engine, factory = _isolated_factory(tmp_path)
    repository_ids = [row["repository_id"] for row in bundle["repositories"]]
    older_name = bundle["repositories"][0]["full_name"]
    newer_id = repository_ids[0]
    try:
        with factory() as session:
            ensure_default_datasets(session)
            repository = bundle["repositories"][0]
            session.add(Repository(
                repository_id=newer_id, full_name=older_name, html_url=repository["html_url"],
                description="preserve existing description", language="LocalLanguage",
            ))
            session.flush()
            session.add(RepositorySnapshot(
                repository_id=newer_id, collected_at=datetime(2026, 11, 10, tzinfo=timezone.utc),
                stars=999, forks=9, open_issues_and_pr_count=1, pushed_at=None, github_updated_at=None,
                response_etag=None, source_http_status=200, source_archive_path=None, valid=True,
            ))
            session.commit()

            result = import_course_research_bundle(session, archive_root=archive_root)
            assert result["repositories"] == 300
            assert result["repository_records_created"] == 299
            assert result["library_memberships_added"] == 300
            assert result["maintenance_runs_added"] == 300
            assert result["maintenance_weeks_added"] == 3600
            assert result["snapshots_skipped_newer"] == 1
            assert result["snapshots_added"] == 299
            assert session.get(Repository, newer_id).description == "preserve existing description"
            assert session.get(Repository, newer_id).language == "LocalLanguage"
            assert session.get(RepositorySnapshot, 1).stars == 999
            assert session.scalar(select(func.count()).select_from(DatasetRepository).where(DatasetRepository.dataset_id == COURSE_RESEARCH_ID)) == 300
            assert session.scalar(select(func.count()).select_from(DatasetRepository).where(DatasetRepository.dataset_id == "library-default")) == 300
            assert session.scalar(select(func.count()).select_from(MaintenanceRun)) == 300
            assert session.scalar(select(func.count()).select_from(MaintenanceWeek)) == 3600

            duplicate = import_course_research_bundle(session, archive_root=archive_root)
            assert duplicate["already_imported"] is True

            insights = course_research_insights(session, COURSE_RESEARCH_ID)
            assert insights["sample_size"] == 300
            assert insights["course_summary"]["split_counts"] == {"train": 150, "test": 150}
            assert sum(row["sample_role"] == "train" for row in insights["rows"]) == 150
            assert sum(row["sample_role"] == "test" for row in insights["rows"]) == 150
            assert insights["summary"]["issue_median_hours"]["count"] == 0

            train_id = next(value for value in repository_ids if bundle["role_by_id"][value] == "train")
            test_id = next(value for value in repository_ids if bundle["role_by_id"][value] == "test")
            evaluation = repository_evaluation(session, train_id)
            assert evaluation["research_sample"]["sample_role"] == "train"
            assert evaluation["research_sample"]["dataset_id"] == COURSE_RESEARCH_ID

            comparison = compare_insights(session, [train_id, test_id], mode="same_period", window_days=90)
            assert comparison["comparison_basis"]["status"] == "comparable"
            assert all(row["source_kind"] == "course_research_historical_snapshot" for row in comparison["repositories"])
            assert all(row["sample_role"] in {"train", "test"} for row in comparison["repositories"])
            assert all(row["metrics"]["commits_weekly_mean"]["quality"] == "ready" for row in comparison["repositories"])
            assert all(row["metrics"]["issue_median_hours"]["value"] is None for row in comparison["repositories"])

            body = SelectionRequest(
                repository_ids=[train_id, test_id], scenario="同类开源库比较", candidate_group="课程样例",
                candidates_confirmed=True, window_days=90, allowed_languages=[], allowed_licenses=[],
                weights=SelectionWeights(commits_weekly_mean=1),
            )
            report = selection_report(session, body)
            assert report["status"] == "available"
            assert len(report["ranking"]) == 2
            markdown = selection_markdown(report)
            assert "课程研究历史快照" in markdown
            assert "课程实验角色为训练组" in markdown
            assert "课程实验角色为测试组留出仓库" in markdown
    finally:
        engine.dispose()


def test_newer_online_maintenance_observation_wins_over_course_snapshot(tmp_path, monkeypatch):
    bundle = verify_course_research_bundle(BUNDLE_ROOT)
    archive_root = tmp_path / "raw"
    monkeypatch.setattr(maintenance, "get_settings", lambda: SimpleNamespace(raw_data_path=archive_root, base_refresh_hours=24))
    engine, factory = _isolated_factory(tmp_path)
    repository = bundle["repositories"][0]
    repository_id = repository["repository_id"]
    try:
        with factory() as session:
            ensure_default_datasets(session)
            import_course_research_bundle(session, archive_root=archive_root)
            now = datetime.now(timezone.utc).replace(microsecond=0)
            end = now.replace(hour=0, minute=0, second=0) - timedelta(days=now.weekday())
            start = end - timedelta(weeks=12)
            weeks = [{
                "week_start_utc": iso_z(start + timedelta(weeks=index)),
                "week_end_exclusive_utc": iso_z(start + timedelta(weeks=index + 1)),
                "commits": index + 1, "prs_created": 0,
                "commit_coverage": "complete", "pr_created_coverage": "true_zero",
            } for index in range(12)]
            result = {"repository_id": repository_id, "status": "complete", "lookback_weeks": 12,
                      "history_start": iso_z(start), "history_end": iso_z(end), "captured_at": iso_z(now),
                      "head_sha": "b" * 40, "weeks": weeks, "limitations": []}
            archive = archive_json(repository_id, "online-newer", "maintenance-12w", result, root=archive_root)
            maintenance.persist_maintenance(session, "online-newer", result, archive)
            session.commit()

            evaluation = repository_evaluation(session, repository_id)
            assert evaluation["research_sample"]["sample_role"] in {"train", "test"}
            assert evaluation["maintenance_pattern"]["source_run_id"] == "online-newer"
            comparison = compare_insights(session, [repository_id, bundle["repositories"][1]["repository_id"]], "individual_periods", 90)
            online_row = next(row for row in comparison["repositories"] if row["repository_id"] == repository_id)
            assert online_row["source_kind"] == "maintenance_weekly_aggregation"
            assert online_row["maintenance_source_run_id"] == "online-newer"
    finally:
        engine.dispose()
