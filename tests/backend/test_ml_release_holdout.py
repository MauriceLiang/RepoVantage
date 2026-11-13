from types import SimpleNamespace

from scripts.collect_ml_release_holdout import collect_repo


class GitHub:
    def __init__(self, releases, complete=True):
        self.releases = releases
        self.complete = complete

    def get_repository_by_id(self, repository_id):
        return ({'id': repository_id, 'private': False, 'created_at': '2020-01-01T00:00:00Z'}, None, None)

    def list_paginated_detailed(self, path, params, on_page=None, **kwargs):
        if on_page:
            on_page(SimpleNamespace(page_index=1, request_url=path, next_url=None, http_status=200,
                                    records=self.releases, has_next=not self.complete))
        return SimpleNamespace(items=self.releases, complete=self.complete, error_code=None)


def test_release_collection_distinguishes_complete_snapshot_from_truncated():
    items = [{'id': 1, 'draft': False, 'prerelease': False, 'published_at': '2026-01-01T00:00:00Z'}]
    candidate = {'repository_id': 5, 'selected_full_name': 'example/project'}
    complete = collect_repo(GitHub(items), candidate, 2)
    assert complete['status'] == 'complete_current_snapshot'
    assert complete['releases'][0]['id'] == 1
    assert '不证明历史时点' in complete['limitations'][0]
    incomplete = collect_repo(GitHub(items, complete=False), candidate, 1)
    assert incomplete['status'] == 'coverage_uncertain'
    assert 'pagination_incomplete' in incomplete['coverage_reasons']


def test_release_collection_rejects_duplicate_identifiers():
    item = {'id': 1, 'draft': False, 'published_at': '2026-01-01T00:00:00Z'}
    result = collect_repo(GitHub([item, item]), {'repository_id': 5}, 2)
    assert result['status'] == 'coverage_uncertain'
    assert 'invalid_or_duplicate_release' in result['coverage_reasons']
