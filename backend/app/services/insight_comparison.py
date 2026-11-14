import json
from collections import Counter
from statistics import mean
from sqlalchemy import func, select

from backend.app.analytics.metrics import numeric_summary, spearman_summary
from backend.app.core.clock import iso_z, parse_github_datetime
from backend.app.core.exceptions import AppError
from backend.app.persistence.models import Dataset, DatasetRepository, MaintenanceRun, Repository
from backend.app.services.insights import repository_insights, repository_insights_for_window
from backend.app.services.repositories import STANDARD_TEST_ID

INSIGHT_FIELDS = {'commits_weekly_mean': ('commit_activity', 'commits/week'), 'issue_median_hours': ('issue_resolution', 'hours'), 'pr_median_hours': ('pr_merges', 'hours'), 'release_interval_days': ('release_cadence', 'days')}


def metric_value(result, key, *, include_observed=False):
    metric = result['insights'].get(INSIGHT_FIELDS[key][0])
    if not metric:
        return None
    status = metric['quality']['status']
    if status != 'ready' and not (include_observed and status == 'partial'):
        return None
    if key == 'commits_weekly_mean':
        points = [p['value'] for p in metric['weekly'] if p['quality'] == 'ready']
        return mean(points) if points else None
    return metric.get('median_interval_days' if key == 'release_interval_days' else 'median_hours')


def _maintenance_commit_fallback(session, result, window_days, *, prefer_recent=False):
    """Use an integrity-checked weekly maintenance snapshot when it is newer than event analysis."""
    if result.get('origin') == 'course-test-events-v1' and not prefer_recent:
        return None
    from backend.app.services.maintenance import maintenance_observation

    observation = maintenance_observation(session, result['repository_id'])
    pattern = observation['maintenance_pattern']
    if pattern['status'] not in {'available', 'unclassified'} or not observation['weeks']:
        return None
    analyzed_at = parse_github_datetime(result.get('analyzed_at'))
    captured_at = parse_github_datetime(pattern.get('collected_at'))
    if analyzed_at and captured_at and analyzed_at > captured_at:
        return None
    week_count = {30: 4, 90: 12, 180: 24}.get(window_days)
    if not week_count:
        return None
    weeks = observation['weeks'][-week_count:]
    if (len(weeks) != week_count
            or any(row['commit_coverage'] not in {'complete', 'true_zero'} for row in weeks)
            or any(weeks[index]['week_end_exclusive_utc'] != weeks[index + 1]['week_start_utc'] for index in range(len(weeks) - 1))):
        return None
    start = parse_github_datetime(weeks[0]['week_start_utc'])
    end = parse_github_datetime(weeks[-1]['week_end_exclusive_utc'])
    if not start or not end or (end - start).total_seconds() < window_days * 86400 * 0.8:
        return None
    points = [{
        'start': row['week_start_utc'], 'end': row['week_end_exclusive_utc'], 'value': row['commits'],
        'quality': 'ready', 'complete_week': True,
    } for row in weeks]
    pattern_run = session.get(MaintenanceRun, pattern['source_run_id'])
    details = {}
    if pattern_run and pattern_run.details_json:
        try:
            details = json.loads(pattern_run.details_json)
        except (TypeError, ValueError):
            details = {}
    source_kind = 'course_research_historical_snapshot' if details.get('data_source') == 'course_research_historical_snapshot' else 'maintenance_weekly_aggregation'
    metric = {
        'quality': {'status': 'ready', 'valid_samples': week_count, 'reason': None},
        'weekly': points, 'window_start': iso_z(start), 'window_end': iso_z(end),
        'source_run_id': pattern['source_run_id'], 'source_kind': source_kind,
    }
    result['insights'] = dict(result.get('insights') or {})
    result['insights']['commit_activity'] = metric
    result['window_start'], result['window_end'] = iso_z(start), iso_z(end)
    result['analyzed_at'] = pattern.get('collected_at')
    result['window_available'] = True
    result['window_reason'] = None
    result['comparison_source_kind'] = source_kind
    result['maintenance_source_run_id'] = pattern['source_run_id']
    result['run_id'] = None
    return source_kind


