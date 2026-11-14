from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from backend.app.analytics.maintenance_features import InsufficientMaintenanceData, build_maintenance_features
from backend.app.core.clock import iso_z


def rows():
    start = datetime(2025, 11, 3)
    return [{'week_start_utc': iso_z(start + timedelta(weeks=i)), 'week_end_exclusive_utc': iso_z(start + timedelta(weeks=i+1)),
             'commits': i % 3, 'prs_created': i % 2, 'commit_coverage': 'complete', 'pr_created_coverage': 'complete'} for i in range(52)]


def test_52_week_features_include_only_covered_real_observations():
    weeks = rows()
    result = build_maintenance_features(weeks)
    assert result['lookback_weeks'] == 52
    assert result['as_of_utc'] == '2026-11-02T00:00:00Z'
    assert result['evidence']['commits_52w'] == sum(row['commits'] for row in weeks)
    assert result['evidence']['prs_created_52w'] == 26
    assert result['source_sha256'] == build_maintenance_features(deepcopy(weeks))['source_sha256']


@pytest.mark.parametrize('change,reason', [
    (lambda w: w.pop(), 'insufficient_history'),
    (lambda w: w[0].update(commit_coverage='partial'), 'incomplete_coverage'),
    (lambda w: w[1].update(commit_coverage='true_zero'), 'invalid_count_or_true_zero'),
    (lambda w: w[2].update(prs_created=None), 'invalid_count_or_true_zero'),
    (lambda w: w[1].update(week_start_utc='2025-11-11T00:00:00Z'), 'noncontiguous_weeks'),
])
def test_bad_coverage_or_history_never_becomes_zero(change, reason):
    weeks = rows()
    change(weeks)
    with pytest.raises(InsufficientMaintenanceData, match=reason):
        build_maintenance_features(weeks)


def test_proven_zero_is_valid():
    weeks = rows()
    for week in weeks:
        week.update(commits=0, prs_created=0, commit_coverage='true_zero', pr_created_coverage='true_zero')
    result = build_maintenance_features(weeks)
    assert result['evidence']['longest_zero_commit_weeks'] == 52
    assert result['evidence']['commits_52w'] == 0
