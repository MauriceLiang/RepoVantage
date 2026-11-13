from datetime import datetime, timezone
from types import SimpleNamespace
import hashlib
import json
import sys

import pytest

from scripts import ml01_shadow_outcome
from scripts.ml01_shadow_outcome import observe_events


class FakeGitHub:
    def __init__(self, compare_status='ahead'):
        self.compare_status = compare_status

    def _request(self, method, path, **kwargs):
        return SimpleNamespace(json=lambda: {'status': self.compare_status, 'behind_by': 0, 'ahead_by': 1, 'total_commits': 1})

    def list_paginated_detailed(self, path, params, on_page, **kwargs):
        rows = [{'sha': 'c'*40, 'commit': {'committer': {'date': '2026-11-10T00:00:00Z'}}}]
        on_page(SimpleNamespace(page_index=1, request_url=path, next_url=None, http_status=200, records=rows, has_next=False))
        return SimpleNamespace(items=rows, complete=True, error_code=None)


def test_boundary_and_visible_commit_evidence_never_auto_approves_label():
    row = {'repository_id': 1, 'default_branch': 'main', 'head_sha_observed': 'a'*40}
    pre = {'branch': 'main', 'head_sha': 'b'*40, 'observed_at': '2026-12-07T14:07:59Z'}
    post = {'branch': 'main', 'head_sha': 'b'*40, 'observed_at': '2026-12-07T14:08:01Z'}
    result = observe_events(FakeGitHub(), row, pre, post, datetime(2026,11,9,14,8,tzinfo=timezone.utc), datetime(2026,12,7,14,8,tzinfo=timezone.utc))
    assert result['visible_commit_timestamp_count'] == 1
    assert result['eligible_for_scoring'] is False and result['target_status'] == 'coverage_uncertain'
    assert 'historical_membership_requires_independent_review' in result['reasons']


def test_divergence_or_missing_boundary_is_explicitly_uncertain():
    row = {'repository_id': 1, 'default_branch': 'main', 'head_sha_observed': 'a'*40}
    post = {'branch': 'renamed', 'head_sha': 'b'*40, 'observed_at': '2026-12-07T14:08:01Z'}
    result = observe_events(FakeGitHub(compare_status='diverged'), row, None, post, datetime(2026,11,9,14,8,tzinfo=timezone.utc), datetime(2026,12,7,14,8,tzinfo=timezone.utc))
    assert 'missing_pre_boundary_snapshot' in result['reasons']
    assert 'non_descendant_or_unverifiable_history' in result['reasons']
    assert result['eligible_for_scoring'] is False


def test_scheduled_code_lock_rejects_modified_runtime(monkeypatch, tmp_path):
    names = ['scripts/ml01_shadow_outcome.py', 'scripts/collect_ml_holdout.py', 'scripts/repair_issue_comments.py',
             'backend/app/integrations/github/client.py', 'backend/app/core/clock.py', 'backend/app/core/config.py',
             'backend/app/core/exceptions.py', 'pyproject.toml', 'uv.lock',
             'ml-production/scheduling/com.repovantage.ml01-shadow-20261207.plist']
    hashes = {}
    for name in names:
        path = tmp_path/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    lock = tmp_path/'task_lock.json'
    lock.write_text(json.dumps({'python_version':sys.version.split()[0], 'hashes':hashes}))
    monkeypatch.setattr(ml01_shadow_outcome, 'ROOT', tmp_path)
    monkeypatch.setattr(ml01_shadow_outcome, 'TASK_LOCK', lock)
    monkeypatch.setattr(ml01_shadow_outcome.Path, 'home', classmethod(lambda cls: tmp_path/'fake-home'))
    ml01_shadow_outcome.validate_task_code()
    (tmp_path/'backend/app/core/clock.py').write_text('changed')
    with pytest.raises(ValueError, match='哈希已改变'):
        ml01_shadow_outcome.validate_task_code()
