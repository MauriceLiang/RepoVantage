from scripts.build_anomaly_review_set import build


def test_review_sample_preserves_flags_and_is_reproducible():
    rows = []
    for index in range(40):
        rows.append({"repository_id": str(index), "week_start": "2026-08-10", "robust_rule_flag": str(int(index < 20)),
                     "isolation_flag": str(int(index % 3 == 0)), "commit_robust_deviation": str((-1) ** index * 4), "pr_robust_deviation": "0"})
    first = build(rows, size=20)
    assert first == build(rows, size=20)
    assert len(first) == 20 and len({row["repository_id"] for _, row in first}) == 20
    assert {key[0] for key, _ in first} == {"both", "model_only", "rule_only", "neither"}
