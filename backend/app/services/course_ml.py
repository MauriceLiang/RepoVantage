"""Small dependency-free inference for the course-design model artifacts."""
import json
import math
from functools import lru_cache
from pathlib import Path
from datetime import timedelta

from backend.app.analytics.course_ml_features import (
    FEATURE_SCHEMA_VERSION, PATTERN_FEATURES, TREND_FEATURES, InsufficientCourseData,
    anomaly_context, build_weekly_features, recent_trend_baseline,
)
from backend.app.core.clock import iso_z, parse_github_datetime

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / "ml/course/artifacts"
PATTERN_ARTIFACT = "ml03-maintenance-pattern-12w-150train-v1.json"
TREND_ARTIFACT = "ml01-activity-trend-12w-150train-v1.json"


@lru_cache(maxsize=2)
def _artifact(name):
    path = ARTIFACTS / name
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (not isinstance(value, dict) or value.get("status") != "available"
            or value.get("feature_schema_version") != FEATURE_SCHEMA_VERSION):
        return None
    return value


def _number_list(value, length):
    return (isinstance(value, list) and len(value) == length
            and all(type(item) in (float, int) and math.isfinite(item) for item in value))


def _pattern_prediction(values):
    model = _artifact(PATTERN_ARTIFACT)
    size = len(PATTERN_FEATURES)
    if (model is None or model.get("feature_names") != list(PATTERN_FEATURES)
            or not _number_list(model.get("scaler_mean"), size)
            or not _number_list(model.get("scaler_scale"), size)
            or not isinstance(model.get("centers_scaled"), list)):
        return None
    means, scales = model["scaler_mean"], model["scaler_scale"]
    centers = model["centers_scaled"]
    if (not centers or any(not _number_list(center, size) for center in centers)
            or any(value <= 0 for value in scales)):
        return None
    point = [(values[name] - means[index]) / scales[index] for index, name in enumerate(PATTERN_FEATURES)]
    distances = [sum((point[index] - center[index]) ** 2 for index in range(size)) for center in centers]
    cluster_id = min(range(len(distances)), key=distances.__getitem__)
    profile = model.get("cluster_profiles", {}).get(str(cluster_id), {})
    if not isinstance(profile.get("name"), str):
        return None
    return {"pattern_id": str(cluster_id), "pattern_name": profile["name"], "model_id": model["model_id"],
            "model_version": model["version"]}


def _trend_prediction(values):
    model = _artifact(TREND_ARTIFACT)
    size = len(TREND_FEATURES)
    if (model is None or model.get("feature_names") != list(TREND_FEATURES)
            or not _number_list(model.get("scaler_mean"), size)
            or not _number_list(model.get("scaler_scale"), size)
            or not isinstance(model.get("classes"), list)
            or not isinstance(model.get("coefficients"), list)
            or not isinstance(model.get("intercepts"), list)):
        return None
    means, scales = model["scaler_mean"], model["scaler_scale"]
    coeffs, intercepts, classes = model["coefficients"], model["intercepts"], model["classes"]
    if (not classes or len(coeffs) != len(intercepts) or len(scales) != size
            or any(value <= 0 for value in scales)
            or any(not _number_list(row, size) for row in coeffs)
            or not all(isinstance(value, str) for value in classes)):
        return None
    point = [(values[name] - means[index]) / scales[index] for index, name in enumerate(TREND_FEATURES)]
    if len(classes) == 2 and len(coeffs) == 1:
        score = sum(coeffs[0][index] * point[index] for index in range(size)) + intercepts[0]
        class_index = 1 if score >= 0 else 0
    elif len(coeffs) == len(classes):
        scores = [sum(coeff[index] * point[index] for index in range(size)) + intercept
                  for coeff, intercept in zip(coeffs, intercepts)]
        class_index = max(range(len(scores)), key=scores.__getitem__)
    else:
        return None
    return {"trend": classes[class_index], "model_id": model["model_id"], "model_version": model["version"]}


