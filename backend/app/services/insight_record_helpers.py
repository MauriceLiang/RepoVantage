"""Shared read-only helpers and the stable insights metric version."""

import json
from datetime import timedelta
from sqlalchemy import desc, select
from backend.app.core.exceptions import AppError
from backend.app.persistence.models import RepositoryInsightRun

METRIC_VERSION = "insights-v1"

def _select_insight_run(runs, window_days):
    return next((
        run for run in runs
        if window_days is None or run.window_start <= run.window_end - timedelta(days=window_days)
    ), None)



def _latest_insight_run(session, repository_id):
    """查找仓库最近一次指定指标版本的分析运行。"""
    return session.scalar(select(RepositoryInsightRun).where(
        RepositoryInsightRun.repository_id == repository_id,
        RepositoryInsightRun.metric_version == METRIC_VERSION,
    ).order_by(desc(RepositoryInsightRun.analyzed_at), desc(RepositoryInsightRun.run_id)).limit(1))


def _archive_sources(run, module, error_code, label):
    """读取逐条记录所需的任务、归档和模块覆盖信息。"""
    try:
        task_ids = json.loads(run.source_task_ids_json)
        archive_paths = json.loads(run.source_archive_paths_json)
        coverage = json.loads(run.module_coverage_json).get(module, {}).get("coverage", "not_collected")
    except (TypeError, ValueError, AttributeError) as exc:
        raise AppError(503, error_code, f"{label} 采集记录无法读取，请重新采集仓库数据") from exc
    return (
        task_ids if isinstance(task_ids, list) else [],
        archive_paths if isinstance(archive_paths, list) else [],
        coverage,
    )



def _online_comments(comment_count, fetch_comments, kind):
    """评论是可选内容；获取失败时保留详情正文并返回错误原因。"""
    comments = []
    if not comment_count:
        return comments, True, None
    try:
        result = fetch_comments()
        if result.error_code:
            raise AppError(result.error_status_code or 502, result.error_code, result.error_message or f"读取 {kind} 评论失败", result.error_details)
        for row in result.items:
            user = row.get("user") if isinstance(row.get("user"), dict) else {}
            comments.append({
                "author": user.get("login") if isinstance(user.get("login"), str) else "已删除用户",
                "body": row.get("body") if isinstance(row.get("body"), str) else "",
                "created_at": row.get("created_at") if isinstance(row.get("created_at"), str) else None,
            })
        return comments, not result.has_next, None
    except AppError as exc:
        return comments, False, exc.message


