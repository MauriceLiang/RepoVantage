"""insights-v1：基于 UTC 的确定性事件统计，不依赖 HTTP、数据库或界面。"""
from collections import Counter
from datetime import datetime, timedelta
from statistics import median

import numpy as np

from backend.app.core.clock import iso_z

LIMITATIONS = [
    "UTC，左闭右开窗口；达到用户设定的页数上限表示预算耗尽，不代表查询范围内的全部记录或 GitHub 全历史。",
    "Commit 来自默认分支，包含合并提交；Issue 使用对象最近可观测关闭时间，不回溯 reopen 生命周期。",
    "PR 仅采集 closed 状态；合并耗时不是首次响应时间，不能计算所有创建 PR 的合并率。",
    "Release 仅统计已发布正式版本；预发布单独计数，纯 tag 不计入。",
    "GitHub 对象在分页期间可能更新；统计是采集时观察结果，不是事务一致的全站快照。",
]


def week_start(value):
    return value.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=value.weekday())


def quality(source, n, *, insufficient=False):
    coverage = source.get("coverage", "not_collected")
    if coverage == "not_collected":
        status = "missing"
    elif coverage != "complete":
        status = "partial"
    elif insufficient:
        status = "insufficient_samples"
    else:
        status = "ready"
    if source.get("error_code") and not source.get("observed_records"):
        status = "failed"
    reason = source.get("error_code")
    if reason is None:
        if coverage == "budget_exhausted":
            reason = "达到用户设置的页数预算，仍有后续页未采集"
        elif status == "partial":
            reason = "采集覆盖不完整，仅为已观察样本"
        elif insufficient:
            reason = "样本不足"
    return {
        "status": status, "coverage": coverage, "valid_samples": n, "reason": reason,
        "limit_reached": bool(source.get("limit_reached")),
        "rejected_records": source.get("rejected_records", 0),
        "invalid_event_times": source.get("invalid_event_times", 0),
    }


def weekly(events, start, end, source):
    """在左闭右开的分析窗口内，按 UTC 周一开始的自然周聚合。

    先按自然周统计一次窗口内的事件，再依次生成每周结果。
    边界周或数据源不完整时保留已观察数量，但正式统计值为 None；
    只有完整周中的零才能解释为该周没有观察到事件。
    """
    current = week_start(start)
    if current >= end:
        return []

    counts = Counter()
    for event in events:
        event_at = event["event_at"]
        if event_at is not None and start <= event_at < end:
            counts[week_start(event_at)] += 1

    points = []
    while current < end:
        stop = current + timedelta(days=7)
        full = current >= start and stop <= end
        ready = full and source.get("coverage") == "complete"
        count = counts[current]
        points.append({
            "start": iso_z(current), "end": iso_z(stop),
            "value": count if ready else None, "observed_events": count,
            "quality": "ready" if ready else "partial", "complete_week": full,
        })
        current = stop
    return points


def duration_metric(events, start, end, source, field, key):
    """统计在窗口内结束的事件从创建到结束的有效耗时。

    缺失或倒序的时间戳会排除并单独计数。P75 至少需要 5 个有效样本，
    P90 至少需要 10 个；中位数和直方图使用全部有效样本，不填补缺失耗时。
    """
    terminal = [e for e in events if e[field] is not None and start <= e[field] < end]
    values = []
    invalid = 0
    for event in terminal:
        created = event["created_at"]
        if created is None or event[field] < created:
            invalid += 1
        else:
            values.append((event[field] - created).total_seconds() / 3600)
    n = len(values)
    edges = [0, 24, 72, 168, 720]
    labels = ["<1 天", "1–3 天", "3–7 天", "7–30 天", "≥30 天"]
    histogram = [
        {"label": label, "count": sum(low <= value < high for value in values)}
        for low, high, label in zip(edges, edges[1:] + [float("inf")], labels)
    ]
    return {
        "metric_key": key, "unit": "hours", "window_start": iso_z(start), "window_end": iso_z(end),
        "quality": quality(source, n, insufficient=n == 0),
        "observed_terminal_count": len(terminal), "excluded_invalid_duration": invalid,
        "missing_duration_rate": invalid / len(terminal) if terminal else None,
        "observed_without_terminal": sum(event[field] is None for event in events),
        "median_hours": median(values) if values else None,
        "p75_hours": float(np.quantile(values, .75, method="linear")) if n >= 5 else None,
        "p90_hours": float(np.quantile(values, .9, method="linear")) if n >= 10 else None,
        "histogram": histogram, "weekly": weekly(terminal, start, end, source),
    }


def calculate_insights(events, sources, start, end):
    """根据标准化事件和各模块覆盖状态计算 insights-v1 指标。

    Commit 变化比较连续两组各 4 个完整 UTC 自然周。
    发布节奏固定使用截至 ``end`` 的前 365 天，不受较短的活动窗口影响。
    """
    commits = events["commits"]
    points = weekly(commits, start, end, sources["commits"])
    completed_end = week_start(end)
    eight = [p for p in points if completed_end - timedelta(weeks=8) <= datetime.fromisoformat(p["start"].replace("Z", "")) < completed_end]
    comparable = len(eight) == 8 and all(p["quality"] == "ready" for p in eight)
    previous = sum(p["value"] for p in eight[:4]) if comparable else None
    recent = sum(p["value"] for p in eight[4:]) if comparable else None
    valid_commits = sum(1 for event in commits if event["event_at"] and start <= event["event_at"] < end)
    if not comparable:
        comparison_reason = "不足八个完整覆盖的已结束自然周，无法判断前后四周变化"
    elif previous == 0:
        comparison_reason = "基期为零，不计算百分比"
    else:
        comparison_reason = None
    activity = {
        "metric_key": "commits_weekly", "unit": "commits", "window_start": iso_z(start), "window_end": iso_z(end),
        "quality": quality(sources["commits"], valid_commits), "weekly": points,
        "recent_4w": recent, "previous_4w": previous,
        "delta": recent - previous if comparable else None,
        "change_rate_pct": (recent - previous) / previous * 100 if comparable and previous else None,
        "comparison_reason": comparison_reason,
    }
    release_start = end - timedelta(days=365)
    releases = [e for e in events["releases"] if e["published_at"] and release_start <= e["published_at"] < end and not e["is_draft"]]
    formal = sorted([e for e in releases if not e["is_prerelease"]], key=lambda e: e["published_at"])
    gaps = [(b["published_at"] - a["published_at"]).total_seconds() / 86400 for a, b in zip(formal, formal[1:])]
    return {
        "commit_activity": activity,
        "issue_resolution": duration_metric(events["issues"], start, end, sources["issues"], "closed_at", "issue_closed_duration_hours"),
        "pr_merges": duration_metric(events["pulls"], start, end, sources["pulls"], "merged_at", "pr_merge_duration_hours"),
        "release_cadence": {
            "metric_key": "release_intervals_days", "unit": "days",
            "window_start": iso_z(release_start), "window_end": iso_z(end),
            "quality": quality(sources["releases"], len(formal), insufficient=len(formal) < 2),
            "release_count": len(formal), "prerelease_count": len(releases) - len(formal),
            "timeline": [{"id": event["source_item_id"], "published_at": iso_z(event["published_at"])} for event in formal],
            "intervals_days": gaps, "median_interval_days": median(gaps) if gaps else None,
        },
    }
