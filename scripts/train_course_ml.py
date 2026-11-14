#!/usr/bin/env python3
"""Run the frozen 150/150 course-design experiment using local weekly data only."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import itertools
import json
import platform
from collections import Counter, defaultdict
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.cluster import KMeans
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (adjusted_rand_score, balanced_accuracy_score, confusion_matrix,
                             f1_score, normalized_mutual_info_score,
                             precision_recall_fscore_support, silhouette_score)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from backend.app.analytics.course_ml_features import (
    FEATURE_SCHEMA_VERSION, PATTERN_FEATURES, TREND_FEATURES,
    build_weekly_features, recent_trend_baseline, trend_label,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dataprepare/MachineLearn/run/repo-evaluation-2026-v1/repository_weekly_features.csv.gz"
SPLIT_DEFAULT = ROOT / "ml/course/splits/repositories-150-150-v1.json"
EXPECTED_SOURCE_SHA256 = "5a463e44da2260d943a7851c872277984552fba3034e12eb8d5bb14c7c2c148d"
SEED = 20261111
OUTPUT_DEFAULT = ROOT / "ml/course/experiments/course-150-150-v1"
CANDIDATE_DEFAULT = ROOT / "ml/course/candidates/course-150-150-v1"
CANDIDATE_DIR = CANDIDATE_DEFAULT


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def load_weekly():
    grouped = defaultdict(list)
    with gzip.open(SOURCE, "rt", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            grouped[str(int(row["repository_id"]))].append(row)
    for repo_id, rows in grouped.items():
        rows.sort(key=lambda row: row["period_start"])
        if len(rows) != 52 or len({row["period_start"] for row in rows}) != 52:
            raise ValueError(f"{repo_id}: expected 52 distinct weekly rows")
    return dict(sorted(grouped.items()))


def normalize_week(row):
    def optional_count(value):
        return int(value) if value not in (None, "") else None

    return {
        "week_start_utc": row["period_start"],
        "week_end_exclusive_utc": row["period_end"],
        "commits": optional_count(row.get("commits_observed")),
        "prs_created": optional_count(row.get("pr_opened")),
        "commit_coverage": row["commit_coverage"],
        "pr_created_coverage": row["pr_opened_coverage"],
    }


def load_split_manifest(path: Path, repository_ids):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    train, test = manifest.get("train_repository_ids"), manifest.get("test_repository_ids")
    if (manifest.get("dataset_id") != "repo-evaluation-2026-v1"
            or manifest.get("split_version") != "course-150-150-v1"
            or manifest.get("source_sha256") != EXPECTED_SOURCE_SHA256
            or len(train or []) != 150 or len(test or []) != 150
            or len(set(train or [])) != 150 or len(set(test or [])) != 150
            or set(train or []) & set(test or [])
            or set(train or []) | set(test or []) != set(repository_ids)):
        raise ValueError("split manifest is not the frozen, disjoint 150/150 split for this source")
    from scripts.course_split import id_list_sha256
    if (manifest.get("train_ids_sha256") != id_list_sha256(train)
            or manifest.get("test_ids_sha256") != id_list_sha256(test)):
        raise ValueError("split manifest ID-list hash mismatch")
    return {"train": set(train), "test": set(test)}, manifest


def save_rows(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _kmeans_seed_stability(z_train, k):
    seeds = (SEED, SEED + 1, SEED + 2, SEED + 3, SEED + 4)
    models = [KMeans(n_clusters=k, random_state=seed, n_init=50).fit(z_train) for seed in seeds]
    aris = [adjusted_rand_score(left.labels_, right.labels_)
            for left, right in itertools.combinations(models, 2)]
    silhouettes = [float(silhouette_score(z_train, model.labels_))
                   if len(set(model.labels_.tolist())) > 1 else None for model in models]
    return models[0], seeds, aris, silhouettes


def pattern_training(grouped, splits, output):
    rows, excluded = [], []
    for repo_id, weekly in grouped.items():
        try:
            weeks = [normalize_week(row) for row in weekly[-12:]]
            result = build_weekly_features(weeks)
        except (TypeError, ValueError) as exc:
            excluded.append({"repository_id": repo_id, "repository": weekly[0]["repository"], "reason": str(exc)})
            continue
        features = result["pattern_features"]
        rows.append({"repository_id": repo_id, "repository": weekly[0]["repository"],
                     "commit_total_12w": result["facts"]["commit_total"], **features})
    ids = splits
    train = [row for row in rows if row["repository_id"] in ids["train"]]
    test = [row for row in rows if row["repository_id"] in ids["test"]]
    x_train = np.asarray([[row[name] for name in PATTERN_FEATURES] for row in train], dtype=float)
    x_test = np.asarray([[row[name] for name in PATTERN_FEATURES] for row in test], dtype=float)
    scaler = StandardScaler().fit(x_train)
    z_train = scaler.transform(x_train)
    comparisons, candidates = {}, {}
    for k in (2, 3, 4):
        model, seeds, seed_ari, seed_silhouettes = _kmeans_seed_stability(z_train, k)
        size_cuts = np.quantile([row["commit_total_12w"] for row in train], np.arange(1, k) / k)
        size_train = np.digitize([row["commit_total_12w"] for row in train], size_cuts, right=True)
        size_silhouette = (float(silhouette_score(z_train, size_train))
                           if 1 < len(set(size_train.tolist())) < len(size_train) else None)
        size_nmi = float(normalized_mutual_info_score(size_train, model.labels_))
        silhouette_values = [value for value in seed_silhouettes if value is not None]
        comparisons[str(k)] = {
            "train_silhouette": float(silhouette_score(z_train, model.labels_)) if len(set(model.labels_)) > 1 else None,
            "seed_silhouette_mean": float(np.mean(silhouette_values)) if silhouette_values else None,
            "seed_silhouette_by_seed": dict(zip(map(str, seeds), seed_silhouettes)),
            "seed_pairwise_ari": seed_ari,
            "mean_seed_pairwise_ari": float(np.mean(seed_ari)) if seed_ari else None,
            "size_only_train_silhouette": size_silhouette,
            "nmi_with_training_size_quantile_bins": size_nmi,
            "cluster_sizes_train": dict(Counter(map(int, model.labels_))),
        }
        candidates[k] = (model, size_cuts)
    eligible = [k for k in candidates if comparisons[str(k)]["train_silhouette"] is not None]
    selected_k = max(eligible, key=lambda k: (
        comparisons[str(k)]["seed_silhouette_mean"],
        comparisons[str(k)]["mean_seed_pairwise_ari"],
    )) if eligible else None
    selected_info = comparisons[str(selected_k)] if selected_k is not None else {}
    deploy = bool(selected_k is not None and selected_info["train_silhouette"] is not None
                  and (selected_info["size_only_train_silhouette"] is None
                       or selected_info["train_silhouette"] > selected_info["size_only_train_silhouette"])
                  and selected_info["nmi_with_training_size_quantile_bins"] < 0.85
                  and selected_info["mean_seed_pairwise_ari"] >= 0.70)
    # Final model and scaler are fitted only on the frozen 150-repository training group.
    final_scaler = scaler
    final_model = candidates[selected_k][0] if selected_k is not None else None
    test_z = final_scaler.transform(x_test)
    test_labels = final_model.predict(test_z) if final_model is not None else np.asarray([], dtype=int)
    profiles = {}
    for cluster_id in range(final_model.n_clusters if final_model is not None else 0):
        members = [row for row, label in zip(train, final_model.labels_) if label == cluster_id]
        means = {name: float(np.mean([row[name] for row in members])) for name in PATTERN_FEATURES}
        active, concentration = means["commit_active_fraction"], means["commit_top2_share"]
        if active >= 0.72 and concentration < 0.66:
            name = "持续活动型"
        elif concentration >= 0.66:
            name = "集中活动型"
        elif active < 0.42:
            name = "低活动型"
        else:
            name = "阶段波动型"
        profiles[str(cluster_id)] = {"name": name, "repositories": len(members), "feature_means": means,
                                     "median_commit_total_12w": float(np.median([row["commit_total_12w"] for row in members]))}
    if final_model is not None:
        artifact = {"model_id": "M1-maintenance-pattern", "version": "ml03-12w-150train-v1",
                    "status": "candidate", "feature_schema_version": FEATURE_SCHEMA_VERSION,
                    "feature_names": list(PATTERN_FEATURES), "cluster_count": int(selected_k),
                    "scaler_mean": final_scaler.mean_.tolist(), "scaler_scale": final_scaler.scale_.tolist(),
                    "centers_scaled": final_model.cluster_centers_.tolist(),
                    "cluster_profiles": profiles, "limitations": ["聚类描述近期行为，不代表质量、健康度或采用价值。"]}
        write_json(output / "candidates/ml03-maintenance-pattern-12w-150train-v1.json", artifact)
        write_json(CANDIDATE_DIR / "ml03-maintenance-pattern-12w-150train-v1.json", artifact)
        joblib.dump({"scaler": final_scaler, "model": final_model, "feature_names": PATTERN_FEATURES},
                    output / "candidates/ml03-maintenance-pattern-12w-150train-v1.joblib")
    test_silhouette = (float(silhouette_score(test_z, test_labels))
                       if final_model is not None and 1 < len(set(test_labels.tolist())) < len(test_labels) else None)
    size_cuts = candidates[selected_k][1] if selected_k is not None else []
    size_test = np.digitize([row["commit_total_12w"] for row in test], size_cuts, right=True) if selected_k else []
    test_size_silhouette = (float(silhouette_score(test_z, size_test))
                            if len(size_test) and 1 < len(set(size_test.tolist())) < len(size_test) else None)
    metrics = {"task": "M1 maintenance_pattern", "status": "candidate" if final_model is not None else "descriptive_only",
               "training_repositories": len(train), "test_repositories": len(test),
               "feature_schema_version": FEATURE_SCHEMA_VERSION, "feature_names": list(PATTERN_FEATURES),
               "candidate_comparison": comparisons, "selected_k": selected_k,
               "test_silhouette": test_silhouette,
               "size_only_test_silhouette": test_size_silhouette,
               "test_cluster_sizes": dict(Counter(map(int, test_labels))), "cluster_profiles": profiles,
               "deployment_eligible_by_training_checks": deploy,
               "decision": "生成独立候选；需完成留出分布与兼容检查后决定是否切换" if deploy else "保留统计画像，候选未达到训练集内基本条件",
               "decision_checks": {"beats_size_only_silhouette": selected_info.get("size_only_train_silhouette") is None or selected_info.get("train_silhouette", -1) > selected_info.get("size_only_train_silhouette", 1),
                                   "size_nmi_below_0_85": selected_info.get("nmi_with_training_size_quantile_bins", 1) < 0.85,
                                   "mean_seed_ari_at_least_0_70": selected_info.get("mean_seed_pairwise_ari", 0) >= 0.70}}
    save_rows(output / "datasets/maintenance_pattern_features.csv",
              ["repository_id", "repository", "commit_total_12w", *PATTERN_FEATURES], rows)
    save_rows(output / "evaluations/ml03-not-evaluable.csv", ["repository_id", "repository", "reason"], excluded)
    predictions = [{"repository_id": row["repository_id"], "repository": row["repository"],
                    "cluster": int(label), "pattern": profiles[str(int(label))]["name"],
                    "commit_total_12w": row["commit_total_12w"]}
                   for row, label in zip(test, test_labels)]
    save_rows(output / "evaluations/ml03-test-examples.csv", list(predictions[0]) if predictions else [], predictions)
    metrics["eligible_training_repositories"] = len(train)
    metrics["eligible_test_repositories"] = len(test)
    metrics["not_evaluable_repositories"] = len(excluded)
    metrics["test_size_nmi"] = (float(normalized_mutual_info_score(size_test, test_labels))
                                if len(size_test) and final_model is not None else None)
    write_json(output / "evaluations/ml03-maintenance-pattern.json", metrics)
    return metrics


def trend_samples(grouped):
    rows, exclusions = [], []
    for repo_id, weekly in grouped.items():
        normalized = [normalize_week(row) for row in weekly]
        # PR coverage is optional to the shared weekly contract; this task uses Commit-only features.
        for row in normalized:
            row["pr_created_coverage"] = "unavailable"
            row["prs_created"] = None
        counts = [row["commits"] for row in normalized]
        for origin in range(12, 49):
            history = normalized[origin - 12:origin]
            label_rows = normalized[origin - 4:origin + 4]
            if any(row["commit_coverage"] not in {"complete", "true_zero"} for row in (*history, *label_rows)):
                exclusions.append({"repository_id": repo_id, "repository": weekly[0]["repository"],
                                   "origin": origin, "reason": "incomplete_commit_coverage"})
                continue
            try:
                features = build_weekly_features(history)["trend_features"]
                label = trend_label(counts[origin - 4:origin], counts[origin:origin + 4])
            except (TypeError, ValueError) as exc:
                exclusions.append({"repository_id": repo_id, "repository": weekly[0]["repository"],
                                   "origin": origin, "reason": str(exc)})
                continue
            rows.append({"repository_id": repo_id, "repository": weekly[0]["repository"], "origin": origin,
                         "prediction_time": weekly[origin]["period_start"], "label_end": weekly[origin + 3]["period_end"],
                         "label": label, "baseline": recent_trend_baseline(counts[origin - 12:origin]),
                         "recent_4w_count": sum(counts[origin - 4:origin]), **features})
    return rows, exclusions


def class_metrics(actual, predicted):
    labels = ["下降", "基本稳定", "上升"]
    if not actual:
        return {"macro_f1": None, "balanced_accuracy": None, "confusion_matrix_labels": labels,
                "confusion_matrix": [[0, 0, 0] for _ in labels], "per_class": {},
                "actual_class_counts": {}, "predicted_class_counts": {}}
    precision, recall, f1, support = precision_recall_fscore_support(
        actual, predicted, labels=labels, zero_division=0)
    return {"macro_f1": float(f1_score(actual, predicted, labels=labels, average="macro", zero_division=0)),
            "balanced_accuracy": float(balanced_accuracy_score(actual, predicted)),
            "confusion_matrix_labels": labels,
            "confusion_matrix": confusion_matrix(actual, predicted, labels=labels).tolist(),
            "per_class": {label: {"precision": float(precision[index]), "recall": float(recall[index]),
                                  "f1": float(f1[index]), "support": int(support[index])}
                          for index, label in enumerate(labels)},
            "actual_class_counts": dict(Counter(actual)), "predicted_class_counts": dict(Counter(predicted))}


def trend_training(grouped, splits, output):
    samples, exclusions = trend_samples(grouped)
    ids = splits
    all_features = list(TREND_FEATURES)
    validation_by_model = defaultdict(lambda: {"actual": [], "predicted": []})
    fold_rows = []
    constructors = {}
    for class_weight in (None, "balanced"):
        for c_value in (0.1, 1.0, 3.0):
            key = f"logistic_regression_c{c_value:g}_{'balanced' if class_weight else 'unweighted'}"
            constructors[key] = lambda c=c_value, weight=class_weight: make_pipeline(
                StandardScaler(), LogisticRegression(C=c, max_iter=1000, class_weight=weight, random_state=SEED))
    constructors["hist_gradient_boosting"] = lambda: HistGradientBoostingClassifier(
        max_iter=120, max_leaf_nodes=7, min_samples_leaf=25, learning_rate=0.08,
        l2_regularization=1.0, random_state=SEED)
    for origin in (40, 44):
        training = [row for row in samples if row["repository_id"] in ids["train"] and row["origin"] + 4 <= origin]
        validation = [row for row in samples if row["repository_id"] in ids["train"] and row["origin"] == origin]
        x_train = np.asarray([[row[name] for name in all_features] for row in training], dtype=float)
        y_train = np.asarray([row["label"] for row in training])
        x_valid = np.asarray([[row[name] for name in all_features] for row in validation], dtype=float)
        y_valid = [row["label"] for row in validation]
        latest_training_label_end = max(row["label_end"] for row in training)
        validation_prediction_time = validation[0]["prediction_time"] if validation else None
        if not validation or latest_training_label_end > validation_prediction_time:
            raise ValueError(f"training labels cross validation origin {origin}")
        fold = {"origin": origin, "training_samples": len(training),
                "latest_training_label_end": latest_training_label_end,
                "validation_prediction_time": validation_prediction_time,
                "validation_samples": len(validation), "metrics": {}}
        for name, make_model in constructors.items():
            model = make_model().fit(x_train, y_train)
            predicted = model.predict(x_valid).tolist()
            validation_by_model[name]["actual"].extend(y_valid)
            validation_by_model[name]["predicted"].extend(predicted)
            fold["metrics"][name] = class_metrics(y_valid, predicted)
        baseline = [row["baseline"] for row in validation]
        validation_by_model["recent_trend_baseline"]["actual"].extend(y_valid)
        validation_by_model["recent_trend_baseline"]["predicted"].extend(baseline)
        fold["metrics"]["recent_trend_baseline"] = class_metrics(y_valid, baseline)
        fold_rows.append(fold)
    combined = {name: class_metrics(value["actual"], value["predicted"])
                for name, value in validation_by_model.items()}
    logistic_candidates = [name for name in constructors if name.startswith("logistic_regression_")]
    def score_key(name):
        metric = combined[name]
        rising = metric["per_class"].get("上升", {})
        return (metric["macro_f1"] or -1, metric["balanced_accuracy"] or -1,
                rising.get("f1", -1), rising.get("precision", -1), rising.get("recall", -1))
    selected_candidate = max(logistic_candidates, key=score_key)
    final_origin = 48
    training = [row for row in samples if row["repository_id"] in ids["train"] and row["origin"] + 4 <= final_origin]
    x_train = np.asarray([[row[name] for name in all_features] for row in training], dtype=float)
    y_train = np.asarray([row["label"] for row in training])
    final_model = constructors[selected_candidate]().fit(x_train, y_train)
    test = [row for row in samples if row["repository_id"] in ids["test"] and row["origin"] == final_origin]
    x_test = np.asarray([[row[name] for name in all_features] for row in test], dtype=float)
    actual = [row["label"] for row in test]
    test_prediction = final_model.predict(x_test).tolist()
    baselines = [row["baseline"] for row in test]
    dummy_class = Counter(y_train).most_common(1)[0][0]
    test_metrics = {"selected_candidate": class_metrics(actual, test_prediction),
                    "dummy_most_frequent": class_metrics(actual, [dummy_class] * len(test)),
                    "recent_trend_baseline": class_metrics(actual, baselines),
                    "by_recent_activity": {}}
    for tier, predicate in (("zero", lambda value: value == 0), ("1-9", lambda value: 1 <= value <= 9),
                            ("10-99", lambda value: 10 <= value <= 99), ("100+", lambda value: value >= 100)):
        indexes = [index for index, row in enumerate(test) if predicate(row["recent_4w_count"])]
        if indexes:
            majority = dummy_class
            test_metrics["by_recent_activity"][tier] = {
                "samples": len(indexes),
                "selected_candidate": class_metrics([actual[i] for i in indexes], [test_prediction[i] for i in indexes]),
                "dummy_most_frequent": class_metrics([actual[i] for i in indexes], [majority] * len(indexes)),
                "recent_trend_baseline": class_metrics([actual[i] for i in indexes], [baselines[i] for i in indexes]),
            }
    estimator = final_model.named_steps["logisticregression"]
    scaler = final_model.named_steps["standardscaler"]
    artifact = {"model_id": "M2-activity-trend", "version": "ml01-trend-12w-150train-v1",
                "status": "candidate", "feature_schema_version": FEATURE_SCHEMA_VERSION,
                "feature_names": all_features, "classes": estimator.classes_.tolist(),
                "scaler_mean": scaler.mean_.tolist(), "scaler_scale": scaler.scale_.tolist(),
                "coefficients": estimator.coef_.tolist(), "intercepts": estimator.intercept_.tolist(),
                "limitations": ["类别预测不代表精确 Commit 数量；无校准概率。", "历史回测复用既有 300 仓库，不是未见过的全新数据集。"]}
    write_json(output / "candidates/ml01-activity-trend-12w-150train-v1.json", artifact)
    write_json(CANDIDATE_DIR / "ml01-activity-trend-12w-150train-v1.json", artifact)
    joblib.dump(final_model, output / "candidates/ml01-activity-trend-12w-150train-v1.joblib")
    manifest_fields = ["repository_id", "repository", "origin", "prediction_time", "label_end", *all_features,
                       "recent_4w_count", "label", "baseline"]
    save_rows(output / "datasets/activity_trend_windows.csv", manifest_fields, samples)
    save_rows(output / "evaluations/ml01-test-predictions.csv",
              ["repository_id", "repository", "prediction_time", "actual", "predicted", "recent_trend_baseline", "recent_4w_count"],
              [{"repository_id": row["repository_id"], "repository": row["repository"],
                "prediction_time": row["prediction_time"], "actual": actual[i], "predicted": test_prediction[i],
                "recent_trend_baseline": baselines[i], "recent_4w_count": row["recent_4w_count"]}
               for i, row in enumerate(test)])
    ml_beats_both_baselines = (test_metrics["selected_candidate"]["macro_f1"]
                               > max(test_metrics["dummy_most_frequent"]["macro_f1"],
                                     test_metrics["recent_trend_baseline"]["macro_f1"]))
    metrics = {"task": "M2 activity_trend", "status": "candidate",
               "training_repositories": len(ids["train"]), "test_repositories": len(ids["test"]),
               "eligible_training_repositories": len({row["repository_id"] for row in training}),
               "eligible_test_repositories": len({row["repository_id"] for row in test}),
               "not_evaluable_test_repositories": len(ids["test"] - {row["repository_id"] for row in test}),
               "not_evaluable_windows": len(exclusions), "samples": len(samples), "feature_schema_version": FEATURE_SCHEMA_VERSION,
               "feature_names": all_features, "label_definition": "future4 vs preceding4; direction requires max(3 commits, 25% of past4) absolute change",
               "validation_folds": fold_rows, "validation_combined": combined,
               "selected_candidate": selected_candidate,
               "selected_parameters": {"C": float(selected_candidate.split("_c", 1)[1].split("_", 1)[0]),
                                       "class_weight": "balanced" if selected_candidate.endswith("balanced") else None},
               "test_ml_beats_both_baselines": ml_beats_both_baselines,
               "test_origin": test[0]["prediction_time"] if test else None, "test": test_metrics,
               "decision": "候选模型在本轮留出测试上优于两种基线，可进入兼容性/课程版切换审查" if ml_beats_both_baselines else "保留既有线上模型，不启用本轮候选；只展示历史事实",
               "limitations": ["300 仓库和早期窗口已用于此前研究；这是重新设计后的历史回测。",
                               "同仓库窗口重叠，指标仅用于组间留仓检验，不把窗口视为独立仓库。"]}
    write_json(output / "evaluations/ml01-activity-trend.json", metrics)
    save_rows(output / "evaluations/ml01-not-evaluable-windows.csv",
              ["repository_id", "repository", "origin", "reason"], exclusions)
    return metrics


def main():
    global SOURCE, CANDIDATE_DIR
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--split-manifest", type=Path, default=SPLIT_DEFAULT)
    parser.add_argument("--candidate-dir", type=Path, default=CANDIDATE_DEFAULT)
    args = parser.parse_args()
    SOURCE = args.source
    CANDIDATE_DIR = args.candidate_dir
    if args.output.exists() or CANDIDATE_DIR.exists():
        raise SystemExit("Output or candidate directory already exists; choose new paths to preserve earlier evidence")
    actual_source_sha256 = sha256(SOURCE)
    if actual_source_sha256 != EXPECTED_SOURCE_SHA256:
        raise SystemExit(f"Source SHA-256 mismatch; expected {EXPECTED_SOURCE_SHA256}, found {actual_source_sha256}")
    grouped = load_weekly()
    splits, split_manifest = load_split_manifest(args.split_manifest, grouped)
    args.output.mkdir(parents=True)
    CANDIDATE_DIR.mkdir(parents=True)
    pattern = pattern_training(grouped, splits, args.output)
    trend = trend_training(grouped, splits, args.output)
    anomaly = {"task": "M3 activity_anomaly", "status": "preserved_mad_rule", "retrained": False,
               "rule": "previous 11 complete weeks log1p median and MAD; flag absolute robust z >= 3",
               "decision": "沿用现有统计异常提示；本轮没有重训 Isolation Forest。"}
    write_json(args.output / "evaluations/ml06-activity-anomaly.json", anomaly)
    split_sha256 = sha256(args.split_manifest)
    write_json(args.output / "split_summary.json", {
        "manifest_path": str(args.split_manifest.relative_to(ROOT)),
        "manifest_sha256": split_sha256, "source_sha256": actual_source_sha256,
        "split_version": split_manifest["split_version"], "seed": split_manifest["seed"],
        "split_unit": split_manifest["split_unit"], "train_count": len(splits["train"]),
        "test_count": len(splits["test"]), "train_ids_sha256": split_manifest["train_ids_sha256"],
        "test_ids_sha256": split_manifest["test_ids_sha256"],
        "test_usage": "single_final_evaluation_only",
    })
    manifest = {"status": "course_research", "source": str(SOURCE.relative_to(ROOT)),
                "source_sha256": actual_source_sha256, "dataset_id": "repo-evaluation-2026-v1",
                "repositories": len(grouped), "weekly_rows": sum(map(len, grouped.values())),
                "weeks_per_repository": sorted(set(map(len, grouped.values()))),
                "feature_schema_version": FEATURE_SCHEMA_VERSION,
                "split_version": split_manifest["split_version"], "split_manifest_sha256": split_sha256,
                "seed": split_manifest["seed"], "python": platform.python_version(), "numpy": np.__version__,
                "scikit_learn": sklearn.__version__, "split": {"train": len(splits["train"]), "test": len(splits["test"])},
                "tasks": {"M1": pattern["status"], "M2": trend["status"], "M3": anomaly["status"]},
                "data_scope": "既有 300 仓库 52 周聚合资料；不是新采集的独立测试集。"}
    write_json(args.output / "manifest.json", manifest)
    print(json.dumps({"output": str(args.output), "candidate_dir": str(CANDIDATE_DIR),
                      "tasks": {"M1": pattern["status"], "M2": trend["status"], "M3": anomaly["status"]}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
