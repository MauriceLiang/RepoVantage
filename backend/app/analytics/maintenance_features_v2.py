"""独立于活动规模的周序列形态候选，适用于事件量足够的仓库。"""
import math

from backend.app.analytics.maintenance_features import InsufficientMaintenanceData, build_maintenance_features

SCHEMA_VERSION = 'maintenance-temporal-shape-v2'
TEMPORAL_NAMES = ('commit_recent_share', 'commit_top4_share', 'commit_entropy', 'commit_active_cv',
                  'pr_recent_share', 'pr_top4_share', 'pr_entropy', 'pr_active_cv', 'commit_pr_week_overlap')


def _shape(values):
    total = sum(values)
    active = [value for value in values if value > 0]
    mean = total / len(active)
    cv = math.sqrt(sum((value - mean)**2 for value in active) / len(active)) / mean
    entropy = -sum((value/total) * math.log(value/total) for value in active) / math.log(52)
    return [sum(values[-12:]) / total, sum(sorted(values, reverse=True)[:4]) / total, entropy, math.log1p(cv)]


def build_temporal_features(weeks):
    base = build_maintenance_features(weeks)
    commits = [row['commits'] for row in weeks]
    prs = [row['prs_created'] for row in weeks]
    if sum(commits) < 20 or sum(prs) < 10:
        raise InsufficientMaintenanceData('below_activity_scope')
    active_commit = {index for index, count in enumerate(commits) if count > 0}
    active_pr = {index for index, count in enumerate(prs) if count > 0}
    values = _shape(commits) + _shape(prs) + [len(active_commit & active_pr) / len(active_commit | active_pr)]
    return {**base, 'feature_schema_version': SCHEMA_VERSION,
            'feature_values': {**{name: base['feature_values'][name] for name in ('commit_log_total', 'pr_log_total')},
                               **dict(zip(TEMPORAL_NAMES, values))}}
