import pytest

from scripts.build_ml_coverage_matrix import MODULES, build_matrix


def rows(repository_id, repository, **statuses):
    return [{"repository_id": repository_id, "selected_full_name": repository, "module": module, "status": statuses.get(module, "complete")} for module in MODULES]


def test_module_level_coverage_does_not_discard_unrelated_fields():
    values = rows(1, "sgl-project/sglang", pull_requests_updated="partial_concurrent_change")
    values += rows(2, "renovatebot/renovate", releases="failed", commits="true_zero")
    audit = {"affected_repositories": [{"repository_id": 1}], "repositories_with_full_terminal_page_at_300_or_more": []}
    first, second = build_matrix(values, audit)
    assert first["ml01_source_usable"] and first["ml02_source_usable"] and first["ml03_sources_usable"]
    assert first["pull_requests_updated"] == "partial_concurrent_change" and first["issue_comment_audit"] == "coverage_uncertain"
    assert second["ml01_source_usable"] and second["ml02_source_usable"] and not second["release_source_usable"]
    assert second["commits"] == "true_zero" and second["issue_comment_audit"] == "not_independently_certified"


def test_missing_or_duplicate_module_is_not_silently_filled():
    audit = {"affected_repositories": [], "repositories_with_full_terminal_page_at_300_or_more": []}
    with pytest.raises(ValueError, match="missing module"):
        build_matrix(rows(1, "a/b")[:-1], audit)
    with pytest.raises(ValueError, match="duplicate"):
        build_matrix(rows(1, "a/b") + rows(1, "a/b")[:1], audit)
