from scripts.evaluate_ml_release_holdout import sample


def test_release_features_are_strictly_before_origin_and_label_uses_future():
    protocol = {'evaluation_origin': '2026-08-10T00:00:00Z', 'history_start': '2026-02-09T00:00:00Z',
                'target_end_exclusive': '2026-11-02T00:00:00Z'}
    record = {'repository_id': 1, 'selected_full_name': 'example/project', 'status': 'complete_current_snapshot',
              'created_at': '2020-01-01T00:00:00Z', 'releases': [
                  {'published_at': '2026-02-09T00:00:00Z'}, {'published_at': '2026-03-09T00:00:00Z'},
                  {'published_at': '2026-08-03T00:00:00Z'}, {'published_at': '2026-08-10T00:00:00Z'},
                  {'published_at': '2026-11-02T00:00:00Z'}]}
    row, reason = sample(record, protocol)
    assert reason is None
    assert row['features'][:4] == [1, 1, 3, 3]
    assert row['actual'] == 0
    record['releases'] = record['releases'][:3] + record['releases'][4:]
    row, _ = sample(record, protocol)
    assert row['actual'] == 1
