import json
import logging
import time
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from backend.app.core.clock import iso_z, parse_github_datetime, utc_now
from backend.app.core.exceptions import AppError
from backend.app.integrations.github.client import GitHubClient
from backend.app.persistence.db import begin_immediate
from backend.app.persistence.models import AnalysisResult, ActivityWindow, CollectionLog, CollectionTask, Repository, RepositorySnapshot, TaskModuleProgress
from backend.app.pipeline.cleaner import clean_repository_profile
from backend.app.pipeline.feature_builder import build_profile_metrics
from backend.app.pipeline.quality import overall_coverage
from backend.app.pipeline.raw_archive import archive_json
from backend.app.services.insights import PAGE_LIMIT_NOTE, persist_insights
from backend.app.services.repositories import latest_analysis, latest_snapshot, repository_from_github
from backend.app.worker.collection import collect_deep
from backend.app.worker.queue import MAX_ATTEMPTS, update_phase
from backend.app.worker.progress import TaskProgressReporter
from backend.app.worker.telemetry import log_module_timing, log_task_timing, request_metrics_delta


logger = logging.getLogger(__name__)


def _request_metrics(github: GitHubClient) -> dict[str, int | float]:
    snapshot = getattr(github, "request_metrics_snapshot", None)
    return snapshot() if snapshot else {}


def _log_task_timing(
    github: GitHubClient,
    task_id: str,
    repository_id: int | None,
    depth: str | None,
    status: str,
    started_at: float,
    initial_metrics: dict[str, int | float],
) -> None:
    final_metrics = _request_metrics(github)
    log_task_timing(
        task_id=task_id,
        repository_id=repository_id,
        depth=depth,
        status=status,
        duration_ms=(time.monotonic() - started_at) * 1000,
        metrics=request_metrics_delta(final_metrics, initial_metrics),
    )


def _log_profile_timing(
    github: GitHubClient,
    task_id: str,
    repository_id: int,
    started_at: float,
    initial_metrics: dict[str, int | float],
    status: str,
) -> None:
    final_metrics = _request_metrics(github)
    succeeded = status in {"complete", "reused"}
    metrics = request_metrics_delta(final_metrics, initial_metrics)
    log_module_timing(
        task_id=task_id,
        repository_id=repository_id,
        module="profile",
        http_calls=int(metrics["http_calls"]),
        pages_fetched=0 if status == "failed" else 1,
        observed_items=0 if status == "failed" else 1,
        duration_ms=(time.monotonic() - started_at) * 1000,
        coverage="complete" if succeeded else "partial",
        error_code=None if succeeded else status,
        rate_limited_count=int(metrics["rate_limited_count"]),
        timeout_count=int(metrics["timeout_count"]),
    )


def _owns_attempt(task: CollectionTask | None, attempt: int | None, lease_owner: str | None, now) -> bool:
    return bool(
        task
        and attempt is not None
        and task.status == "running"
        and task.attempt == attempt
        and task.lease_owner == lease_owner
        and task.lease_until is not None
        and task.lease_until > now
    )


def _complete_not_modified(session: Session, task_id: str, repository_id: int, attempt: int | None, lease_owner: str | None) -> bool:
    session.rollback()
    begin_immediate(session)
    task = session.get(CollectionTask, task_id)
    now = utc_now()
    if not _owns_attempt(task, attempt, lease_owner, now):
        session.rollback()
        return False
    repo = session.get(Repository, repository_id)
    if repo:
        repo.last_seen_at = now
    task.status = "succeeded"
    task.phase = None
    task.current_module = None
    task.message = "GitHub 确认仓库资料未变化，沿用最近一次有效观测"
    task.finished_at = now
    task.heartbeat_at = now
    task.lease_until = None
    session.add(CollectionLog(request_id=task.task_id, task_id=task.task_id, repository_id=repository_id, event_type="not_modified", source_endpoint=f"/repositories/{repository_id}", http_status=304, message_redacted="ETag 命中；未新增指标快照"))
    session.commit()
    return True


def _update_phase(
    session: Session,
    task: CollectionTask,
    reporter: TaskProgressReporter | None,
    phase: str,
    message: str,
    progress_percent: int | None,
) -> None:
    if reporter:
        reporter.set_phase(phase, message, progress_percent)
    else:
        update_phase(
            session,
            task.task_id,
            phase,
            message,
            attempt=task.attempt,
            lease_owner=task.lease_owner,
            progress_percent=progress_percent,
        )


