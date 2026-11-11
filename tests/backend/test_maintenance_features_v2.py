from copy import deepcopy

import pytest

from backend.app.analytics.maintenance_features import InsufficientMaintenanceData
from backend.app.analytics.maintenance_features_v2 import TEMPORAL_NAMES, build_temporal_features
from tests.backend.test_maintenance_features import rows


def test_temporal_shape_is_invariant_under_uniform_activity_scaling():
    original = rows()
    scaled = deepcopy(original)
    for row in scaled:
        row['commits'] *= 10
        row['prs_created'] *= 10
    first, second = build_temporal_features(original), build_temporal_features(scaled)
    for name in TEMPORAL_NAMES:
        assert first['feature_values'][name] == pytest.approx(second['feature_values'][name], abs=1e-12)
    assert first['feature_values']['commit_log_total'] != second['feature_values']['commit_log_total']


def test_small_activity_is_outside_predeclared_scope_not_a_zero_filled_pattern():
    weeks = rows()
    for row in weeks:
        row['commits'] = 0
    with pytest.raises(InsufficientMaintenanceData, match='below_activity_scope'):
        build_temporal_features(weeks)
