"""Shared 12-week feature contract for course ML training and live inference."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import timedelta

from backend.app.core.clock import iso_z, parse_github_datetime

FEATURE_SCHEMA_VERSION = "course-maintenance-12w-v1"
MODEL_WINDOW_WEEKS = 12
EXTENDED_WINDOW_WEEKS = 24
TREND_HORIZON_WEEKS = 4
PATTERN_FEATURES = (
    "commit_active_fraction",
    "commit_log_cv",
    "commit_longest_zero_fraction",
    "commit_recent_change_log1p",
    "commit_top2_share",
)
TREND_FEATURES = (
    "commit_log_mean_4w",
    "commit_log_mean_previous_8w",
    "commit_active_fraction",
    "commit_log_cv",
    "commit_recent_change_log1p",
)
TREND_LABELS = ("下降", "基本稳定", "上升")


class InsufficientCourseData(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _time(value):
    if not isinstance(value, str) or not (value.endswith("Z") or value.endswith("+00:00")):
        raise InsufficientCourseData("invalid_week_boundary")
    parsed = parse_github_datetime(value)
    if parsed is None:
        raise InsufficientCourseData("invalid_week_boundary")
    return parsed


def _longest_zero(values):
    longest = current = 0
    for value in values:
        current = current + 1 if value == 0 else 0
        longest = max(longest, current)
    return longest


def _log_cv(values):
    logs = [math.log1p(value) for value in values]
    mean = sum(logs) / len(logs)
    variance = sum((value - mean) ** 2 for value in logs) / len(logs)
    return math.sqrt(variance)


def _series(weeks, field, coverage_field, *, required):
    values = []
    complete = True
    for row in weeks:
        coverage, count = row.get(coverage_field), row.get(field)
        if coverage not in {"complete", "true_zero"}:
            complete = False
            if required:
                raise InsufficientCourseData(f"incomplete_{field}_coverage")
            values.append(None)
            continue
        if type(count) is not int or count < 0 or (coverage == "true_zero" and count != 0):
            raise InsufficientCourseData(f"invalid_{field}_count")
        values.append(count)
    return values if complete else None


def validate_week_rows(weeks, *, max_weeks=EXTENDED_WINDOW_WEEKS):
    """Validate ordered, complete UTC week boundaries without treating gaps as zero."""
    if not isinstance(weeks, list) or not 1 <= len(weeks) <= max_weeks:
        raise InsufficientCourseData("invalid_observation_length")
    previous = None
    for row in weeks:
        if not isinstance(row, dict):
            raise InsufficientCourseData("invalid_week")
        start = _time(row.get("week_start_utc"))
        end = _time(row.get("week_end_exclusive_utc"))
        if (start.weekday() != 0 or start.hour or start.minute or start.second or start.microsecond
                or end - start != timedelta(days=7) or (previous is not None and start != previous)):
            raise InsufficientCourseData("noncontiguous_weeks")
        previous = end
    commits = _series(weeks, "commits", "commit_coverage", required=True)
    prs = _series(weeks, "prs_created", "pr_created_coverage", required=False)
    return commits, prs


def _recent_features(commits):
    count = len(commits)
    if count < MODEL_WINDOW_WEEKS:
        return None
    recent = commits[-MODEL_WINDOW_WEEKS:]
    previous_mean = sum(recent[:8]) / 8
    recent_mean = sum(recent[8:]) / 4
    total = sum(recent)
    features = {
        "commit_active_fraction": sum(value > 0 for value in recent) / MODEL_WINDOW_WEEKS,
        "commit_log_cv": _log_cv(recent),
        "commit_longest_zero_fraction": _longest_zero(recent) / MODEL_WINDOW_WEEKS,
        "commit_recent_change_log1p": math.log1p(recent_mean) - math.log1p(previous_mean),
        "commit_top2_share": sum(sorted(recent, reverse=True)[:2]) / total if total else 0.0,
    }
    return features


def build_weekly_features(weeks):
    """Build factual 1-24 week summaries and model features from one shared contract."""
    commits, prs = validate_week_rows(weeks)
    commit_features = _recent_features(commits)
    pr_features = _recent_features(prs) if prs is not None else None
    total = sum(commits)
    facts = {
        "commit_total": total,
        "commit_active_weeks": sum(value > 0 for value in commits),
        "commit_observed_weeks": len(commits),
        "commit_active_fraction": sum(value > 0 for value in commits) / len(commits),
        "commit_longest_zero_weeks": _longest_zero(commits),
        "pr_coverage": "complete" if prs is not None else "partial_or_unavailable",
        "pr_created_total": sum(prs) if prs is not None else None,
    }
    if prs is not None:
        facts.update({
            "pr_active_weeks": sum(value > 0 for value in prs),
            "pr_observed_weeks": len(prs),
        })
    canonical = json.dumps(weeks, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    end = _time(weeks[-1]["week_end_exclusive_utc"])
    return {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "window_weeks": len(weeks),
        "model_window_weeks": MODEL_WINDOW_WEEKS,
        "as_of_utc": iso_z(end),
        "source_sha256": hashlib.sha256(canonical).hexdigest(),
        "facts": facts,
        "pattern_features": commit_features,
        "trend_features": _trend_features(commits) if len(commits) >= MODEL_WINDOW_WEEKS else None,
        "optional_pr_features": pr_features,
    }


def _trend_features(commits):
    recent = commits[-MODEL_WINDOW_WEEKS:]
    summary = _recent_features(recent)
    return {
        "commit_log_mean_4w": math.log1p(sum(recent[-4:]) / 4),
        "commit_log_mean_previous_8w": math.log1p(sum(recent[:8]) / 8),
        "commit_active_fraction": summary["commit_active_fraction"],
        "commit_log_cv": summary["commit_log_cv"],
        "commit_recent_change_log1p": summary["commit_recent_change_log1p"],
    }


def trend_label(past4, future4, *, relative_threshold=0.25, absolute_threshold=3):
    """Label a four-week change; sparse 0->1 activity remains stable."""
    if (len(past4) != TREND_HORIZON_WEEKS or len(future4) != TREND_HORIZON_WEEKS
            or any(type(value) is not int or value < 0 for value in (*past4, *future4))):
        raise ValueError("trend labels require two non-negative four-week integer series")
    past, future = sum(past4), sum(future4)
    delta = future - past
    threshold = max(absolute_threshold, relative_threshold * past)
    if delta >= threshold:
        return "上升"
    if delta <= -threshold:
        return "下降"
    return "基本稳定"


def recent_commit_change(weeks):
    """Describe the last two complete four-week periods as historical facts."""
    empty = {
        "status": "insufficient_data", "method": "factual", "reason_code": "short_history",
        "previous_4w_commits": None, "recent_4w_commits": None, "change_count": None,
        "threshold": None, "trend": None,
        "previous_window_start_utc": None, "previous_window_end_exclusive_utc": None,
        "recent_window_start_utc": None, "recent_window_end_exclusive_utc": None,
        "notes": ["需要最近 8 个完整 UTC 周；数据不足时不推断历史变化。"],
    }
    if not isinstance(weeks, list) or len(weeks) < 8:
        return empty
    recent_eight = weeks[-8:]
    try:
        commits, _ = validate_week_rows(recent_eight, max_weeks=8)
    except InsufficientCourseData as exc:
        status = "partial_data" if exc.reason == "incomplete_commits_coverage" else "insufficient_data"
        return {**empty, "status": status, "reason_code": exc.reason,
                "notes": ["最近 8 周 Commit 覆盖不完整；只保留已核验事实，不把缺失周补为零。"]}

    previous, recent = sum(commits[:4]), sum(commits[4:])
    threshold = max(3, 0.25 * previous)
    trend = trend_label(commits[:4], commits[4:])
    notes = ["实际变化使用此前 4 周与最近 4 周的完整 Commit 聚合，不代表未来预测。"]
    if previous == 0 and recent == 0:
        notes.append("此前与最近 4 周均为零 Commit；表示持续无默认分支提交活动。")
    return {
        "status": "available", "method": "factual", "reason_code": None,
        "previous_4w_commits": previous, "recent_4w_commits": recent,
        "change_count": recent - previous, "threshold": threshold, "trend": f"近期{trend}",
        "previous_window_start_utc": recent_eight[0]["week_start_utc"],
        "previous_window_end_exclusive_utc": recent_eight[4]["week_start_utc"],
        "recent_window_start_utc": recent_eight[4]["week_start_utc"],
        "recent_window_end_exclusive_utc": recent_eight[-1]["week_end_exclusive_utc"],
        "notes": notes,
    }


def recent_trend_baseline(commits):
    """A deterministic continuation baseline using the last two observed four-week periods."""
    if len(commits) < 8:
        raise InsufficientCourseData("insufficient_trend_history")
    return trend_label(commits[-8:-4], commits[-4:])
