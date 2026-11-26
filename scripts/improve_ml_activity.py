#!/usr/bin/env python3
"""在已查看的历史回测上诊断计数模型和验证集路由，不产生正式验收。"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dataprepare/MachineLearn/research_s1"))
from common import HORIZON, SEED, activity_samples, features, load_weekly, sha256, split_repositories  # noqa: E402


def cohort(value):
    return "zero" if value == 0 else "1-9" if value < 10 else "10-99" if value < 100 else "100+"


def build_models(train):
    x = np.asarray([item["x"] for item in train])
    y = np.asarray([item["target"] for item in train])
    models = {
        "ridge": make_pipeline(StandardScaler(), Ridge(alpha=10)),
        "hist_absolute": HistGradientBoostingRegressor(loss="absolute_error", max_iter=120, max_leaf_nodes=15, min_samples_leaf=30, learning_rate=0.07, random_state=SEED),
        "hist_poisson": HistGradientBoostingRegressor(loss="poisson", max_iter=120, max_leaf_nodes=15, min_samples_leaf=30, learning_rate=0.07, random_state=SEED),
        "hist_log_target": TransformedTargetRegressor(regressor=HistGradientBoostingRegressor(loss="squared_error", max_iter=120, max_leaf_nodes=15, min_samples_leaf=30, learning_rate=0.07, random_state=SEED), func=np.log1p, inverse_func=np.expm1),
    }
    for model in models.values():
        model.fit(x, y)
    return models


def predict(models, rows):
    x = np.asarray([row["x"] for row in rows])
    result = {"last_4_weeks": np.asarray([row["last4"] for row in rows]), "last_12_week_mean": np.asarray([row["last12_scaled"] for row in rows])}
    result.update({name: np.maximum(0, model.predict(x)) for name, model in models.items()})
    return result


def mae(rows, values):
    return float(np.mean(np.abs(np.asarray([row["target"] for row in rows]) - values)))


def bootstrap_difference(actual, baseline, candidate, seed=SEED, repetitions=2000):
    differences = np.abs(actual - baseline) - np.abs(actual - candidate)
    rng = np.random.default_rng(seed)
    means = np.mean(differences[rng.integers(0, len(differences), size=(repetitions, len(differences)))], axis=1)
    return {"mean_baseline_minus_candidate_mae": float(np.mean(differences)), "ci95": [float(value) for value in np.quantile(means, [0.025, 0.975])]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    grouped, starts, _ = load_weekly()
    samples = activity_samples(grouped, "commit")
    for item in samples:
        rows = grouped[item["repository_id"]][item["origin"] - 12:item["origin"]]
        if not all(row["pr_opened_coverage"] in {"complete", "true_zero"} and row["pr_opened"] != "" for row in rows):
            item["x"] = None
        else:
            item["x"] = item["x"] + features([int(row["pr_opened"]) for row in rows])
    samples = [item for item in samples if item["x"] is not None]
    splits = split_repositories(grouped)
    train_ids, valid_ids, test_ids = map(set, (splits["train"], splits["validation"], splits["test"]))
    folds = []
    for origin in (40, 44):
        train = [row for row in samples if row["repository_id"] in train_ids and row["origin"] + HORIZON <= origin]
        valid = [row for row in samples if row["repository_id"] in valid_ids and row["origin"] == origin]
        folds.append((valid, predict(build_models(train), valid)))
    routes = {}
    for group in ("zero", "1-9", "10-99", "100+"):
        per_fold = []
        for rows, predictions in folds:
            indices = np.asarray([i for i, row in enumerate(rows) if cohort(row["last4"]) == group])
            per_fold.append({name: mae([rows[i] for i in indices], values[indices]) for name, values in predictions.items()} if len(indices) else {})
        counts = [sum(cohort(row["last4"]) == group for row in rows) for rows, _ in folds]
        baseline = min(("last_4_weeks", "last_12_week_mean"), key=lambda name: sum(values.get(name, 0) for values in per_fold))
        eligible = [name for name in ("ridge", "hist_absolute", "hist_poisson", "hist_log_target")
                    if all(count >= 5 and values[baseline] > 0 and values[name] <= 0.95 * values[baseline] for count, values in zip(counts, per_fold))]
        route = min(eligible, key=lambda name: sum(values[name] for values in per_fold)) if eligible else baseline
        routes[group] = {"method": route, "baseline": baseline, "fold_counts": counts, "fold_mae": per_fold,
                         "rule": "ML requires >=5 repositories per fold and >=5% improvement over selected baseline in each validation fold"}
    origin = 48
    train = [row for row in samples if row["repository_id"] in train_ids and row["origin"] + HORIZON <= origin]
    models = build_models(train)
    tests = {}
    for name, ids in (("seen", train_ids), ("unseen", test_ids)):
        rows = [row for row in samples if row["repository_id"] in ids and row["origin"] == origin]
        values = predict(models, rows)
        routed = np.asarray([values[routes[cohort(row["last4"])]["method"]][i] for i, row in enumerate(rows)])
        baseline = np.asarray([values[routes[cohort(row["last4"])]["baseline"]][i] for i, row in enumerate(rows)])
        tests[name] = {"repositories": len(rows), "mae": {key: mae(rows, pred) for key, pred in values.items()},
                       "routed_mae": mae(rows, routed), "routed_baseline_mae": mae(rows, baseline),
                       "bootstrap": bootstrap_difference(np.asarray([row["target"] for row in rows]), baseline, routed)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = {"status": "research_only", "evaluation_type": "historical_evaluation_not_independent", "seed": SEED,
              "sources_sha256": {"weekly": sha256(ROOT / "ml/course/datasets/repo-evaluation-2026-v1/repository_weekly_features.csv.gz")},
              "validation_origins": [starts[i].isoformat() for i in (40, 44)], "test_origin": starts[48].isoformat(),
              "routes": routes, "historical_test": tests,
              "limitations": ["测试仓库和时段此前已被研究实验查看，不能作为新的发布验收。", "默认分支历史成员关系不可回溯，PR 创建量仅作为对应模块完整的历史协变量。"]}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"routes": {key: value["method"] for key, value in routes.items()}, "historical_test": tests}, ensure_ascii=False))


if __name__ == "__main__":
    main()
