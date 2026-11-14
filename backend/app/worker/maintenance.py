"""在既有 Worker 租约下采集默认 12 周、可扩展至 24 周的维护活动。"""
import logging
import json
from datetime import timedelta

from sqlalchemy import desc, select

from backend.app.core.clock import iso_z, parse_github_datetime, utc_now
from backend.app.core.config import get_settings
from backend.app.core.exceptions import AppError
from backend.app.persistence.db import begin_immediate
from backend.app.persistence.models import CollectionTask, Repository, RepositoryActivityEvent, RepositoryInsightRun
from backend.app.pipeline.raw_archive import archive_json
from backend.app.services.insights import METRIC_VERSION
from backend.app.services.maintenance import persist_maintenance
from backend.app.services.maintenance_collection import COURSE_MAINTENANCE_COMMIT_PAGE_BUDGET, collect_maintenance
from backend.app.worker.executor import _defer_rate_limited, _finish_failed, _owns_attempt

logger = logging.getLogger(__name__)


def _cached_commit_counts(session, repository_id, start, end):
    run = session.scalar(select(RepositoryInsightRun).where(
        RepositoryInsightRun.repository_id == repository_id,
        RepositoryInsightRun.metric_version == METRIC_VERSION,
    ).order_by(desc(RepositoryInsightRun.analyzed_at), desc(RepositoryInsightRun.run_id)).limit(1))
    now = utc_now()
    if (run is None or run.analyzed_at > now
            or now - run.analyzed_at > timedelta(hours=get_settings().base_refresh_hours)
            or run.window_start > start or run.window_end < end):
        return None
    try:
        sources = json.loads(run.module_coverage_json)
        source = sources.get('commits') if isinstance(sources, dict) else None
    except (TypeError, ValueError):
        return None
    if (not isinstance(source, dict) or source.get('coverage') not in {'complete', 'true_zero'}
            or source.get('limit_reached') or source.get('rejected_records', 0)
            or source.get('invalid_event_times', 0)):
        return None
    requested = source.get('requested_interval')
    if requested is not None:
        if not isinstance(requested, list) or len(requested) != 2:
            return None
        lower, upper = (parse_github_datetime(value) if isinstance(value, str) else None for value in requested)
        if lower is None or upper is None or lower > start or upper < end:
            return None
    events = session.scalars(select(RepositoryActivityEvent).where(
        RepositoryActivityEvent.repository_id == repository_id,
        RepositoryActivityEvent.event_type == 'commit',
        RepositoryActivityEvent.event_at >= start,
        RepositoryActivityEvent.event_at < end,
    )).all()
    if any(event.last_seen_at > run.analyzed_at for event in events) or (source.get('coverage') == 'true_zero' and events):
        return None
    counts = {start + timedelta(weeks=index): 0 for index in range((end - start).days // 7)}
    for event in events:
        week = event.event_at.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=event.event_at.weekday())
        if week in counts:
            counts[week] += 1
    return counts, run.run_id, iso_z(run.analyzed_at)


def execute_maintenance_task(session_factory, task_id, github):
    session = session_factory()
    attempt = owner = None
    try:
        task = session.get(CollectionTask, task_id)
        if not task or task.scope_kind != 'maintenance' or task.status != 'running':
            return
        attempt, owner, repository_id = task.attempt, task.lease_owner, task.repository_id
        if session.get(Repository, repository_id) is None:
            _finish_failed(session, task_id, 'RESOURCE_NOT_FOUND', '本地仓库不存在', attempt, owner)
            return
        try:
            try:
                task_scope = json.loads(task.scope_json or "{}")
            except (TypeError, ValueError):
                task_scope = {}
            lookback_weeks = task_scope.get('lookback_weeks', 12)
            end = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
            end -= timedelta(days=end.weekday())
            start = end - timedelta(weeks=lookback_weeks)
            cached = _cached_commit_counts(session, repository_id, start, end)
            result = collect_maintenance(github, repository_id, lookback_weeks=lookback_weeks,
                                         max_pages=COURSE_MAINTENANCE_COMMIT_PAGE_BUDGET,
                                         cached_commit_counts=cached[0] if cached else None,
                                         cached_commit_source_run_id=cached[1] if cached else None,
                                         cached_commit_analyzed_at=cached[2] if cached else None)
        except AppError as exc:
            if exc.code == 'GITHUB_RATE_LIMITED':
                delay = exc.details.get('retry_after_seconds')
                _defer_rate_limited(session, task_id, attempt, owner, utc_now() + timedelta(seconds=delay if isinstance(delay, int) and delay > 0 else 60))
            else:
                _finish_failed(session, task_id, exc.code, exc.message, attempt, owner)
            return
        if any(value.get('error_code') == 'GITHUB_RATE_LIMITED' for value in result.get('source_audits', {}).values()):
            _defer_rate_limited(session, task_id, attempt, owner, utc_now() + timedelta(seconds=60))
            return
        try:
            archive = archive_json(repository_id, task_id, f'maintenance-{attempt}', result)
        except (OSError, ValueError) as exc:
            logger.exception('Maintenance archive failed task_id=%s', task_id)
            _finish_failed(session, task_id, 'MAINTENANCE_ARCHIVE_FAILED', '维护活动来源归档失败', attempt, owner)
            return
        session.rollback()
        begin_immediate(session)
        task = session.get(CollectionTask, task_id)
        now = utc_now()
        if not _owns_attempt(task, attempt, owner, now):
            session.rollback()
            return
        persist_maintenance(session, task_id, result, archive)
        task.status = 'partial' if result['status'] == 'partial' else 'succeeded'
        task.message = {'complete': f'最近 {lookback_weeks} 周维护活动采集完成', 'partial': f'最近 {lookback_weeks} 周 Commit 覆盖不完整',
                        'insufficient_history': '仓库没有可观察的完整 UTC 周'}[result['status']]
        task.phase = None
        task.current_module = None
        task.finished_at = now
        task.heartbeat_at = now
        task.lease_until = None
        task.lease_owner = None
        session.commit()
    except Exception:
        session.rollback()
        logger.exception('Maintenance task failed task_id=%s', task_id)
        if attempt is not None:
            _finish_failed(session, task_id, 'MAINTENANCE_COLLECTION_FAILED', '维护活动采集失败', attempt, owner)
    finally:
        session.close()
