"""训练与线上共用的 52 个完整 UTC 周维护行为特征。"""
import hashlib
import json
import math
from datetime import timedelta

from backend.app.core.clock import iso_z, parse_github_datetime

SCHEMA_VERSION = 'maintenance-shape-v1'
SHAPE_NAMES = ('commit_active_fraction', 'commit_longest_zero_fraction', 'commit_log_cv',
               'commit_log_recent_ratio', 'pr_active_fraction', 'pr_log_cv', 'pr_commit_log_ratio')
SCALE_NAMES = ('commit_log_total', 'pr_log_total')


class InsufficientMaintenanceData(ValueError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _time(value):
    if not isinstance(value, str) or not (value.endswith('Z') or value.endswith('+00:00')):
        raise InsufficientMaintenanceData('invalid_week_boundary')
    result = parse_github_datetime(value)
    if result is None:
        raise InsufficientMaintenanceData('invalid_week_boundary')
    return result


def _longest_zero(values):
    best = current = 0
    for value in values:
        current = current + 1 if value == 0 else 0
        best = max(best, current)
    return best


def _log_cv(values):
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return math.log1p(math.sqrt(variance) / (mean + 1))


def build_maintenance_features(weeks):
    """缺失、部分覆盖、非法真零和非连续周不能生成特征。"""
    if not isinstance(weeks, list) or len(weeks) != 52:
        raise InsufficientMaintenanceData('insufficient_history')
    commits, prs, previous = [], [], None
    for row in weeks:
        if not isinstance(row, dict):
            raise InsufficientMaintenanceData('invalid_week')
        start, end = _time(row.get('week_start_utc')), _time(row.get('week_end_exclusive_utc'))
        if start.weekday() != 0 or start.hour or start.minute or start.second or start.microsecond or end - start != timedelta(days=7) or (previous is not None and start != previous):
            raise InsufficientMaintenanceData('noncontiguous_weeks')
        previous = end
        for field, coverage, output in (('commits', 'commit_coverage', commits), ('prs_created', 'pr_created_coverage', prs)):
            state, count = row.get(coverage), row.get(field)
            if state not in {'complete', 'true_zero'}:
                raise InsufficientMaintenanceData('incomplete_coverage')
            if type(count) is not int or count < 0 or (state == 'true_zero' and count != 0):
                raise InsufficientMaintenanceData('invalid_count_or_true_zero')
            output.append(count)
    commit_total, pr_total = sum(commits), sum(prs)
    recent = sum(commits[-12:]) / 12
    previous_mean = sum(commits[:40]) / 40
    features = {
        'commit_log_total': math.log1p(commit_total), 'pr_log_total': math.log1p(pr_total),
        'commit_active_fraction': sum(value > 0 for value in commits) / 52,
        'commit_longest_zero_fraction': _longest_zero(commits) / 52,
        'commit_log_cv': _log_cv(commits),
        'commit_log_recent_ratio': math.log1p(min(5, (recent + 1) / (previous_mean + 1))),
        'pr_active_fraction': sum(value > 0 for value in prs) / 52,
        'pr_log_cv': _log_cv(prs),
        'pr_commit_log_ratio': math.log1p((pr_total + 1) / (commit_total + 1)),
    }
    canonical = json.dumps(weeks, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
    return {'feature_schema_version': SCHEMA_VERSION, 'as_of_utc': iso_z(previous), 'lookback_weeks': 52,
            'feature_values': features, 'source_sha256': hashlib.sha256(canonical).hexdigest(),
            'evidence': {'commits_52w': commit_total, 'prs_created_52w': pr_total,
                         'commit_active_weeks': sum(value > 0 for value in commits),
                         'pr_active_weeks': sum(value > 0 for value in prs),
                         'longest_zero_commit_weeks': _longest_zero(commits),
                         'commit_recent_12_week_mean': recent, 'commit_previous_40_week_mean': previous_mean}}
