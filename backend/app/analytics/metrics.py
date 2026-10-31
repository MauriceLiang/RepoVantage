from datetime import datetime
import math
from statistics import median, stdev

from scipy.stats import spearmanr


def basic_metrics(stars: int | None, forks: int | None, collected_at: datetime, created_at: datetime | None, pushed_at: datetime | None) -> dict:
    age = (collected_at - created_at).total_seconds() / 86400 if created_at else None
    since_push = (collected_at - pushed_at).total_seconds() / 86400 if pushed_at else None
    if age is not None and age < 0:
        age = None
    if since_push is not None and since_push < 0:
        since_push = None
    return {
        "stars": stars,
        "forks": forks,
        "age_days": round(age, 1) if age is not None else None,
        "days_since_push": round(since_push, 1) if since_push is not None else None,
        "release_count_365d": None,
        "commits_90d": None,
        "issues_closed_90d": None,
        "pr_merged_90d": None,
    }


def _number(value) -> float | None:
    """等价于 pd.to_numeric(errors="coerce") + dropna：可转换的返回 float，NaN 与不可解析的返回 None。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def numeric_summary(values: list[float]) -> dict:
    series = [number for value in values if (number := _number(value)) is not None]
    if not series:
        return {"count": 0, "mean": None, "median": None, "std": None}
    return {
        "count": len(series),
        "mean": round(sum(series) / len(series), 3),
        "median": round(median(series), 3),
        "std": round(stdev(series), 3) if len(series) > 1 else None,
    }


def spearman_summary(x_values: list[float], y_values: list[float]) -> dict:
    pairs = []
    for x, y in zip(x_values, y_values):
        left, right = _number(x), _number(y)
        if left is not None and right is not None:
            pairs.append((left, right))
    n = len(pairs)
    result = {"method": "spearman", "n": n, "coefficient": None, "p_value": None, "note": None}
    if n < 10:
        result["note"] = "有效配对样本少于 10，未计算研究性相关"
        return result
    x_series = [pair[0] for pair in pairs]
    y_series = [pair[1] for pair in pairs]
    if len(set(x_series)) < 2 or len(set(y_series)) < 2:
        result["note"] = "输入为常量，Spearman 系数与 p 值未定义"
        return result
    coefficient, p_value = spearmanr(x_series, y_series)
    if math.isfinite(coefficient) and math.isfinite(p_value):
        result["coefficient"] = round(float(coefficient), 6)
        result["p_value"] = round(float(p_value), 8)
    else:
        result["note"] = "输入数据无法形成有效相关估计"
    return result
