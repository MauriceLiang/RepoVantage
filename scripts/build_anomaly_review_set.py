#!/usr/bin/env python3
"""生成未标注的分层人工复核样本；不推断异常真值。"""
import argparse
import csv
import hashlib
import random
from collections import defaultdict
from pathlib import Path


def build(rows, *, size=200, seed=20261109):
    if size < 1 or size > len(rows):
        raise ValueError("复核数量必须在可用周数范围内")
    groups = defaultdict(list)
    for row in rows:
        rule, model = row["robust_rule_flag"] == "1", row["isolation_flag"] == "1"
        label = "both" if rule and model else "model_only" if model else "rule_only" if rule else "neither"
        dominant = max((float(row["commit_robust_deviation"]), float(row["pr_robust_deviation"])), key=abs)
        direction = "increase" if dominant > 0 else "decrease" if dominant < 0 else "unchanged"
        groups[(label, direction)].append(row)
    rng = random.Random(seed)
    for group in groups.values():
        rng.shuffle(group)
    selected = []
    # 先保证各种告警来源与方向有代表，再用剩余样本补足数量。
    for key in sorted(groups):
        amount = min(len(groups[key]), max(1, size // max(1, len(groups))))
        selected.extend((key, row) for row in groups[key][:amount])
        groups[key] = groups[key][amount:]
    if len(selected) > size:
        rng.shuffle(selected)
        selected = selected[:size]
    remainder = [(key, row) for key, group in groups.items() for row in group]
    rng.shuffle(remainder)
    selected.extend(remainder[:size - len(selected)])
    rng.shuffle(selected)
    return [(key, row) for key, row in selected]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, default=200)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    with args.input.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    selected = build(rows, size=args.size)
    fields = ["case_id", "repository_id", "repository", "week_start", "available_at", "stratum", "direction", "commits", "pr_created", "history_median_commit", "history_median_pr", "commit_robust_deviation", "pr_robust_deviation", "robust_rule_flag", "isolation_score", "isolation_flag", "reviewer_a", "reviewer_b", "evidence_url", "notes"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for (stratum, direction), row in selected:
            identifier = hashlib.sha256(f"{row['repository_id']}:{row['week_start']}".encode()).hexdigest()[:16]
            writer.writerow({key: value for key, value in {**row, "case_id": identifier, "stratum": stratum, "direction": direction}.items() if key in fields})


if __name__ == "__main__":
    main()