def execute_task(session_factory, task_id: str, github: GitHubClient) -> None:
    session: Session = session_factory()
    expected_attempt: int | None = None
    expected_owner: str | None = None
    repository_id: int | None = None
    depth: str | None = None
    reporter: TaskProgressReporter | None = None
    task_started = time.monotonic()
    initial_metrics = _request_metrics(github)
    try:
        task = session.get(CollectionTask, task_id)
        if task is None or task.status != "running":
            return
        expected_attempt = task.attempt
        expected_owner = task.lease_owner
        repository_id = task.repository_id
        depth = task.depth
        if task.depth == "deep" and task.lease_owner:
            reporter = TaskProgressReporter(session_factory, task.task_id, task.attempt, task.lease_owner)
        repo = session.get(Repository, task.repository_id)
        if repo is None:
            if _finish_failed(session, task_id, "RESOURCE_NOT_FOUND", "本地仓库记录不存在", expected_attempt, expected_owner):
                _log_task_timing(github, task_id, repository_id, depth, "failed", task_started, initial_metrics)
            return
        profile_started = time.monotonic()
        if reporter:
            reporter.begin_module("profile", page_cap=1)
        previous = latest_snapshot(session, repo.repository_id)
        reusable_basic_analysis = None
        request_etag = None
        if task.depth == "basic" and previous and previous.response_etag:
            candidate = latest_analysis(session, repo.repository_id, "basic")
            try:
                candidate_metrics = json.loads(candidate.metrics_json) if candidate else None
            except (TypeError, ValueError):
                candidate_metrics = None
            if (
                candidate
                and candidate.source_collected_at == previous.collected_at
                and (candidate.valid_sample_size or 0) > 0
                and candidate.coverage in {"complete", "partial"}
                and isinstance(candidate_metrics, dict)
            ):
                reusable_basic_analysis = candidate
                request_etag = previous.response_etag
        try:
            profile_metrics_before = _request_metrics(github)
            payload, status, etag = github.get_repository_by_id(repo.repository_id, request_etag)
            if status == 304:
                if reusable_basic_analysis is None:
                    raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 返回 304，但没有可复用的当前 basic 分析结果", {"http_status": 304})
                _log_profile_timing(github, task_id, repo.repository_id, profile_started, profile_metrics_before, "reused")
                completed = _complete_not_modified(session, task_id, repo.repository_id, expected_attempt, expected_owner)
                if completed:
                    _log_task_timing(github, task_id, repo.repository_id, task.depth, "succeeded", task_started, initial_metrics)
                return
            if payload is None:
                raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 未返回仓库资料")
        except AppError as exc:
            _log_profile_timing(github, task_id, repo.repository_id, profile_started, profile_metrics_before, exc.code)
            if reporter:
                reporter.finish_module(
                    "profile",
                    status="skipped" if exc.code == "GITHUB_RATE_LIMITED" else "failed",
                    coverage="deferred" if exc.code == "GITHUB_RATE_LIMITED" else "partial",
                    elapsed_seconds=time.monotonic() - profile_started,
                    error_code=exc.code,
                )
            if exc.code == "GITHUB_RATE_LIMITED":
                retry_after = exc.details.get("retry_after_seconds")
                delay = retry_after if isinstance(retry_after, int) and retry_after > 0 else min(3600, 60 * (2 ** min(max(task.attempt - 1, 0), 5)))
                resume_after = utc_now() + timedelta(seconds=delay)
                final_status = _defer_rate_limited(session, task_id, expected_attempt, expected_owner, resume_after)
                if final_status:
                    _log_task_timing(github, task_id, repository_id, depth, final_status, task_started, initial_metrics)
                return
            if _finish_failed(session, task_id, exc.code, exc.message, expected_attempt, expected_owner, details=exc.details):
                _log_task_timing(github, task_id, repository_id, depth, "failed", task_started, initial_metrics)
            return
        _log_profile_timing(github, task_id, repo.repository_id, profile_started, profile_metrics_before, "complete")
        if reporter:
            reporter.page_fetched("profile", pages_fetched=1, observed_items=1)
            reporter.finish_module(
                "profile",
                status="complete",
                coverage="complete",
                elapsed_seconds=time.monotonic() - profile_started,
            )

        try:
            archive_path = archive_json(repo.repository_id, task.task_id, "repository", {"source_endpoint": f"/repositories/{repo.repository_id}", "collected_at": iso_z(utc_now()), "http_status": status, "etag": etag, "data": payload})
        except OSError:
            archive_path = None
            session.add(CollectionLog(request_id=task.task_id, task_id=task.task_id, repository_id=repo.repository_id, event_type="archive_failed", source_endpoint=f"/repositories/{repo.repository_id}", http_status=status, message_redacted="原始数据归档写入失败"))

        session.commit()
        _update_phase(session, task, reporter, "cleaning", "正在规范化 GitHub 仓库字段", 12 if reporter else None)
        try:
            cleaned = clean_repository_profile(payload, repo.repository_id)
        except AppError as exc:
            if _finish_failed(session, task_id, exc.code, exc.message, expected_attempt, expected_owner):
                _log_task_timing(github, task_id, repository_id, depth, "failed", task_started, initial_metrics)
            return

        collected_at = utc_now()
        profile_metrics = build_profile_metrics(cleaned, collected_at)
        metrics = dict(profile_metrics)
        depth_coverage = "complete"
        activity: dict[str, Any] | None = None
        insight_result = None
        window_end = collected_at.replace(microsecond=0)
        window_start = window_end - timedelta(days=90)
        deferred_until = None
        query_start = window_start
        if task.depth == "deep":
            window_end = task.created_at.replace(microsecond=0)
            window_start = window_end - timedelta(days=90)
            query_start = window_start
        if task.depth == "deep" and task.scope_json:
            try:
                task_scope = json.loads(task.scope_json)
                scoped_start = parse_github_datetime(task_scope.get("window_start")) if isinstance(task_scope, dict) else None
                scoped_end = parse_github_datetime(task_scope.get("window_end")) if isinstance(task_scope, dict) else None
                if scoped_start and scoped_end and scoped_start < scoped_end:
                    if task.scope_kind in {"incremental", "backfill"}:
                        query_start = scoped_start
                        analysis_start = parse_github_datetime(task_scope.get("analysis_window_start"))
                        analysis_end = parse_github_datetime(task_scope.get("analysis_window_end"))
                        if analysis_start and analysis_end and analysis_start < analysis_end:
                            window_start, window_end = analysis_start, analysis_end
                    else:
                        window_start, window_end = scoped_start, scoped_end
                        query_start = scoped_start
            except (TypeError, ValueError):
                logger.warning("Invalid saved collection scope task_id=%s; using task creation window", task.task_id)
                window_end = task.created_at.replace(microsecond=0)
                window_start = window_end - timedelta(days=90)
                query_start = window_start
        if task.depth == "deep":
            if reporter:
                collection_label = "历史回填" if task.scope_kind == "backfill" else "重叠增量窗口" if task.scope_kind == "incremental" else "完整时间窗" if task.scope_kind == "window" else "快速预算"
                reporter.set_phase("collecting", f"正在采集{collection_label}深度活动数据", 12)
            effective_page_cap = None if task.scope_kind in {"window", "incremental"} else getattr(github, "max_pages", None)
            logger.info(
                "Collecting repository activity task_id=%s repository_id=%s scope_kind=%s window_days=%s window_start=%s window_end=%s max_pages=%s",
                task.task_id,
                task.repository_id,
                task.scope_kind,
                max(1, int((window_end - window_start).total_seconds() // 86400)),
                iso_z(window_start),
                iso_z(window_end),
                effective_page_cap,
            )
            activity, depth_coverage, deferred_until = collect_deep(
                github, cleaned["full_name"], window_start, window_end, task, reporter, session_factory,
                query_start=query_start,
            )
            for metric, key in (("commits_90d", "commits_count"), ("issues_closed_90d", "issues_closed_count"), ("pr_merged_90d", "pulls_merged_count"), ("release_count_365d", "releases_count")):
                metrics[metric] = activity[key] if activity["coverage_by_module"][key] == "complete" else None

        _update_phase(session, task, reporter, "analyzing", "正在计算基础指标与数据覆盖", 94 if reporter else None)
        coverage = overall_coverage({"profile": "complete", "activity": depth_coverage})
        limitations = ["关注度指标不等于代码质量"]
        if task.depth == "deep" and depth_coverage == "partial":
            limitations.append("部分深度活动端点或分页未能完整采集")
        page_limit_reached = bool(activity and any(source.get("limit_reached") for source in activity["sources"].values()))
        if page_limit_reached:
            limitations.append(PAGE_LIMIT_NOTE)
        _update_phase(session, task, reporter, "persisting", "正在保存快照、分析结果与来源记录", 98 if reporter else None)

        session.rollback()
        begin_immediate(session)
        task = session.get(CollectionTask, task_id)
        now = utc_now()
        if not _owns_attempt(task, expected_attempt, expected_owner, now):
            session.rollback()
            return
        repo = repository_from_github(session, payload)
        snapshot = RepositorySnapshot(
            repository_id=repo.repository_id,
            collected_at=collected_at,
            stars=cleaned["stars"],
            forks=cleaned["forks"],
            open_issues_and_pr_count=cleaned["open_issues_and_pr_count"],
            pushed_at=cleaned["pushed_at"],
            github_updated_at=cleaned["github_updated_at"],
            response_etag=etag,
            source_http_status=status,
            source_archive_path=archive_path,
            valid=True,
        )
        session.add(snapshot)
        if activity is not None:
            try:
                activity_archive = archive_json(repo.repository_id, task.task_id, "activity", activity["raw"])
            except OSError:
                activity_archive = None
                session.add(CollectionLog(request_id=task.task_id, task_id=task.task_id, repository_id=repo.repository_id, event_type="archive_failed", source_endpoint="activity", http_status=status, message_redacted="深度活动数据归档写入失败"))
            insight_result = persist_insights(
                session, repo.repository_id, task.task_id, activity["events"], activity["sources"],
                window_start, window_end, [activity_archive] if activity_archive else [],
                normalized_event_counts=activity["event_counts"],
                aggregate_from_store=task.scope_kind in {"incremental", "backfill"},
            )
            observed_counts = insight_result["observed_counts"]
            for metric, key, module in (
                ("commits_90d", "commits_count", "commits"),
                ("issues_closed_90d", "issues_closed_count", "issues"),
                ("pr_merged_90d", "pulls_merged_count", "pulls"),
                ("release_count_365d", "releases_count", "releases"),
            ):
                metrics[metric] = observed_counts[key] if activity["coverage_by_module"][key] == "complete" else None
            session.add(ActivityWindow(
                repository_id=repo.repository_id,
                depth="deep",
                window_start=window_start,
                window_end=window_end,
                commits_count=observed_counts["commits_count"],
                issues_opened_count=observed_counts["issues_opened_count"],
                issues_closed_count=observed_counts["issues_closed_count"],
                pulls_opened_count=observed_counts["pulls_opened_count"],
                pulls_merged_count=observed_counts["pulls_merged_count"],
                releases_count=observed_counts["releases_count"],
                coverage=depth_coverage,
                collected_at=collected_at,
                details_json=json.dumps({
                    "coverage_by_module": activity["coverage_by_module"],
                    "scope_kind": task.scope_kind,
                    "collection_window_start": iso_z(query_start),
                    "collection_window_end": iso_z(window_end),
                }, ensure_ascii=False),
                source_archive_path=activity_archive,
            ))
        result = AnalysisResult(
            repository_id=repo.repository_id,
            analysis_kind=task.depth,
            metric_version="metrics-v1",
            window_start=window_start if task.depth == "deep" else None,
            window_end=window_end if task.depth == "deep" else None,
            source_collected_at=collected_at,
            calculated_at=utc_now(),
            coverage=coverage,
            metrics_json=json.dumps(metrics, ensure_ascii=False),
            limitations_json=json.dumps(limitations, ensure_ascii=False),
            valid_sample_size=1,
        )
        if task.depth == "deep":
            session.add(AnalysisResult(
                repository_id=repo.repository_id,
                analysis_kind="basic",
                metric_version="metrics-v1",
                source_collected_at=collected_at,
                calculated_at=utc_now(),
                coverage="complete",
                metrics_json=json.dumps(profile_metrics, ensure_ascii=False),
                limitations_json=json.dumps(["关注度指标不等于代码质量"], ensure_ascii=False),
                valid_sample_size=1,
            ))
        session.add(result)
        incomplete = coverage == "partial" or (insight_result is not None and insight_result["status"] == "partial")
        exhausted_retries = bool(activity and activity.get("defer_reason") == "rate_limit" and task.attempt >= MAX_ATTEMPTS)
        task.status = "failed" if exhausted_retries else "queued" if deferred_until is not None else "partial" if incomplete else "succeeded"
        task.phase = None
        task.current_module = None
        task.resume_after = deferred_until if task.status == "queued" else None
        if task.status == "queued":
            task.error_code = None
            task.error_message = None
            task.progress_kind = "unknown"
            task.progress_percent = None
            task.progress_updated_at = now
            task.message = "历史回填已保存检查点，稍后让出队列并继续" if activity and activity.get("defer_reason") == "page_budget" else "GitHub 配额暂时不足，已保存检查点并延迟恢复"
        elif exhausted_retries:
            task.error_code = "GITHUB_RATE_LIMITED"
            task.error_message = "GitHub 多次限流，已保留检查点；请稍后手动重试"
            task.message = task.error_message
            task.finished_at = now
        elif reporter:
            task.progress_kind = "stages"
            task.progress_percent = 100
            task.progress_updated_at = now
        else:
            task.progress_kind = "unknown"
            task.progress_percent = None
        if task.status not in {"queued", "failed"}:
            task.message = (
                "已达到用户设置的页数预算，后续页面未采集完整" if page_limit_reached
                else "基础数据与分析已完成" if not incomplete
                else "基础数据已保存，部分活动模块采集或事件校验不完整"
            )
            task.finished_at = now
        task.heartbeat_at = now
        task.lease_until = None
        session.add(CollectionLog(request_id=task.task_id, task_id=task.task_id, repository_id=repo.repository_id, event_type="collection_deferred" if task.status == "queued" else "collection_completed", source_endpoint=f"/repositories/{repo.repository_id}", http_status=status, message_redacted=f"depth={task.depth}; coverage={coverage}"))
        session.commit()
        _log_task_timing(github, task_id, repository_id, depth, "deferred" if task.status == "queued" else task.status, task_started, initial_metrics)
    except Exception as exc:
        session.rollback()
        if expected_attempt is not None:
            logger.exception("Task execution failed task_id=%s error_type=%s", task_id, type(exc).__name__)
            failed = _finish_failed(
                session,
                task_id,
                "WORKER_EXECUTION_FAILED",
                f"采集任务执行失败：{type(exc).__name__}",
                expected_attempt,
                expected_owner,
            )
            if failed:
                _log_task_timing(github, task_id, repository_id, depth, "failed", task_started, initial_metrics)
    finally:
        session.close()


def _defer_rate_limited(session: Session, task_id: str, attempt: int | None, lease_owner: str | None, resume_after) -> str | None:
    session.rollback()
    begin_immediate(session)
    task = session.get(CollectionTask, task_id)
    now = utc_now()
    if not _owns_attempt(task, attempt, lease_owner, now):
        session.rollback()
        return None
    task.phase = None
    task.current_module = None
    task.lease_until = None
    task.heartbeat_at = now
    if task.attempt >= MAX_ATTEMPTS:
        task.status = "failed"
        task.finished_at = now
        task.resume_after = None
        task.error_code = "GITHUB_RATE_LIMITED"
        task.error_message = "GitHub 多次限流，已保留检查点；请稍后手动重试"
        task.message = task.error_message
        status = "failed"
    else:
        task.status = "queued"
        task.finished_at = None
        task.resume_after = resume_after
        task.error_code = None
        task.error_message = None
        task.progress_kind = "unknown"
        task.progress_percent = None
        task.progress_updated_at = now
        task.message = "GitHub 配额暂时不足，任务已延迟恢复"
        status = "deferred"
    session.add(CollectionLog(
        request_id=task.task_id,
        task_id=task.task_id,
        repository_id=task.repository_id,
        event_type="collection_deferred" if status == "deferred" else "collection_failed",
        source_endpoint=f"/repositories/{task.repository_id}",
        http_status=429,
        message_redacted=task.message,
    ))
    session.commit()
    return status




def _finish_failed(
    session: Session,
    task_id: str,
    code: str,
    message: str,
    expected_attempt: int | None,
    expected_owner: str | None,
    details: dict[str, Any] | None = None,
) -> bool:
    session.rollback()
    begin_immediate(session)
    task = session.get(CollectionTask, task_id)
    now = utc_now()
    if not _owns_attempt(task, expected_attempt, expected_owner, now):
        session.rollback()
        return False
    task.status = "failed"
    task.phase = None
    if task.current_module:
        progress = session.get(TaskModuleProgress, (task.task_id, task.current_module))
        if progress and progress.attempt == task.attempt and progress.status == "running":
            progress.status = "failed"
            progress.coverage = "partial"
            progress.finished_at = now
            progress.elapsed_seconds = max(0.0, (now - progress.started_at).total_seconds()) if progress.started_at else None
            progress.error_code = code
            progress.last_updated_at = now
    task.current_module = None
    task.error_code = code
    task.error_message = message[:1000]
    task.message = message[:1000]
    task.finished_at = now
    task.heartbeat_at = now
    task.lease_until = None
    task.progress_updated_at = now if task.progress_kind == "stages" else task.progress_updated_at
    session.add(CollectionLog(request_id=task.task_id, task_id=task.task_id, repository_id=task.repository_id, event_type="collection_failed", http_status=details.get("http_status") if details else None, message_redacted=f"{code}: {message[:800]}"))
    session.commit()
    return True
