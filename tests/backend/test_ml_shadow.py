from types import SimpleNamespace

from scripts.start_ml_shadow import collect_repo


class GitHub:
    def __init__(self, complete=True):
        self.complete = complete
        self.requested_sha = None

    def get_repository_by_id(self, repository_id):
        return ({'id': repository_id, 'private': False, 'default_branch': 'main', 'created_at': '2020-01-01T00:00:00Z'}, None, None)

    def _request(self, method, path):
        return SimpleNamespace(json=lambda: {'sha': 'a' * 40})

    def list_paginated_detailed(self, path, params, on_page, **kwargs):
        self.requested_sha = params['sha']
        on_page(SimpleNamespace(page_index=1, request_url=path, next_url=None, http_status=200, records=[], has_next=not self.complete))
        return SimpleNamespace(items=[], complete=self.complete, error_code=None)


def test_shadow_history_is_anchored_to_a_captured_immutable_head():
    github = GitHub()
    item = {'repository_id': 5, 'selected_full_name': 'example/project'}
    result = collect_repo(github, item, 10)
    assert result['status'] == 'complete_snapshot'
    assert github.requested_sha == 'a' * 40 == result['head_sha_observed']
    assert len(result['weekly_commits']) == 12
    assert result['history_end'] <= result['snapshot_recorded_at']
    incomplete = collect_repo(GitHub(complete=False), item, 1)
    assert incomplete['status'] == 'coverage_uncertain'
    assert 'pagination_incomplete' in incomplete['coverage_reasons']