def compare_insights(session, ids, mode='same_period', window_days=90):
    """按可比较的时间口径对比 2 至 5 个仓库。

    同期对比仅在共同时间交集覆盖所选窗口至少 80% 时重新计算指标；
    各自周期模式保留每个仓库自己的窗口。Commit 均值只使用完整 UTC 自然周，
    且仅在同期模式下要求各仓库使用共同的完整周。
    """
    if not 2 <= len(ids) <= 5 or len(set(ids)) != len(ids):
        raise AppError(422, 'VALIDATION_ERROR', '请选择2–5个不同仓库')
    if mode not in {'same_period', 'individual_periods'}:
        raise AppError(422, 'VALIDATION_ERROR', '不支持的对比方式')
    if window_days not in {30, 90, 180}:
        raise AppError(422, 'VALIDATION_ERROR', '分析范围只支持 30、90 或 180 天')
    from backend.app.services.course_test_events import historical_insights
    results = [
        historical_insights(session, id, window_days) or repository_insights(session, id, window_days=window_days)
        for id in ids
    ]
    for result in results:
        _maintenance_commit_fallback(session, result, window_days, prefer_recent=mode == 'individual_periods')
    repos = [session.get(Repository, id) for id in ids]
    candidate_windows = [(result['window_start'], result['window_end']) for result in results]
    comparison_basis = {
        'scope': 'shared_observation' if mode == 'same_period' else 'repository_windows',
        'requested_window_days': window_days,
        'shared_window': None,
        'effective_days': None,
        'minimum_coverage_ratio': 0.8 if mode == 'same_period' else None,
        'minimum_effective_days': round(window_days * 0.8, 6) if mode == 'same_period' else None,
        'status': 'separate_windows' if mode == 'individual_periods' else 'not_comparable',
        'reason_code': 'INDIVIDUAL_WINDOWS_ASYNC' if mode == 'individual_periods' else 'MISSING_REPOSITORY_WINDOW',
        'reason': '各仓库分别使用自身分析窗口；结果不代表同期对比。' if mode == 'individual_periods' else '至少一个仓库没有覆盖所选窗口的分析运行。',
    }
    shared_start = shared_end = None
    if mode == 'same_period' and all(result['window_available'] for result in results):
        starts = [parse_github_datetime(start) for start, _ in candidate_windows]
        ends = [parse_github_datetime(end) for _, end in candidate_windows]
        if all(starts) and all(ends):
            shared_start, shared_end = max(starts), min(ends)
            if shared_end <= shared_start:
                shared_start = shared_end = None
                comparison_basis.update({
                    'reason_code': 'NO_SHARED_WINDOW',
                    'reason': '所选仓库的分析窗口没有时间交集。',
                })
            else:
                effective_days = (shared_end - shared_start).total_seconds() / 86400
                comparison_basis['shared_window'] = {'start': iso_z(shared_start), 'end': iso_z(shared_end)}
                comparison_basis['effective_days'] = round(effective_days, 6)
                if effective_days + 1e-9 >= window_days * 0.8:
                    comparison_basis.update({'status': 'comparable', 'reason_code': None, 'reason': None})
                    results = [result if result.get('comparison_source_kind') else repository_insights_for_window(session, result['repository_id'], shared_start, shared_end, result) for result in results]
                else:
                    comparison_basis.update({
                        'reason_code': 'SHARED_WINDOW_BELOW_THRESHOLD',
                        'reason': f'共同观察窗口为 {effective_days:.1f} 天，少于所选 {window_days} 天窗口的 80%。',
                    })

    common_weeks = None
    for result in results:
        weeks = {p['start'] for p in result['insights'].get('commit_activity', {}).get('weekly', []) if p['complete_week'] and p['quality'] == 'ready' and p['value'] is not None}
        common_weeks = weeks if common_weeks is None else common_weeks & weeks
    warnings = ['项目类型未分类；活动规模与处理耗时不能直接判定项目优劣。']
    if len({r.language for r in repos}) > 1:
        warnings.append('仓库主语言不同，请确认用途相近。')
    windows = set(candidate_windows)
    same_observation_window = len(windows) == 1 and all(result['window_available'] for result in results)
    if mode == 'same_period' and comparison_basis['status'] != 'comparable':
        warnings.append(comparison_basis['reason'])
    elif mode == 'individual_periods' and not same_observation_window:
        warnings.append('各仓库分别使用自身最近一次分析中的完整周与可用指标；观察窗口可能不同，适合查看各自活跃度和处理节奏，不代表同期对比。')
    rows = []
    course_dataset = session.get(Dataset, 'course-research-300-v1')
    course_metadata = {}
    if course_dataset and course_dataset.source_metadata_json:
        try:
            course_metadata = json.loads(course_dataset.source_metadata_json)
        except (TypeError, ValueError):
            course_metadata = {}
    course_snapshot_as_of = course_metadata.get('data_as_of') if any(
        result.get('comparison_source_kind') == 'course_research_historical_snapshot'
        or result.get('origin') == 'course-test-events-v1' for result in results
    ) else None
    if course_snapshot_as_of:
        warnings.append(f'课程研究资料来自固定历史快照，仓库资料采集截至 {course_snapshot_as_of}；不代表实时状态。')
    for repo, result in zip(repos, results):
        if not result.get('window_available', result.get('run_id') is not None):
            warnings.append(f"{repo.full_name}：{result['window_reason']}")
        values = {}
        metric = result['insights'].get('commit_activity')
        ready_weeks = [
            point
            for point in (metric or {}).get('weekly', [])
            if point['complete_week'] and point['quality'] == 'ready' and point['value'] is not None
        ]
        selected_weeks = ready_weeks if mode == 'individual_periods' else [
            point for point in ready_weeks if point['start'] in (common_weeks or set())
        ]
        weekly_commits = selected_weeks
        course_membership = session.get(DatasetRepository, ('course-research-300-v1', repo.repository_id))
        for key, (name, unit) in INSIGHT_FIELDS.items():
            metric = result['insights'].get(name)
            value = metric_value(result, key, include_observed=True)
            comparable = (mode == 'individual_periods' or comparison_basis['status'] == 'comparable') and value is not None
            start, end = (metric['window_start'], metric['window_end']) if metric else (None, None)
            if key == 'commits_weekly_mean':
                points = selected_weeks
                value = mean(p['value'] for p in points) if points else None
                comparable = value is not None
                start, end = (points[0]['start'], points[-1]['end']) if points else (None, None)
            if mode == 'same_period' and comparison_basis['status'] != 'comparable':
                comparable = False
            if comparison_basis['status'] == 'not_comparable' and mode == 'same_period':
                reason_code = comparison_basis['reason_code']
            elif key == 'commits_weekly_mean' and value is None and metric and metric['quality']['status'] == 'ready':
                reason_code = 'NO_COMMON_COMPLETE_UTC_WEEK' if mode == 'same_period' else 'NO_COMPLETE_UTC_WEEK'
            elif metric and metric['quality']['status'] != 'ready':
                reason_code = 'PARTIAL_OBSERVATION' if comparable and metric['quality']['status'] == 'partial' else 'METRIC_QUALITY_NOT_READY'
            elif value is None:
                reason_code = 'NO_VALID_SAMPLES'
            else:
                reason_code = None
            values[key] = {
                'value': value if comparable else None,
                'unit': unit,
                'comparable': comparable,
                'valid_samples': len(points) if key == 'commits_weekly_mean' else metric['quality']['valid_samples'] if metric else 0,
                'source_run_id': metric.get('source_run_id') if metric else None,
                'source_kind': metric.get('source_kind') if metric else None,
                'quality': metric['quality']['status'] if metric else 'missing',
                'reason_code': reason_code,
                'reason': comparison_basis['reason'] if reason_code in {'NO_SHARED_WINDOW', 'MISSING_REPOSITORY_WINDOW', 'SHARED_WINDOW_BELOW_THRESHOLD'} else metric['quality'].get('reason') if metric else None,
                'window_start': start,
                'window_end': end,
            }
        original_start, original_end = candidate_windows[len(rows)]
        rows.append({
            'repository_id': repo.repository_id,
            'full_name': repo.full_name,
            'language': repo.language,
            'created_at': iso_z(repo.created_at),
            'analyzed_at': result['analyzed_at'],
            'run_id': result['run_id'],
            'source_kind': result.get('comparison_source_kind') or ('course_research_historical_snapshot' if result.get('origin') == 'course-test-events-v1' else None),
            'maintenance_source_run_id': result.get('maintenance_source_run_id'),
            'sample_role': course_membership.selection_tier if course_membership else None,
            'window_start': result['window_start'],
            'window_end': result['window_end'],
            'source_window_start': original_start,
            'source_window_end': original_end,
            'window_available': result.get('window_available', result.get('run_id') is not None),
            'window_reason': result.get('window_reason'),
            'metrics': values,
            'weekly_commits': weekly_commits,
        })
    return {'metric_version': 'insights-v1', 'timezone': 'UTC', 'mode': mode, 'requested_window_days': window_days, 'comparison_basis': comparison_basis, 'common_complete_weeks': len(common_weeks or []), 'course_snapshot_as_of': course_snapshot_as_of, 'repositories': rows, 'warnings': warnings}


