"""Curated, read-only model evaluation data for the separate ML console."""

from __future__ import annotations

import json
import math
import csv
from pathlib import Path
from typing import Any

from backend.app.core.config import PROJECT_ROOT


EXPERIMENT = PROJECT_ROOT / "ml" / "course" / "experiments" / "course-150-150-v1"
EVALUATIONS = EXPERIMENT / "evaluations"
MAX_FILE_BYTES = 2_000_000


def _read_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("evaluation_artifact_too_large")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("evaluation_artifact_invalid")
    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("evaluation_artifact_too_large")
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def _number(value: Any) -> float | None:
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    return float(value)


def _parse_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _score(value: Any) -> dict[str, float | None]:
    item = value if isinstance(value, dict) else {}
    return {
        "macro_f1": _number(item.get("macro_f1")),
        "balanced_accuracy": _number(item.get("balanced_accuracy")),
    }


def _confusion_matrix(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    matrix = value.get("confusion_matrix")
    labels = value.get("confusion_matrix_labels")
    if (not isinstance(matrix, list) or not isinstance(labels, list) or not labels
            or len(matrix) != len(labels) or any(not isinstance(row, list) or len(row) != len(labels) for row in matrix)
            or any(type(count) is not int or count < 0 for row in matrix for count in row)):
        return None
    return {"labels": labels, "values": matrix}


def evaluation_dashboard() -> dict[str, Any]:
    """Return only the metrics needed by the local model observability frontend."""
    try:
        manifest = _read_json(EXPERIMENT / "manifest.json")
        pattern = _read_json(EVALUATIONS / "ml03-maintenance-pattern.json")
        trend = _read_json(EVALUATIONS / "ml01-activity-trend.json")
        pattern_features = _read_csv(EXPERIMENT / "datasets" / "maintenance_pattern_features.csv")
        pattern_test_predictions = _read_csv(EVALUATIONS / "ml03-test-examples.csv")
    except (OSError, ValueError, TypeError):
        return {"status": "unavailable", "reason": "评估文件缺失或格式无效。"}

    split = manifest.get("split") if isinstance(manifest.get("split"), dict) else {}
    selected_k = pattern.get("selected_k")
    candidates = pattern.get("candidate_comparison") if isinstance(pattern.get("candidate_comparison"), dict) else {}
    candidate = candidates.get(str(selected_k), {})
    candidate = candidate if isinstance(candidate, dict) else {}
    test_clusters = pattern.get("test_cluster_sizes") if isinstance(pattern.get("test_cluster_sizes"), dict) else {}
    profiles = pattern.get("cluster_profiles") if isinstance(pattern.get("cluster_profiles"), dict) else {}
    clusters = []
    for cluster_id, count in sorted(test_clusters.items(), key=lambda item: str(item[0])):
        if type(count) is not int or count < 0:
            continue
        profile = profiles.get(str(cluster_id), {})
        clusters.append({
            "id": str(cluster_id),
            "name": profile.get("name") if isinstance(profile, dict) else None,
            "repositories": count,
        })
    features_by_repository = {}
    for row in pattern_features:
        try:
            repository_id = int(row.get("repository_id", ""))
        except (TypeError, ValueError):
            continue
        features_by_repository[repository_id] = row
    test_points = []
    for row in pattern_test_predictions:
        try:
            repository_id = int(row.get("repository_id", ""))
            cluster_id = str(int(row.get("cluster", "")))
        except (TypeError, ValueError):
            continue
        feature_row = features_by_repository.get(repository_id)
        if feature_row is None:
            continue
        active_week_ratio = _number(_parse_number(feature_row.get("commit_active_fraction")))
        no_commit_week_ratio = _number(_parse_number(feature_row.get("commit_longest_zero_fraction")))
        if active_week_ratio is None or no_commit_week_ratio is None:
            continue
        test_points.append({
            "repository_id": repository_id,
            "repository": row.get("repository"),
            "cluster_id": cluster_id,
            "cluster_name": row.get("pattern") or profiles.get(cluster_id, {}).get("name"),
            "active_week_ratio": active_week_ratio,
            "no_commit_week_ratio": no_commit_week_ratio,
            "commits_12w": _number(_parse_number(feature_row.get("commit_total_12w"))),
        })

    trend_validation = trend.get("validation_combined") if isinstance(trend.get("validation_combined"), dict) else {}
    trend_test = trend.get("test") if isinstance(trend.get("test"), dict) else {}
    selected_candidate_id = trend.get("selected_candidate")
    trend_model_ids = [model_id for model_id in (selected_candidate_id, "recent_trend_baseline", "dummy_most_frequent")
                       if isinstance(model_id, str)]
    trend_benchmarks = []
    for model_id in trend_model_ids:
        validation = trend_validation.get(model_id, {})
        test = trend_test.get("selected_candidate", {}) if model_id == selected_candidate_id else trend_test.get(model_id, {})
        if not isinstance(validation, dict) or not isinstance(test, dict):
            continue
        trend_benchmarks.append({
            "id": model_id,
            "name": "逻辑回归（当前候选）" if model_id == selected_candidate_id else {
                "recent_trend_baseline": "近期趋势基线",
                "dummy_most_frequent": "多数类基线",
            }.get(model_id, model_id),
            "selected": model_id == selected_candidate_id,
            "validation": _score(validation),
            "test": _score(test),
        })

    selected_test = trend_test.get("selected_candidate", {})
    selected_validation = trend_validation.get(selected_candidate_id, {})
    validation_series = []
    folds = trend.get("validation_folds") if isinstance(trend.get("validation_folds"), list) else []
    for index, fold in enumerate(folds, start=1):
        if not isinstance(fold, dict):
            continue
        fold_metrics = fold.get("metrics") if isinstance(fold.get("metrics"), dict) else {}
        selected_fold = fold_metrics.get(selected_candidate_id, {})
        baseline_fold = fold_metrics.get("recent_trend_baseline", {})
        validation_series.append({
            "label": f"验证折 {index}",
            "as_of": (fold.get("latest_training_label_end") or "")[:10],
            "samples": fold.get("validation_samples"),
            "macro_f1": _number(selected_fold.get("macro_f1")) if isinstance(selected_fold, dict) else None,
            "baseline_macro_f1": _number(baseline_fold.get("macro_f1")) if isinstance(baseline_fold, dict) else None,
            "balanced_accuracy": _number(selected_fold.get("balanced_accuracy")) if isinstance(selected_fold, dict) else None,
            "baseline_balanced_accuracy": _number(baseline_fold.get("balanced_accuracy")) if isinstance(baseline_fold, dict) else None,
        })
    validation_series.append({
        "label": "独立测试",
        "as_of": (trend.get("test_origin") or "")[:10],
        "samples": trend.get("test_repositories"),
        "macro_f1": _number(selected_test.get("macro_f1")) if isinstance(selected_test, dict) else None,
        "baseline_macro_f1": _number(trend_test.get("recent_trend_baseline", {}).get("macro_f1")),
        "balanced_accuracy": _number(selected_test.get("balanced_accuracy")) if isinstance(selected_test, dict) else None,
        "baseline_balanced_accuracy": _number(trend_test.get("recent_trend_baseline", {}).get("balanced_accuracy")),
    })
    return {
        "status": "available",
        "dataset": {
            "id": manifest.get("dataset_id"),
            "status": manifest.get("status"),
            "repositories": manifest.get("repositories"),
            "weekly_rows": manifest.get("weekly_rows"),
            "weeks_per_repository": (manifest.get("weeks_per_repository") or [None])[0],
            "split": {"train": split.get("train"), "validation": split.get("validation"), "test": split.get("test")},
            "feature_schema_version": manifest.get("feature_schema_version"),
            "source_sha256": manifest.get("source_sha256"),
            "scope": manifest.get("data_scope"),
            "split_version": manifest.get("split_version"),
        },
        "models": [
            {
                "id": "M1",
                "name": "近期维护模式聚类",
                "version": "ml03-12w-150train-v1",
                "algorithm": "K-Means",
                "kind": "聚类",
                "feature_schema_version": pattern.get("feature_schema_version"),
                "selected_clusters": selected_k,
                "samples": {
                    "train_repositories": pattern.get("training_repositories"),
                    "validation_repositories": pattern.get("validation_repositories"),
                    "test_repositories": pattern.get("test_repositories"),
                },
                "silhouette": {
                    "train": _number(candidate.get("train_silhouette")),
                    "seed_mean": _number(candidate.get("seed_silhouette_mean")),
                    "test": _number(pattern.get("test_silhouette")),
                },
                "size_only_train_silhouette": _number(candidate.get("size_only_train_silhouette")),
                "test_clusters": clusters,
                "test_points": test_points,
                "candidates": [
                    {
                        "clusters": int(key),
                        "train_silhouette": _number(value.get("train_silhouette")),
                        "size_only_train_silhouette": _number(value.get("size_only_train_silhouette")),
                        "seed_silhouette_mean": _number(value.get("seed_silhouette_mean")),
                        "selected": str(key) == str(selected_k),
                    }
                    for key, value in candidates.items()
                    if str(key).isdigit() and isinstance(value, dict)
                ],
                "notes": [
                    "轮廓系数衡量簇内紧密度与簇间分离度，不是分类准确率。",
                    "簇名称是对历史活动形态的描述，不代表项目质量或推荐结论。",
                ],
            },
            {
                "id": "M2",
                "name": "近期活动趋势预测",
                "version": "ml01-trend-12w-150train-v1",
                "algorithm": "逻辑回归",
                "kind": "三分类",
                "feature_schema_version": trend.get("feature_schema_version"),
                "selected_candidate": trend.get("selected_candidate"),
                "samples": {
                    "training_repositories": trend.get("training_repositories"),
                    "validation_folds": len(trend.get("validation_folds", [])) if isinstance(trend.get("validation_folds"), list) else None,
                    "validation_samples_per_fold": (trend.get("validation_folds") or [{}])[0].get("validation_samples")
                    if isinstance(trend.get("validation_folds"), list) and trend.get("validation_folds") else None,
                    "test_repositories": trend.get("test_repositories"),
                },
                "validation": _score(selected_validation),
                "test": _score(selected_test),
                "test_confusion_matrix": _confusion_matrix(selected_test),
                "benchmarks": trend_benchmarks,
                "validation_series": validation_series,
                "label_definition": trend.get("label_definition"),
                "notes": trend.get("limitations") if isinstance(trend.get("limitations"), list) else [],
            },
        ],
    }
