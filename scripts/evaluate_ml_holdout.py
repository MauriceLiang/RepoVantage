#!/usr/bin/env python3
"""评估预先冻结的未见仓库；数据血缘未达标时禁止批准模型。"""
import argparse
import csv
import json
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path

import joblib
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dataprepare/MachineLearn/research_s1"))
from common import dt, features, sha256  # noqa: E402


def category(value):
    return "0" if value == 0 else "1-9" if value < 10 else "10-99" if value < 100 else "100+"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--collection", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    lock = json.loads(args.lock.read_text(encoding="utf-8"))
    collection = json.loads((args.collection / "manifest.json").read_text(encoding="utf-8"))
    if lock["manifest_sha256"] != sha256(args.manifest) or collection["input_sha256"] != sha256(args.manifest) or lock["model_sha256"] != sha256(args.model):
        raise ValueError("冻结的名单、模型或采集清单哈希不一致")
    if args.output.exists():
        raise FileExistsError(args.output)
    expected = {item["repository_id"] for item in manifest["repositories"]}
    files = {int(path.stem): path for path in (args.collection / "repositories").glob("*.json")}
    if set(files) != expected:
        raise ValueError("采集未完成或输出包含未冻结仓库")
    start, origin, end = dt(manifest["history_start"]), dt(manifest["origin"]), dt(manifest["target_end_exclusive"])
    records, excluded = [], Counter()
    for candidate in manifest["repositories"]:
        record = json.loads(files[candidate["repository_id"]].read_text(encoding="utf-8"))
        if record.get("repository_id") != candidate["repository_id"] or record.get("status") != "complete_current_snapshot":
            excluded[record.get("status", "missing")] += 1
            continue
        weekly = record.get("weekly_commits")
        if not isinstance(weekly, list) or len(weekly) != 16 or any(type(value) is not int or value < 0 for value in weekly):
            raise ValueError(f"invalid weekly data: {candidate['repository_id']}")
        rebuilt, seen = [0] * 16, set()
        for event in record["events"]:
            timestamp = dt(event["event_at"])
            if event["sha"] in seen or not start <= timestamp < end:
                raise ValueError(f"invalid holdout event: {candidate['repository_id']}")
            seen.add(event["sha"])
            rebuilt[(timestamp - start).days // 7] += 1
        if rebuilt != weekly or start + timedelta(weeks=12) != origin:
            raise ValueError(f"holdout weekly mismatch: {candidate['repository_id']}")
        records.append({"repository_id": candidate["repository_id"], "repository": record["full_name_at_capture"],
                        "stratum": candidate["stratum"], "history": weekly[:12], "actual": sum(weekly[12:])})
    if not records:
        raise ValueError("没有完整仓库可供评估")
    model = joblib.load(args.model)
    x = np.asarray([features(row["history"]) for row in records])
    candidate = np.asarray(model["model"].predict(x))
    actual = np.asarray([row["actual"] for row in records], dtype=float)
    last4 = np.asarray([sum(row["history"][-4:]) for row in records], dtype=float)
    last12 = np.asarray([sum(row["history"]) / 3 for row in records], dtype=float)
    if not np.isfinite(candidate).all() or np.any(candidate < 0):
        raise ValueError("候选预测无效")
    rng = np.random.default_rng(20261109)
    indices = rng.integers(0, len(records), size=(5000, len(records)))
    comparisons = {}
    for name, baseline in (("last_4_weeks", last4), ("last_12_week_mean", last12)):
        model_errors = np.abs(actual - candidate)
        baseline_errors = np.abs(actual - baseline)
        differences = baseline_errors - model_errors
        interval = np.quantile(np.mean(differences[indices], axis=1), [0.025, 0.975])
        base_mae = float(np.mean(baseline_errors))
        comparisons[name] = {"baseline_mae": base_mae, "model_mae": float(np.mean(model_errors)),
                             "relative_improvement": float(np.mean(differences) / base_mae) if base_mae else None,
                             "bootstrap_difference_ci95": [float(interval[0]), float(interval[1])]}
    groups = {}
    group_ok = True
    for group in ("0", "1-9", "10-99", "100+"):
        mask = np.asarray([category(value) == group for value in last4])
        if not mask.any():
            continue
        value = {"repositories": int(mask.sum()), "model_mae": float(np.mean(np.abs(actual[mask] - candidate[mask]))),
                 "last4_mae": float(np.mean(np.abs(actual[mask] - last4[mask]))),
                 "last12_mae": float(np.mean(np.abs(actual[mask] - last12[mask])))}
        if mask.sum() >= 10:
            strong = min(value["last4_mae"], value["last12_mae"])
            if value["model_mae"] > strong * 1.05:
                group_ok = False
        groups[group] = value
    numerical_gate = len(records) >= 30 and int(np.sum(last4 > 0)) >= 15 and group_ok and all(
        item["relative_improvement"] is not None and item["relative_improvement"] >= 0.05 and item["bootstrap_difference_ci95"][0] > 0
        for item in comparisons.values())
    args.output.mkdir(parents=True, exist_ok=False)
    with (args.output / "predictions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["repository_id", "repository", "stratum", "recent_4w", "actual", "prediction", "last_4w_baseline", "last_12w_baseline"])
        writer.writerows([row["repository_id"], row["repository"], row["stratum"], int(last4[index]), int(actual[index]), float(candidate[index]), float(last4[index]), float(last12[index])] for index, row in enumerate(records))
    summary = {"status": "research_only", "evaluation_type": "new_unseen_repositories_retrospective_snapshot", "frozen_repositories": len(expected),
               "complete_repositories": len(records), "excluded": dict(excluded), "nonzero_recent_repositories": int(np.sum(last4 > 0)),
               "comparisons": comparisons, "groups": groups, "numerical_gate_passed": numerical_gate,
               "approval_gate_passed": False, "approval_blocker": "无法证明历史预测时默认分支成员关系；当前快照可能引入未来可见提交。",
               "model_sha256": sha256(args.model), "manifest_sha256": sha256(args.manifest), "repetitions": 5000}
    (args.output / "metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
