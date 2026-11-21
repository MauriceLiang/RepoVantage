from datetime import datetime, timedelta

import pytest

from backend.app.analytics.course_ml_features import (
    FEATURE_SCHEMA_VERSION, InsufficientCourseData,
    build_weekly_features, recent_commit_change, trend_label,
)
from backend.app.core.clock import iso_z


def weeks(commits, prs=None, *, pr_coverage="complete"):
    start = datetime(2026, 1, 5)
    rows = []
    for index, count in enumerate(commits):
        lower = start + timedelta(weeks=index)
        pr_count = (prs[index] if prs is not None else 0)
        rows.append({"week_start_utc": iso_z(lower), "week_end_exclusive_utc": iso_z(lower + timedelta(weeks=1)),
                     "commits": count, "prs_created": pr_count,
                     "commit_coverage": "true_zero" if count == 0 else "complete",
                     "pr_created_coverage": "true_zero" if pr_count == 0 and pr_coverage == "complete" else pr_coverage})
    return rows


def test_features_use_latest_twelve_weeks_and_pr_is_optional():
    rows = weeks(list(range(1, 25)), list(range(24)))
    rows[0]["pr_created_coverage"] = "partial"
    result = build_weekly_features(rows)
    assert result["feature_schema_version"] == FEATURE_SCHEMA_VERSION
    assert result["window_weeks"] == 24
    assert result["facts"]["commit_total"] == sum(range(1, 25))
    assert result["pattern_features"]["commit_active_fraction"] == 1
    assert result["optional_pr_features"] is None
    assert result["facts"]["pr_created_total"] is None


def test_incomplete_commit_coverage_is_not_converted_to_zero():
    rows = weeks([1] * 12)
    rows[3]["commit_coverage"] = "partial"
    with pytest.raises(InsufficientCourseData, match="incomplete_commits_coverage"):
        build_weekly_features(rows)


def test_short_repository_keeps_facts_without_model_features():
    result = build_weekly_features(weeks([0, 1, 0, 2]))
    assert result["facts"]["commit_observed_weeks"] == 4
    assert result["facts"]["commit_total"] == 3
    assert result["pattern_features"] is None
    assert result["trend_features"] is None


def test_sparse_trend_boundaries():
    assert trend_label([0, 0, 0, 0], [1, 0, 0, 0]) == "基本稳定"
    assert trend_label([0, 0, 0, 0], [1, 1, 1, 0]) == "上升"


def test_recent_commit_change_reports_fact_windows_and_threshold_labels():
    result = recent_commit_change(weeks([5] * 4 + [0, 0, 0, 1]))
    assert result["status"] == "available"
    assert result["previous_4w_commits"] == 20 and result["recent_4w_commits"] == 1
    assert result["trend"] == "近期下降"
    assert result["previous_window_start_utc"] == "2026-01-05T00:00:00Z"
    assert result["previous_window_end_exclusive_utc"] == "2026-02-02T00:00:00Z"
    assert result["recent_window_start_utc"] == "2026-02-02T00:00:00Z"
    assert result["recent_window_end_exclusive_utc"] == "2026-03-02T00:00:00Z"

    assert recent_commit_change(weeks([0] * 8))["trend"] == "近期基本稳定"
    assert recent_commit_change(weeks([0] * 4 + [1, 0, 0, 0]))["trend"] == "近期基本稳定"
    assert recent_commit_change(weeks([0] * 4 + [4, 0, 0, 0]))["trend"] == "近期上升"
    assert recent_commit_change(weeks([20, 20, 20, 21, 24, 24, 24, 27]))["trend"] == "近期基本稳定"


def test_recent_commit_change_does_not_infer_from_short_or_incomplete_history():
    short = recent_commit_change(weeks([1] * 7))
    assert short["status"] == "insufficient_data"
    assert short["reason_code"] == "short_history"
    assert short["recent_4w_commits"] is None

    rows = weeks([0] * 4 + [1] * 4)
    rows[-1]["commit_coverage"] = "partial"
    partial = recent_commit_change(rows)
    assert partial["status"] == "partial_data"
    assert partial["reason_code"] == "incomplete_commits_coverage"
    assert partial["previous_4w_commits"] is None and partial["trend"] is None
