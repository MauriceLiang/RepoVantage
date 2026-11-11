from __future__ import annotations

import pytest

from scripts.course_split import (
    EXPECTED_SOURCE_SHA256,
    build_manifest,
    make_split,
    validate_manifest,
)


def test_split_is_reproducible_disjoint_and_covers_all_300_ids():
    repository_ids = [str(value) for value in range(1, 301)]
    manifest = build_manifest(repository_ids, EXPECTED_SOURCE_SHA256, seed=20261111)
    train_ids, test_ids = make_split(repository_ids, seed=20261111)

    assert manifest["train_count"] == len(train_ids) == 150
    assert manifest["test_count"] == len(test_ids) == 150
    assert train_ids == manifest["train_repository_ids"]
    assert test_ids == manifest["test_repository_ids"]
    assert set(train_ids).isdisjoint(test_ids)
    assert set(train_ids) | set(test_ids) == set(repository_ids)
    assert make_split(repository_ids, seed=20261111) == (train_ids, test_ids)


def test_split_rejects_duplicate_or_non_300_id_sources():
    with pytest.raises(ValueError, match="300 unique"):
        make_split([str(value) for value in range(1, 300)])
    with pytest.raises(ValueError, match="300 unique"):
        make_split([str(value) for value in range(1, 300)] + ["1"])


def test_split_rejects_changed_source_hash():
    with pytest.raises(ValueError, match="source SHA-256"):
        build_manifest([str(value) for value in range(1, 301)], "0" * 64)


def test_manifest_validation_rejects_test_leakage():
    repository_ids = [str(value) for value in range(1, 301)]
    manifest = build_manifest(repository_ids, EXPECTED_SOURCE_SHA256)
    manifest["test_repository_ids"][0] = manifest["train_repository_ids"][0]
    with pytest.raises(ValueError, match="overlap"):
        validate_manifest(manifest, repository_ids)