def research_insights(session, dataset_id, analysis_mode='formal'):
    dataset = session.get(Dataset, dataset_id)
    expected_type = {'formal': 'research', 'exploratory': 'featured', 'course': 'research'}.get(analysis_mode)
    if expected_type is None:
        raise AppError(422, 'VALIDATION_ERROR', '不支持的研究分析模式')
    if analysis_mode == 'course':
        if dataset_id not in {'course-research-300-v1', STANDARD_TEST_ID} or dataset is None or dataset.type != 'research':
            raise AppError(422, 'VALIDATION_ERROR', '课程研究模式必须选择课程研究或标准测试数据集')
        from backend.app.services.course_research_dataset import course_research_insights
        return course_research_insights(session, dataset_id)
    if dataset is None or dataset.type != expected_type:
        label = '研究数据集' if analysis_mode == 'formal' else '精选数据集'
        raise AppError(422, 'VALIDATION_ERROR', f'当前模式必须选择{label}')
    ids = session.scalars(select(DatasetRepository.repository_id).where(DatasetRepository.dataset_id == dataset_id, DatasetRepository.exclusion_status.is_(None)).order_by(DatasetRepository.repository_id)).all()
    membership_count = session.scalar(select(func.count()).select_from(DatasetRepository).where(DatasetRepository.dataset_id == dataset_id)) or 0
    rows = []
    windows = set()
    for id in ids:
        result = repository_insights(session, id, window_days=None)
        repo = session.get(Repository, id)
        values = {}
        metric_quality = {}
        for key, (name, _unit) in INSIGHT_FIELDS.items():
            metric = result['insights'].get(name)
            quality = metric.get('quality', {}) if metric else {}
            values[key] = metric_value(result, key)
            metric_quality[key] = {
                'status': quality.get('status', 'missing'),
                'coverage': quality.get('coverage', 'not_collected'),
                'valid_samples': quality.get('valid_samples', 0),
                'reason': quality.get('reason') or ('尚无事件级分析运行' if not result['run_id'] else '没有达到当前指标的有效样本'),
            }
        rows.append({'repository_id': id, 'full_name': repo.full_name, 'language': repo.language or '未知', 'analyzed_at': result['analyzed_at'], 'window_start': result['window_start'], 'window_end': result['window_end'], 'run_id': result['run_id'], 'values': values, 'metric_quality': metric_quality})
        if result['run_id']:
            windows.add((result['window_start'], result['window_end']))
    summary = {}
    metric_quality_summary = {}
    groups = []
    for key in INSIGHT_FIELDS:
        values = [r['values'][key] for r in rows if r['values'][key] is not None]
        summary[key] = {**numeric_summary(values), 'missing_count': len(rows) - len(values), 'missing_rate': (len(rows) - len(values)) / len(rows) if rows else None, 'unit': INSIGHT_FIELDS[key][1]}
        reasons = Counter(row['metric_quality'][key]['reason'] for row in rows if row['values'][key] is None)
        statuses = Counter(row['metric_quality'][key]['status'] for row in rows)
        metric_quality_summary[key] = {
            'valid_samples': len(values),
            'missing_count': len(rows) - len(values),
            'missing_rate': (len(rows) - len(values)) / len(rows) if rows else None,
            'status_counts': dict(sorted(statuses.items())),
            'missing_reasons': [{'reason': reason, 'count': count} for reason, count in sorted(reasons.items())],
        }
    for language in sorted({r['language'] for r in rows}):
        members = [r for r in rows if r['language'] == language]
        groups.append({'language': language, 'n': len(members), 'metrics': {key: numeric_summary([r['values'][key] for r in members if r['values'][key] is not None]) for key in INSIGHT_FIELDS}})
    paired = [r for r in rows if r['values']['issue_median_hours'] is not None and r['values']['pr_median_hours'] is not None]
    correlation = spearman_summary([r['values']['issue_median_hours'] for r in paired], [r['values']['pr_median_hours'] for r in paired]) if len(windows) <= 1 else {'n': len(paired), 'coefficient': None, 'p_value': None, 'note': '观察窗口不同，不计算相关性'}
    source_metadata = {}
    if dataset.source_metadata_json:
        try:
            source_metadata = json.loads(dataset.source_metadata_json)
        except (TypeError, ValueError):
            source_metadata = {}
    analyzable_members = sum(row['run_id'] is not None for row in rows)
    if analysis_mode == 'exploratory':
        dataset_status = 'analyzable' if analyzable_members else 'awaiting_collection'
        population_scope = 'curated_featured'
        limitations = [
            '精选数据集是策展样本，不是概率抽样；不得将结果外推为 GitHub 全体。',
            '只读取本地已保存的最新事件分析，不会因打开页面而请求 GitHub。',
            '仅ready输入进入指标；不同仓库采集时间可能不同，相关不代表因果。',
            '不足10个有效配对或变量无变化时不计算 Spearman。',
        ]
    else:
        dataset_status = 'pending_confirmation' if dataset.frozen_at is None else 'approved_not_imported' if membership_count == 0 else 'awaiting_collection' if analyzable_members == 0 else 'analyzable'
        population_scope = 'formal_research_sample'
        limitations = [
            '只分析当前研究成员的最新事件结果；冻结的是成员规则，不是永久锁定指标。',
            '仅ready输入进入分布；不同采集日期可能引入时间偏差，不代表GitHub总体，相关不代表因果。',
            '不足10个有效配对或变量无变化时不计算 Spearman。',
        ]
    return {
        'dataset_id': dataset_id,
        'analysis_mode': analysis_mode,
        'dataset_status': dataset_status,
        'population_scope': population_scope,
        'is_probability_sample': False,
        'dataset_version': source_metadata.get('version') or dataset.rules_version,
        'source': source_metadata.get('source') or dataset.description,
        'metric_version': 'insights-v1',
        'frozen_at': iso_z(dataset.frozen_at),
        'sample_size': len(rows),
        'analyzable_members': analyzable_members,
        'summary': summary,
        'metric_quality': metric_quality_summary,
        'groups': groups,
        'rows': rows,
        'correlation': correlation,
        'limitations': limitations,
    }
