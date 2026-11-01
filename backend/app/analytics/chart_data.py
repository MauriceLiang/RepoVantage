"""根据已观察到的事件生成仓库组合图表数据。"""
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import timedelta
from statistics import median

from backend.app.analytics.insights import week_start, weekly
from backend.app.core.clock import iso_z, parse_github_datetime

PR_SCATTER_LIMIT = 1500


def _next_month(value):
    return value.replace(year=value.year + (value.month == 12), month=value.month % 12 + 1)


def _covers(source, lower, upper):
    """判断完整的数据源能否证明其覆盖整个指定区间。

    旧版完整分析没有保存 ``requested_interval``；此时仍以记录的分析窗口
    作为可用的覆盖证据，不能凭空补造更长的采集范围。
    """
    if source.get('coverage') != 'complete':
        return False
    requested = source.get('requested_interval')
    if requested is None:
        return True  # 旧版完整分析只记录了运行窗口。
    if not isinstance(requested, list) or len(requested) != 2 or not all(isinstance(value, str) for value in requested):
        return False
    start, end = (parse_github_datetime(value) for value in requested)
    return start is not None and end is not None and start <= lower and upper <= end


def _weekly(events, start, end, source):
    """增量请求范围较窄时，隐藏范围之外无法确认完整的周统计值。"""
    points = weekly(events, start, end, source)
    for point in points:
        lower, upper = parse_github_datetime(point['start']), parse_github_datetime(point['end'])
        if point['quality'] == 'ready' and not _covers(source, lower, upper):
            point['value'] = None
            point['quality'] = 'partial'
    return points


