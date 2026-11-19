"""Read-only charts for the frozen 150/150 course evaluation artifacts."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from backend.app.core.config import PROJECT_ROOT
from backend.app.core.exceptions import AppError


EVALUATION_ROOT = PROJECT_ROOT / "ml/course/experiments/course-150-150-v1/evaluations"
DATASET_VERSION = "course-150-150-v1"


def _read_artifact(root: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads((root / name).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AppError(503, "BACKEND_UNAVAILABLE", "冻结的机器学习评估资料暂不可用") from exc
    if not isinstance(value, dict):
        raise AppError(503, "BACKEND_UNAVAILABLE", "冻结的机器学习评估资料格式无效")
    return value


def _number(value: Any) -> float:
    if type(value) not in (float, int) or not math.isfinite(value):
        raise AppError(503, "BACKEND_UNAVAILABLE", "冻结的机器学习评估资料包含无效数值")
    return float(value)


def _count(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise AppError(503, "BACKEND_UNAVAILABLE", "冻结的机器学习评估资料包含无效计数")
    return value


def _performance(label: str, model_id: str, source: dict[str, Any]) -> dict[str, Any]:
    per_class = source.get("per_class")
    if not isinstance(per_class, dict):
        raise AppError(503, "BACKEND_UNAVAILABLE", "冻结的机器学习类别指标缺失")
    classes: dict[str, dict[str, float | int]] = {}
    for class_name, row in per_class.items():
        if not isinstance(class_name, str) or not isinstance(row, dict):
            raise AppError(503, "BACKEND_UNAVAILABLE", "冻结的机器学习类别指标格式无效")
        classes[class_name] = {
            "precision": _number(row.get("precision")),
            "recall": _number(row.get("recall")),
            "f1": _number(row.get("f1")),
            "support": _count(row.get("support")),
        }
    up = classes.get("上升")
    if up is None:
        raise AppError(503, "BACKEND_UNAVAILABLE", "冻结的机器学习上升类指标缺失")
    return {
        "label": label,
        "model_id": model_id,
        "macro_f1": _number(source.get("macro_f1")),
        "balanced_accuracy": _number(source.get("balanced_accuracy")),
        "up_precision": up["precision"],
        "up_recall": up["recall"],
        "up_f1": up["f1"],
        "class_metrics": classes,
    }


def course_machine_learning_evaluation(root: Path = EVALUATION_ROOT) -> dict[str, Any]:
    """Return verified, aggregate metrics only; no sample predictions are exposed."""
    m1 = _read_artifact(root, "ml03-maintenance-pattern.json")
    m2 = _read_artifact(root, "ml01-activity-trend.json")
    m3 = _read_artifact(root, "ml06-activity-anomaly.json")
    if (m1.get("task") != "M1 maintenance_pattern" or m1.get("status") != "candidate"
            or m2.get("task") != "M2 activity_trend" or m2.get("status") != "candidate"
            or m3.get("task") != "M3 activity_anomaly" or m3.get("status") != "preserved_mad_rule"
            or m1.get("eligible_training_repositories") != 150 or m1.get("eligible_test_repositories") != 150
            or m2.get("training_repositories") != 150 or m2.get("test_repositories") != 150):
        raise AppError(503, "BACKEND_UNAVAILABLE", "机器学习评估版本与固定 150/150 数据集不匹配")

    selected_k = m1.get("selected_k")
    comparison = m1.get("candidate_comparison")
    profiles = m1.get("cluster_profiles")
    cluster_sizes = m1.get("test_cluster_sizes")
    if (type(selected_k) is not int or not isinstance(comparison, dict) or not isinstance(profiles, dict)
            or not isinstance(cluster_sizes, dict) or str(selected_k) not in comparison):
        raise AppError(503, "BACKEND_UNAVAILABLE", "M1 聚类评估资料不完整")
    selected_comparison = comparison[str(selected_k)]
    cluster_counts = []
    for cluster_id, size in sorted(cluster_sizes.items(), key=lambda item: str(item[0])):
        profile = profiles.get(str(cluster_id))
        if not isinstance(profile, dict) or not isinstance(profile.get("name"), str):
            raise AppError(503, "BACKEND_UNAVAILABLE", "M1 测试簇资料不完整")
        cluster_counts.append({"label": profile["name"], "count": _count(size)})
    if sum(row["count"] for row in cluster_counts) != 150:
        raise AppError(503, "BACKEND_UNAVAILABLE", "M1 测试簇数量与固定留出集不一致")

    test = m2.get("test")
    if not isinstance(test, dict):
        raise AppError(503, "BACKEND_UNAVAILABLE", "M2 留出评估资料缺失")
    selected_id = m2.get("selected_candidate")
    selected = test.get("selected_candidate")
    recent = test.get("recent_trend_baseline")
    dummy = test.get("dummy_most_frequent")
    if not isinstance(selected_id, str) or not all(isinstance(row, dict) for row in (selected, recent, dummy)):
        raise AppError(503, "BACKEND_UNAVAILABLE", "M2 候选模型或基线资料不完整")
    labels = selected.get("confusion_matrix_labels")
    matrix = selected.get("confusion_matrix")
    actual_counts = selected.get("actual_class_counts")
    if (not isinstance(labels, list) or not all(isinstance(label, str) for label in labels)
            or not isinstance(matrix, list) or len(matrix) != len(labels)
            or any(not isinstance(row, list) or len(row) != len(labels) for row in matrix)
            or not isinstance(actual_counts, dict)):
        raise AppError(503, "BACKEND_UNAVAILABLE", "M2 混淆矩阵或真实标签计数格式无效")
    confusion_matrix = [[_count(value) for value in row] for row in matrix]
    label_counts = {label: _count(actual_counts.get(label)) for label in labels}
    if sum(label_counts.values()) != 150 or sum(sum(row) for row in confusion_matrix) != 150:
        raise AppError(503, "BACKEND_UNAVAILABLE", "M2 标签或混淆矩阵总数与留出集不一致")
    trend_samples = _performance("近期趋势基线", "recent_trend_baseline", recent)
    dummy_samples = _performance("多数类基线", "dummy_most_frequent", dummy)

    return {
        "dataset_id": "course-research-300-v1",
        "dataset_version": DATASET_VERSION,
        "data_as_of": str(m2.get("test_origin") or ""),
        "m1": {
            "status": "candidate",
            "selected_k": selected_k,
            "training_repositories": _count(m1.get("eligible_training_repositories")),
            "test_repositories": _count(m1.get("eligible_test_repositories")),
            "train_silhouette": _number(selected_comparison.get("train_silhouette")),
            "test_silhouette": _number(m1.get("test_silhouette")),
            "size_only_test_silhouette": _number(m1.get("size_only_test_silhouette")),
            "mean_seed_pairwise_ari": _number(selected_comparison.get("mean_seed_pairwise_ari")),
            "cluster_counts": cluster_counts,
            "limitations": list(m1.get("limitations", [])),
        },
        "m2": {
            "status": "candidate",
            "selected_model_id": selected_id,
            "test_origin": str(m2.get("test_origin") or ""),
            "training_repositories": _count(m2.get("training_repositories")),
            "test_repositories": _count(m2.get("test_repositories")),
            "sample_count": 150,
            "actual_class_counts": label_counts,
            "confusion_matrix_labels": labels,
            "confusion_matrix": confusion_matrix,
            "selected_candidate": _performance("课程留出候选", selected_id, selected),
            "baselines": [trend_samples, dummy_samples],
            "limitations": list(m2.get("limitations", [])),
        },
        "m3": {
            "status": "preserved_mad_rule",
            "method": "statistical_rule",
            "rule": str(m3.get("rule") or ""),
            "timeline_available": False,
            "timeline_reason": "固定评估资料仅记录规则定义，没有逐周 Commit 与 robust Z 序列。",
            "limitations": [
                "M3 是 Median / MAD 统计规则，不是经过训练的异常分类器。",
                "当前固定评估资料不提供可绘制的历史逐周序列；不补造时间点或异常值。",
            ],
        },
    }
