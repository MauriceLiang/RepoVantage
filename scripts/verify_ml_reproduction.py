#!/usr/bin/env python3
"""比较历史研究运行与重新运行的内容；历史测试集不作为新的验收集。"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path


def content_hash(path: Path):
    digest = hashlib.sha256()
    reader = gzip.open if path.suffix == ".gz" else open
    with reader(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def equivalent(left, right):
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-10)
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(equivalent(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(equivalent(a, b) for a, b in zip(left, right))
    return left == right


def verify(root: Path, replay: Path):
    prior_s1, prior_followup = root / "s1-20261109-v1", root / "s2-s4-20261109-v1"
    datasets = [
        (prior_s1 / "activity/commit/samples.csv.gz", replay / "activity/commit/samples.csv.gz"),
        (prior_s1 / "activity/pr/samples.csv.gz", replay / "activity/pr/samples.csv.gz"),
        (prior_s1 / "pr_audit/pr_samples.csv.gz", replay / "pr_audit/pr_samples.csv.gz"),
        (prior_followup / "ml05_issue_response/issue_samples.csv.gz", replay / "ml05_issue_response/issue_samples.csv.gz"),
        (prior_followup / "ml07_decline/experiment/samples.csv.gz", replay / "ml07_decline/experiment/samples.csv.gz"),
        (prior_followup / "ml08_release/experiment/samples.csv.gz", replay / "ml08_release/experiment/samples.csv.gz"),
        (prior_s1 / "clusters/repository_clusters.csv", replay / "clusters/repository_clusters.csv"),
        (prior_followup / "ml06_anomaly/test_weeks.csv", replay / "ml06_anomaly/test_weeks.csv"),
    ]
    comparisons = []
    for old, new in datasets:
        old_hash, new_hash = content_hash(old), content_hash(new)
        comparisons.append({"original": str(old), "replay": str(new), "content_sha256": old_hash,
                            "matches": old_hash == new_hash})
    metric_paths = [
        (prior_s1 / "activity/commit/metrics.json", replay / "activity/commit/metrics.json"),
        (prior_s1 / "activity/pr/metrics.json", replay / "activity/pr/metrics.json"),
        (prior_s1 / "pr_merge/metrics.json", replay / "pr_merge/metrics.json"),
        (prior_followup / "ml05_issue_response/metrics.json", replay / "ml05_issue_response/metrics.json"),
        (prior_followup / "ml07_decline/experiment/metrics.json", replay / "ml07_decline/experiment/metrics.json"),
        (prior_followup / "ml08_release/experiment/metrics.json", replay / "ml08_release/experiment/metrics.json"),
    ]
    metrics = []
    for old, new in metric_paths:
        left, right = json.loads(old.read_text()), json.loads(new.read_text())
        metrics.append({"original": str(old), "replay": str(new), "selected_matches": left["selected"] == right["selected"],
                        "test_metrics_match": equivalent(left["test"], right["test"])})
    old_split = json.loads((prior_s1 / "activity/manifest.json").read_text())["split_repository_ids"]
    new_split = json.loads((replay / "activity/manifest.json").read_text())["split_repository_ids"]
    passed = all(item["matches"] for item in comparisons) and all(item["selected_matches"] and item["test_metrics_match"] for item in metrics) and old_split == new_split
    return {"status": "pass" if passed else "fail", "evaluation_status": "historical_evaluation",
            "independent_release_test": False, "datasets": comparisons, "metrics": metrics, "repository_split_matches": old_split == new_split,
            "note": "哈希针对解压后的样本内容；历史 gzip 容器包含时间戳，字节级哈希可能不同。"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.runs, args.replay)
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(result["status"])
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