def build_chart_data(events, sources, start, end):
    """根据标准化、去重后的 UTC 事件构造图表序列。

    开发活动、Issue 和 PR 使用 ``[start, end)``；Release 标记使用截至结束时间
    的前 365 天，因此可能显示发布间隔，但无法确认其中的 Commit 数。
    数量和中位数仅描述已观察事件，不代表覆盖证据之外的 GitHub 历史。
    """
    commits = [event for event in events['commits'] if event.get('event_at') and start <= event['event_at'] < end]
    commits_by_week = defaultdict(list)
    account_totals = Counter()
    for event in commits:
        commits_by_week[week_start(event['event_at'])].append(event)
        if event.get('author_key'):
            account_totals[event['author_key']] += 1
    # 在整个窗口内固定前五名作者，使同一作者在不同周的堆叠颜色一致。
    # 没有关联 GitHub 账号的提交单独归入无法识别身份的分组。
    top_accounts = sorted(account_totals, key=lambda key: (-account_totals[key], key))[:5]

    commit_weeks = []
    current = week_start(start)
    while current < end:
        stop = current + timedelta(days=7)
        items = commits_by_week[current]
        accounts = Counter(item['author_key'] for item in items if item.get('author_key'))
        complete = current >= start and stop <= end and _covers(sources.get('commits', {}), current, stop)
        commit_weeks.append({
            'start': iso_z(current), 'end': iso_z(stop), 'complete': complete,
            'observed_commits': len(items),
            'active_authors': len(accounts) if complete or items else None,
            'contributors': [accounts[key] for key in top_accounts],
            'other_commits': sum(count for key, count in accounts.items() if key not in top_accounts),
            'unidentified_commits': sum(not item.get('author_key') for item in items),
        })
        current = stop

    opened = [{'event_at': item.get('created_at')} for item in events['issues'] if item.get('created_at')]
    issue_opened = _weekly(opened, start, end, sources.get('issues', {}))
    issue_closed = _weekly([{'event_at': item.get('closed_at')} for item in events['issues']], start, end, sources.get('issues', {}))

    merged = [event for event in events['pulls'] if event.get('merged_at') and start <= event['merged_at'] < end]
    pr_merged = _weekly([{'event_at': item['merged_at']} for item in merged], start, end, sources.get('pulls', {}))
    valid = []
    for event in merged:
        created = event.get('created_at')
        if created is not None and created <= event['merged_at']:
            valid.append({
                'id': str(event['source_item_id']), 'merged_at': event['merged_at'],
                'duration_hours': (event['merged_at'] - created).total_seconds() / 3600,
            })
    valid.sort(key=lambda item: (item['merged_at'], item['id']))
    by_week = defaultdict(list)
    by_month = defaultdict(list)
    for item in valid:
        by_week[week_start(item['merged_at'])].append(item['duration_hours'])
        by_month[item['merged_at'].replace(day=1, hour=0, minute=0, second=0, microsecond=0)].append(item['duration_hours'])

    pr_weekly = []
    current = week_start(start)
    while current < end:
        values = by_week[current]
        pr_weekly.append({'start': iso_z(current), 'median_hours': median(values) if values else None, 'valid_samples': len(values)})
        current += timedelta(days=7)

    pr_monthly = []
    month = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while month < end:
        stop = _next_month(month)
        values = by_month[month]
        edges = (0, 24, 72, 168, 720, float('inf'))
        pr_monthly.append({
            'month': iso_z(month), 'counts': [sum(low <= value < high for value in values) for low, high in zip(edges, edges[1:])],
            'median_hours': median(values) if values else None, 'valid_samples': len(values),
            'complete': month >= start and stop <= end and _covers(sources.get('pulls', {}), month, stop),
        })
        month = stop

    # 仅限制传给散点图的数据量；上面的月度和周度统计仍使用全部有效样本。
    # 抽样按时间稳定进行，并保留首尾两个样本。
    total_pr_samples = len(valid)
    shown = valid if total_pr_samples <= PR_SCATTER_LIMIT else [
        valid[index * (total_pr_samples - 1) // (PR_SCATTER_LIMIT - 1)] for index in range(PR_SCATTER_LIMIT)
    ]
    pr_samples = [{**item, 'merged_at': iso_z(item['merged_at'])} for item in shown]

    releases = sorted(
        (item for item in events['releases'] if item.get('published_at') and end - timedelta(days=365) <= item['published_at'] < end and not item.get('is_draft') and not item.get('is_prerelease')),
        key=lambda item: item['published_at'],
    )
    commit_source = sources.get('commits', {})
    requested = commit_source.get('requested_interval')
    bounds = [parse_github_datetime(value) for value in requested] if isinstance(requested, list) and len(requested) == 2 and all(isinstance(value, str) for value in requested) else [None, None]
    source_complete = (commit_source.get('coverage') == 'complete' and not commit_source.get('limit_reached')
                       and not commit_source.get('rejected_records') and not commit_source.get('invalid_event_times'))
    commit_times = sorted(item['event_at'] for item in commits)
    intervals = []
    # 只有请求区间与数据质量共同证明覆盖两次发布时间，才能计算区间 Commit 数。
    # bisect_left 实现左闭右开的 [上次发布, 本次发布) 口径。
    for previous, current_release in zip(releases, releases[1:]):
        lower, upper = previous['published_at'], current_release['published_at']
        covered = source_complete and bounds[0] is not None and bounds[1] is not None and start <= lower <= upper <= end and bounds[0] <= lower and upper <= bounds[1]
        intervals.append({
            'id': str(current_release['source_item_id']), 'previous_published_at': iso_z(lower),
            'published_at': iso_z(upper),
            'commit_count': bisect_left(commit_times, upper) - bisect_left(commit_times, lower) if covered else None,
            'reason': None if covered else 'Commit 未完整覆盖此发布间隔',
        })

    return {
        'commit_accounts': top_accounts, 'commit_weekly': commit_weeks,
        'issue_opened_weekly': issue_opened, 'issue_closed_weekly': issue_closed,
        'pr_merged_weekly': pr_merged, 'pr_monthly': pr_monthly, 'pr_weekly': pr_weekly, 'pr_samples': pr_samples,
        'pr_sample_total': total_pr_samples, 'pr_samples_truncated': total_pr_samples > len(pr_samples),
        'release_intervals': intervals,
    }