def analyze_course_models(weeks):
    """Return independent per-task statuses; incomplete inputs never become zero values."""
    try:
        features = build_weekly_features(weeks)
    except InsufficientCourseData as exc:
        return {"facts": None, "maintenance_pattern": {"status": "insufficient_data", "method": "none", "reason_code": exc.reason},
                "activity_trend": {"status": "insufficient_data", "method": "none", "reason_code": exc.reason},
                "activity_anomaly": {"status": "insufficient_data", "method": "none", "reason_code": exc.reason}}
    facts, counts = features["facts"], [row["commits"] for row in weeks]
    pattern = {"status": "available", "method": "statistical_baseline", "reason_code": None,
               "model_id": None, "model_version": None, "feature_schema_version": FEATURE_SCHEMA_VERSION,
               "pattern_id": None, "pattern_name": None, "evidence": facts,
               "limitations": ["事实统计不等于仓库质量、健康度或技术采用价值。"]}
    if len(weeks) >= 12:
        prediction = _pattern_prediction(features["pattern_features"])
        if prediction:
            pattern.update(method="machine_learning", model_id=prediction["model_id"],
                           model_version=prediction["model_version"], pattern_id=prediction["pattern_id"],
                           pattern_name=prediction["pattern_name"])
        else:
            pattern["reason_code"] = "model_unavailable"
    else:
        pattern["reason_code"] = "short_observation_window"
    pattern["limitations"].append("模型只使用最近 12 个完整 UTC 周；24 周扩展仅提供额外背景，不改变模型窗口。")

    trend = {"status": "insufficient_data", "method": "none", "trend": None, "model_id": None,
             "model_version": None, "horizon_weeks": 4, "probabilities": None, "evidence": {}, "reason_code": None,
             "notes": []}
    if len(weeks) < 12:
        trend["reason_code"] = "short_observation_window"
        trend["notes"].append("不足 12 个完整 UTC 周，只展示已有事实。")
    elif sum(counts[-4:]) < 3 or sum(value > 0 for value in counts[-12:]) < 3:
        trend["reason_code"] = "low_activity_scope"
        trend["notes"].append("最近四周活动或 12 周活跃周过少，只展示历史事实，不作趋势预测。")
    else:
        prediction = _trend_prediction(features["trend_features"])
        if prediction:
            trend.update(status="available", method="machine_learning", trend=prediction["trend"],
                         model_id=prediction["model_id"], model_version=prediction["model_version"])
            trend["notes"].append("这是未来四周的机器学习类别预测，可能存在误差；不表示最近活动已经下降或上升。")
            trend["notes"].append("类别预测不提供未经校准的概率，也不预测精确 Commit 数量。")
            trend["notes"].append("依据既有仓库的历史留仓回测；迁移到不同仓库或活动分布时仍需谨慎解释。")
        else:
            trend.update(status="baseline_only", method="statistical_baseline", trend=recent_trend_baseline(counts[-12:]),
                         reason_code="model_unavailable")
            trend["notes"].append("模型文件不可用，仅展示近四周相对前四周的历史变化类别，不代表未来预测。")
        trend["evidence"] = {"recent_4w_commits": sum(counts[-4:]),
                              "previous_4w_commits": sum(counts[-8:-4]),
                              "active_weeks_12w": sum(value > 0 for value in counts[-12:])}
        as_of = parse_github_datetime(weeks[-1]["week_end_exclusive_utc"])
        if as_of is not None:
            trend["evidence"].update({
                "forecast_start_utc": iso_z(as_of),
                "forecast_end_exclusive_utc": iso_z(as_of + timedelta(weeks=4)),
            })
    trend["feature_schema_version"] = FEATURE_SCHEMA_VERSION

    anomaly = {"status": "insufficient_data", "method": "none", "suspected": False, "weeks": [],
               "model_id": None, "model_version": None, "reason_code": None,
               "notes": ["异常提示是待核查信号，不等同于维护失败或项目放弃。"]}
    if len(weeks) < 12:
        anomaly["reason_code"] = "short_observation_window"
    else:
        detection = anomaly_context(counts[-12:-1], counts[-1])
        anomaly.update(status="baseline_only", method="statistical_baseline", suspected=bool(detection["signals"]),
                       reason_code=None, weeks=[{"week_start_utc": weeks[-1]["week_start_utc"],
                                                 "commit_count": counts[-1], "commit_robust_z": detection["commit_robust_z"],
                                                 "direction": detection["signals"][0]["direction"] if detection["signals"] else None}])
    anomaly["feature_schema_version"] = FEATURE_SCHEMA_VERSION
    return {"facts": facts, "features": features, "maintenance_pattern": pattern,
            "activity_trend": trend, "activity_anomaly": anomaly}
