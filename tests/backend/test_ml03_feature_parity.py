from scripts.ml03_feature_parity import equivalent


def test_float_rounding_is_tolerated_but_changed_data_and_hash_are_not():
    original = {'source_sha256':'abc', 'feature_values':{'variance':0.4121772184846195}, 'count':52}
    assert equivalent(original, {'source_sha256':'abc', 'feature_values':{'variance':0.4121772184846196}, 'count':52})
    assert not equivalent(original, {'source_sha256':'changed', 'feature_values':{'variance':0.4121772184846196}, 'count':52})
    assert not equivalent(original, {'source_sha256':'abc', 'feature_values':{'variance':0.4121773}, 'count':52})
    assert not equivalent({'value': True}, {'value': 1})
