from datetime import datetime, timedelta

from backend.app.analytics.chart_data import PR_SCATTER_LIMIT, build_chart_data
from backend.app.core.clock import iso_z


START = datetime(2026, 1, 5)
END = datetime(2026, 3, 2)


def sources():
    return {name: {'coverage': 'complete', 'requested_interval': [iso_z(START), iso_z(END)]} for name in ('commits', 'issues', 'pulls', 'releases')}


def test_chart_data_uses_observed_accounts_and_issue_open_dates():
    events = {
        'commits': [
            {'event_at': START + timedelta(days=1), 'author_key': 'github:1'},
            {'event_at': START + timedelta(days=2), 'author_key': 'github:1'},
            {'event_at': START + timedelta(days=2), 'author_key': None},
            {'event_at': START + timedelta(days=8), 'author_key': 'github:2'},
            {'event_at': END, 'author_key': 'github:3'},
        ],
        'issues': [{'created_at': START + timedelta(days=1)}, {'created_at': START + timedelta(days=8)}, {'created_at': END}],
        'pulls': [], 'releases': [],
    }
    result = build_chart_data(events, sources(), START, END)
    assert result['commit_accounts'] == ['github:1', 'github:2']
    first, second = result['commit_weekly'][:2]
    assert first['contributors'] == [2, 0] and first['unidentified_commits'] == 1
    assert first['active_authors'] == 1 and first['observed_commits'] == 3
    assert second['active_authors'] == 1 and second['contributors'] == [0, 1]
    assert [point['value'] for point in result['issue_opened_weekly'][:2]] == [1, 1]

    partial_sources = sources()
    partial_sources['issues']['coverage'] = 'partial'
    partial_sources['commits']['coverage'] = 'partial'
    partial = build_chart_data(events, partial_sources, START, END)
    assert partial['issue_opened_weekly'][0]['value'] is None
    assert partial['issue_opened_weekly'][0]['observed_events'] == 1
    assert partial['commit_weekly'][0]['complete'] is False
    assert partial['commit_weekly'][2]['active_authors'] is None


def test_pr_monthly_bins_medians_and_invalid_duration():
    merged = datetime(2026, 1, 20)
    pulls = [
        {'source_item_id': str(index), 'merged_at': merged, 'created_at': merged - timedelta(hours=hours)}
        for index, hours in enumerate((1, 24, 72, 168, 720), 1)
    ]
    pulls += [
        {'source_item_id': 'bad', 'merged_at': merged, 'created_at': merged + timedelta(hours=1)},
        {'source_item_id': 'feb', 'merged_at': datetime(2026, 2, 10), 'created_at': datetime(2026, 2, 9)},
    ]
    result = build_chart_data({'commits': [], 'issues': [], 'pulls': pulls, 'releases': []}, sources(), START, END)
    jan, feb, march = result['pr_monthly']
    assert jan['counts'] == [1, 1, 1, 1, 1] and jan['median_hours'] == 72
    assert jan['valid_samples'] == 5 and jan['complete'] is False
    assert feb['counts'] == [0, 1, 0, 0, 0] and feb['complete'] is True
    assert march['valid_samples'] == 0 and march['complete'] is False
    assert result['pr_sample_total'] == 6
    assert {sample['id'] for sample in result['pr_samples']} == {'1', '2', '3', '4', '5', 'feb'}


def test_incremental_source_does_not_claim_uncovered_periods_are_complete():
    source = sources()
    for module in ('commits', 'issues', 'pulls'):
        source[module]['requested_interval'] = [iso_z(START + timedelta(days=14)), iso_z(END)]
    result = build_chart_data({'commits': [], 'issues': [], 'pulls': [], 'releases': []}, source, START, END)
    assert result['commit_weekly'][0]['complete'] is False
    assert result['commit_weekly'][0]['active_authors'] is None
    assert result['commit_weekly'][2]['complete'] is True
    for name in ('issue_opened_weekly', 'issue_closed_weekly', 'pr_merged_weekly'):
        assert result[name][0]['value'] is None
        assert result[name][2]['value'] == 0
    assert result['pr_monthly'][0]['complete'] is False
    assert result['pr_monthly'][1]['complete'] is True


def test_release_interval_counts_require_full_commit_coverage_and_use_exact_boundaries():
    previous = START + timedelta(days=1, hours=12)
    current = START + timedelta(days=5, hours=12)
    commits = [
        {'event_at': previous, 'author_key': 'github:1'},
        {'event_at': previous + timedelta(hours=1), 'author_key': 'github:2'},
        {'event_at': current, 'author_key': 'github:3'},
    ]
    releases = [
        {'source_item_id': 'old', 'published_at': START - timedelta(days=1)},
        {'source_item_id': 'a', 'published_at': previous},
        {'source_item_id': 'b', 'published_at': current},
    ]
    events = {'commits': commits, 'issues': [], 'pulls': [], 'releases': releases}
    result = build_chart_data(events, sources(), START, END)
    assert result['release_intervals'][0]['commit_count'] is None
    assert result['release_intervals'][1]['commit_count'] == 2
    partial_sources = sources()
    partial_sources['commits']['coverage'] = 'partial'
    assert build_chart_data(events, partial_sources, START, END)['release_intervals'][1]['commit_count'] is None
    missing_proof = sources()
    del missing_proof['commits']['requested_interval']
    assert build_chart_data(events, missing_proof, START, END)['release_intervals'][1]['commit_count'] is None


def test_pr_scatter_sampling_is_bounded_and_preserves_endpoints():
    pulls = [
        {'source_item_id': str(index), 'merged_at': START + timedelta(minutes=index), 'created_at': START}
        for index in range(PR_SCATTER_LIMIT + 100)
    ]
    result = build_chart_data({'commits': [], 'issues': [], 'pulls': pulls, 'releases': []}, sources(), START, END)
    assert result['pr_sample_total'] == len(pulls)
    assert result['pr_samples_truncated'] is True
    assert len(result['pr_samples']) == PR_SCATTER_LIMIT
    assert result['pr_samples'][0]['id'] == '0' and result['pr_samples'][-1]['id'] == str(len(pulls) - 1)
    assert result['pr_weekly'][0]['valid_samples'] == len(pulls)
