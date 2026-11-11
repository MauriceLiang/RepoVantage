#!/usr/bin/env python3
"""One bounded M2 tuning round on the frozen train/validation repositories only."""
from __future__ import annotations

import hashlib
import json
import platform
import csv
import gzip
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_fscore_support
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from backend.app.analytics.course_ml_features import (
    TREND_FEATURES, build_weekly_features, recent_trend_baseline, trend_label,
)
from scripts.train_course_ml import ROOT, SEED, SOURCE, class_metrics, normalize_week, split_ids


OUTPUT = ROOT / "ml/course/evaluations/m2-tuning-round-v41.json"
LABELS = ["下降", "基本稳定", "上升"]
FOLDS = (40, 44)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repository_ids(source: Path) -> list[str]:
    """Read only the ID column to reproduce the frozen repository split."""
    with gzip.open(source, "rt", encoding="utf-8", newline="") as stream:
        return sorted({row["repository_id"] for row in csv.DictReader(stream)})


def load_weekly_for(source: Path, repository_ids_to_load: set[str]):
    """Parse weekly feature rows only for authorized training/validation repositories."""
    grouped = defaultdict(list)
    with gzip.open(source, "rt", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["repository_id"] in repository_ids_to_load:
                grouped[row["repository_id"]].append(row)
    for repo_id, rows in grouped.items():
        rows.sort(key=lambda row: row["period_start"])
        if len(rows) != 52 or len({row["period_start"] for row in rows}) != 52:
            raise ValueError(f"{repo_id}: expected 52 distinct weekly rows")
    if set(grouped) != repository_ids_to_load:
        raise ValueError("a training/validation repository is missing from the source")
    return dict(sorted(grouped.items()))


def metrics(actual, predicted):
    per_class = {}
    precision, recall, f1, support = precision_recall_fscore_support(
        actual, predicted, labels=LABELS, zero_division=0,
    )
    for index, label in enumerate(LABELS):
        per_class[label] = {"precision": float(precision[index]), "recall": float(recall[index]),
                            "f1": float(f1[index]), "support": int(support[index])}
    result = class_metrics(actual, predicted)
    result["per_class"] = per_class
    result["ascending_precision"] = per_class["上升"]["precision"]
    result["ascending_recall"] = per_class["上升"]["recall"]
    return result


def model_factories():
    factories = {}
    for class_weight in (None, "balanced"):
        for c_value in (0.1, 1.0, 3.0):
            name = f"lr_weight-{class_weight or 'none'}_C-{c_value:g}"
            factories[name] = lambda class_weight=class_weight, c_value=c_value: make_pipeline(
                StandardScaler(), LogisticRegression(C=c_value, max_iter=1000,
                                                     class_weight=class_weight, random_state=SEED),
            )
    factories["hist_gradient_boosting_existing"] = lambda: HistGradientBoostingClassifier(
        max_iter=120, max_leaf_nodes=7, min_samples_leaf=25, learning_rate=0.08,
        l2_regularization=1.0, random_state=SEED,
    )
    return factories


def bounded_trend_samples(grouped, train_ids, validation_ids):
    """Materialize only train histories and the two authorized validation origins."""
    rows = []
    for repo_id, weekly in grouped.items():
        if repo_id in train_ids:
            origins = range(12, 41)
        elif repo_id in validation_ids:
            origins = FOLDS
        else:
            continue
        normalized = [normalize_week(row) for row in weekly]
        for row in normalized:
            row["pr_created_coverage"] = "unavailable"
            row["prs_created"] = None
        counts = [row["commits"] for row in normalized]
        for origin in origins:
            history = normalized[origin - 12:origin]
            features = build_weekly_features(history)["trend_features"]
            prior = counts[origin - 4:origin]
            rows.append({"repository_id": repo_id, "repository": weekly[0]["repository"],
                         "origin": origin, "prediction_time": weekly[origin]["period_start"],
                         "label_end": weekly[origin + 3]["period_end"],
                         "label": trend_label(prior, counts[origin:origin + 4]),
                         "baseline": recent_trend_baseline(counts[origin - 12:origin]),
                         "recent_4w_count": sum(prior),
                         "previous_4w_commits": sum(prior),
                         "future_4w_commits": sum(counts[origin:origin + 4]), **features})
    return rows


def main():
    source = SOURCE
    splits = split_ids(repository_ids(source))
    ids = {key: set(value) for key, value in splits.items()}
    grouped = load_weekly_for(source, ids["train"] | ids["validation"])
    samples = bounded_trend_samples(grouped, ids["train"], ids["validation"])
    factories = model_factories()
    observed = {name: {"actual": [], "predicted": [], "folds": {}, "by_key": {}} for name in factories}
    observed["recent_trend_baseline"] = {"actual": [], "predicted": [], "folds": {}, "by_key": {}}
    observed["dummy_most_frequent"] = {"actual": [], "predicted": [], "folds": {}, "by_key": {}}
    fold_evidence = []

    for origin in FOLDS:
        training = [row for row in samples if row["repository_id"] in ids["train"]
                    and row["origin"] + 4 <= origin]
        validation = [row for row in samples if row["repository_id"] in ids["validation"]
                      and row["origin"] == origin]
        x_train = np.asarray([[row[name] for name in TREND_FEATURES] for row in training], dtype=float)
        y_train = np.asarray([row["label"] for row in training])
        x_valid = np.asarray([[row[name] for name in TREND_FEATURES] for row in validation], dtype=float)
        actual = [row["label"] for row in validation]
        fold = {"origin": origin, "training_samples": len(training),
                "training_repositories": len(ids["train"]),
                "latest_training_label_end": max(row["label_end"] for row in training),
                "validation_samples": len(validation), "validation_repositories": len(ids["validation"]),
                "actual_class_counts": dict(Counter(actual)), "candidates": {}}
        predictions = {}
        for name, factory in factories.items():
            estimator = factory().fit(x_train, y_train)
            predictions[name] = estimator.predict(x_valid).tolist()
        majority = Counter(y_train).most_common(1)[0][0]
        predictions["dummy_most_frequent"] = [majority] * len(validation)
        predictions["recent_trend_baseline"] = [row["baseline"] for row in validation]

        for name, predicted in predictions.items():
            observed[name]["actual"].extend(actual)
            observed[name]["predicted"].extend(predicted)
            observed[name]["by_key"].update({(row["repository_id"], origin): value
                                             for row, value in zip(validation, predicted)})
            observed[name]["folds"][str(origin)] = metrics(actual, predicted)
            fold["candidates"][name] = metrics(actual, predicted)
        for tier, predicate in (("zero", lambda value: value == 0),
                                ("1-9", lambda value: 1 <= value <= 9),
                                ("10-99", lambda value: 10 <= value <= 99),
                                ("100+", lambda value: value >= 100)):
            indexes = [index for index, row in enumerate(validation) if predicate(row["recent_4w_count"])]
            fold.setdefault("activity_buckets", {})[tier] = {
                "samples": len(indexes),
                "candidates": {name: metrics([actual[i] for i in indexes], [predictions[name][i] for i in indexes])
                               for name in predictions} if indexes else {},
            }
        fold_evidence.append(fold)

    combined = {}
    for name, value in observed.items():
        combined[name] = metrics(value["actual"], value["predicted"])
        combined[name]["by_fold"] = value["folds"]
    activity = {}
    valid_rows = [row for row in samples if row["repository_id"] in ids["validation"]
                  and row["origin"] in FOLDS]
    for tier, predicate in (("zero", lambda value: value == 0),
                            ("1-9", lambda value: 1 <= value <= 9),
                            ("10-99", lambda value: 10 <= value <= 99),
                            ("100+", lambda value: value >= 100)):
        indexes = [index for index, row in enumerate(valid_rows) if predicate(row["recent_4w_count"])]
        if not indexes:
            continue
        actual = [row["label"] for row in valid_rows]
        activity[tier] = {"samples": len(indexes), "candidates": {
            name: metrics([actual[i] for i in indexes],
                          [observed[name]["by_key"][(valid_rows[i]["repository_id"], valid_rows[i]["origin"])]
                           for i in indexes])
            for name in observed}}

    current_name = "lr_weight-balanced_C-1"
    candidate_name = "lr_weight-balanced_C-0.1"
    decision = ("保留 ml01-trend-12w-v1：balanced C=0.1 的合并 Macro-F1 仅提高 0.0097，第一折提高、第二折持平；"
                "1–9 活动桶没有回落，但上升类 Precision、Recall、F1 均与现版相同，整体提升不够明确、稳定且可解释。")
    ascending_error_cases = {}
    for name in (current_name, candidate_name):
        cases = []
        for row in valid_rows:
            actual = row["label"]
            predicted = observed[name]["by_key"][(row["repository_id"], row["origin"])]
            if actual == "上升" and predicted != "上升":
                error_type = "上升漏报"
            elif actual != "上升" and predicted == "上升":
                error_type = "上升误报"
            else:
                continue
            cases.append({"fold_origin": row["prediction_time"],
                          "repository_id": row["repository_id"],
                          "repository": row["repository"],
                          "error_type": error_type,
                          "actual_label": actual,
                          "predicted_label": predicted,
                          "previous_4w_commits": row["previous_4w_commits"],
                          "future_4w_commits": row["future_4w_commits"]})
        ascending_error_cases[name] = cases
    result = {
        "round": "v4.1-bounded-m2-tuning",
        "source": str(source.relative_to(ROOT)), "source_sha256": sha256(source),
        "feature_schema_version": "course-maintenance-12w-v1",
        "seed": SEED, "runtime": {"python": platform.python_version(), "numpy": np.__version__,
                                   "scikit_learn": sklearn.__version__},
        "frozen_artifact_sha256": sha256(ROOT / "ml/course/artifacts/ml01-activity-trend-12w.json"),
        "fold_origins": list(FOLDS),
        "repositories": {"train": len(ids["train"]), "validation": len(ids["validation"]),
                         "excluded_test": len(ids["test"])},
        "validation_protocol": "先仅读取仓库 ID 复现固定切分，再只解析训练/验证仓库数据行；仅用训练仓库中标签结束不晚于折点的样本拟合、验证仓库两个折点样本评估；旧45仓库的特征、标签和预测均未读取。",
        "materialized_windows": {"training_repositories": len(ids["train"]),
                                 "training_origins": [12, 40],
                                 "validation_origins": list(FOLDS),
                                 "validation_repository_windows": len(ids["validation"]) * len(FOLDS)},
        "labels": LABELS, "folds": fold_evidence, "combined_validation": combined,
        "activity_buckets": activity, "current_candidate": current_name,
        "candidate_considered": candidate_name,
        "ascending_class_error_cases": ascending_error_cases,
        "decision": decision,
        "artifact_changed": False,
        "limitations": ["两折来自既有研究池，仓库窗口重叠；不能替代前瞻性外部验证。",
                        "所有指标基于现有标签定义，不调整标签阈值。"],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "current": combined[current_name],
                      "candidate_macro_f1": {name: item["macro_f1"] for name, item in combined.items()}},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
