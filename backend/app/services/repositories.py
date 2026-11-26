import json
from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from backend.app.core.clock import iso_z, parse_github_datetime, utc_now
from backend.app.core.config import get_settings
from backend.app.core.exceptions import AppError
from backend.app.persistence.models import AnalysisResult, CollectionTask, Dataset, DatasetRepository, MaintenanceRun, Repository, RepositorySnapshot
from backend.app.persistence.db import begin_immediate


LIBRARY_ID = "library-default"
RESEARCH_ID = "research-2026-v1"
FEATURED_ID = "featured-default"
STANDARD_TEST_ID = "course-research-test-150-v1"
STANDARD_TEST_NAME = "机器学习标准测试数据集（150 个留出仓库）"
COURSE_RESEARCH_ID = "course-research-300-v1"


def ensure_default_datasets(session: Session) -> None:
    defaults = (
        (LIBRARY_ID, "我的仓库", "library", None, None, "仅包含用户主动导入或添加的仓库；机器学习研究样本单独保存"),
    )
    for dataset_id, name, kind, rules, frozen_at, description in defaults:
        if session.get(Dataset, dataset_id) is None:
            session.add(Dataset(dataset_id=dataset_id, name=name, type=kind, rules_version=rules, frozen_at=frozen_at, description=description))
    session.commit()


def repository_from_github(session: Session, payload: dict[str, Any]) -> Repository:
    repository_id = payload.get("id")
    full_name = payload.get("full_name")
    if not isinstance(repository_id, int) or isinstance(repository_id, bool) or repository_id <= 0 or not isinstance(full_name, str):
        raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 仓库资料缺少有效 ID 或 full_name")
    from backend.app.integrations.github.client import validate_full_name

    owner, name = validate_full_name(full_name)
    full_name = f"{owner}/{name}"
    now = utc_now()
    repo = session.get(Repository, repository_id)
    if repo is None:
        repo = session.scalar(select(Repository).where(Repository.full_name == full_name))
    if repo is None:
        repo = Repository(repository_id=repository_id, full_name=full_name, html_url=payload.get("html_url") or f"https://github.com/{full_name}", first_seen_at=now, last_seen_at=now)
        session.add(repo)
    repo.full_name = full_name
    repo.html_url = f"https://github.com/{full_name}"
    repo.description = payload.get("description") if isinstance(payload.get("description"), str) else None
    repo.language = payload.get("language") if isinstance(payload.get("language"), str) else None
    topics = payload.get("topics")
    repo.topics_json = json.dumps([topic for topic in topics if isinstance(topic, str)] if isinstance(topics, list) else [], ensure_ascii=False)
    license_data = payload.get("license") if isinstance(payload.get("license"), dict) else {}
    repo.license_spdx = license_data.get("spdx_id") if isinstance(license_data.get("spdx_id"), str) else None
    repo.created_at = parse_github_datetime(payload.get("created_at"))
    repo.pushed_at = parse_github_datetime(payload.get("pushed_at"))
    repo.github_updated_at = parse_github_datetime(payload.get("updated_at"))
    repo.archived = payload.get("archived") if isinstance(payload.get("archived"), bool) else False
    repo.is_fork = payload.get("fork") if isinstance(payload.get("fork"), bool) else False
    size = payload.get("size")
    repo.size_kb = size if isinstance(size, int) and not isinstance(size, bool) and size >= 0 else None
    repo.last_seen_at = now
    return repo


def make_task(
    session: Session,
    repository_id: int,
    depth: str,
    *,
    scope_kind: str = "quick",
    window_days: int = 90,
    scope_json: str | None = None,
    progress_motion: str = "bounce",
    retry_of: str | None = None,
    idempotency_key: str | None = None,
) -> CollectionTask:
    if depth == "basic":
        scope_kind = "quick"
    active = session.scalars(
        select(CollectionTask)
        .where(CollectionTask.repository_id == repository_id, CollectionTask.status.in_(["queued", "running"]))
        .order_by(desc(CollectionTask.created_at))
    ).all()
    for existing in active:
        same_scope = existing.scope_kind == scope_kind
        same_window = scope_kind not in {"quick", "window"} or _task_window_days(existing) == window_days
        if scope_kind == "maintenance":
            try:
                existing_scope = json.loads(existing.scope_json or "{}")
            except (TypeError, ValueError):
                existing_scope = {}
            try:
                requested_scope = json.loads(scope_json or "{}")
            except (TypeError, ValueError):
                requested_scope = {}
            same_window = existing_scope.get("lookback_weeks", 12) == requested_scope.get("lookback_weeks", 12)
        if (existing.depth == depth and (depth == "basic" or (same_scope and same_window))) or (depth == "basic" and existing.depth == "deep" and existing.scope_kind != "maintenance"):
            return existing
    now = utc_now()
    if depth == "deep" and scope_json is None:
        scope = {
            "window_start": iso_z(now - timedelta(days=window_days)),
            "window_end": iso_z(now),
            "window_days": window_days,
        }
    else:
        try:
            scope = json.loads(scope_json or "{}")
        except (TypeError, ValueError):
            scope = {}
        if not isinstance(scope, dict):
            scope = {}
    scope["progress_motion"] = progress_motion if progress_motion in {"forward", "bounce"} else "bounce"
    scope_json = json.dumps(scope, ensure_ascii=False)
    task = CollectionTask(
        task_id=str(uuid4()), repository_id=repository_id, depth=depth, scope_kind=scope_kind,
        scope_json=scope_json, status="queued", retry_of=retry_of, idempotency_key=idempotency_key,
        created_at=now,
    )
    session.add(task)
    session.flush()
    return task


def _task_window_days(task: CollectionTask) -> int:
    try:
        scope = json.loads(task.scope_json or "{}")
    except (TypeError, ValueError):
        scope = {}
    days = scope.get("window_days") if isinstance(scope, dict) else None
    if isinstance(days, int) and not isinstance(days, bool) and days in {30, 90, 180}:
        return days
    start = parse_github_datetime(scope.get("window_start")) if isinstance(scope, dict) else None
    end = parse_github_datetime(scope.get("window_end")) if isinstance(scope, dict) else None
    if start is not None and end is not None and start < end:
        return max(1, round((end - start).total_seconds() / 86400))
    return 90


def latest_snapshot(session: Session, repository_id: int) -> RepositorySnapshot | None:
    return session.scalar(select(RepositorySnapshot).where(RepositorySnapshot.repository_id == repository_id, RepositorySnapshot.valid.is_(True)).order_by(desc(RepositorySnapshot.collected_at), desc(RepositorySnapshot.id)).limit(1))


def latest_analysis(session: Session, repository_id: int, depth: str | None = "basic") -> AnalysisResult | None:
    statement = select(AnalysisResult).where(AnalysisResult.repository_id == repository_id)
    if depth is not None:
        statement = statement.where(AnalysisResult.analysis_kind == depth)
    return session.scalar(statement.order_by(desc(AnalysisResult.source_collected_at), desc(AnalysisResult.result_id)).limit(1))


def latest_task(session: Session, repository_id: int) -> CollectionTask | None:
    return session.scalar(select(CollectionTask).where(CollectionTask.repository_id == repository_id).order_by(desc(CollectionTask.created_at), desc(CollectionTask.task_id)).limit(1))


def analysis_status(session: Session, repository_id: int) -> str:
    analysis = latest_analysis(session, repository_id, None)
    if analysis:
        return "partial" if analysis.coverage == "partial" else "completed"
    task = latest_task(session, repository_id)
    if task is None:
        return "not_started"
    if task.status in ("queued", "running"):
        return "queued" if task.status == "queued" else "processing"
    return task.status if task.status in {"partial", "failed"} else "not_started"


def summaries(session: Session, repositories: list[Repository]) -> list[dict[str, Any]]:
    if not repositories:
        return []

    repository_ids = [repo.repository_id for repo in repositories]
    latest_snapshots = select(
        RepositorySnapshot.repository_id.label("repository_id"),
        RepositorySnapshot.collected_at.label("collected_at"),
        RepositorySnapshot.stars.label("stars"),
        RepositorySnapshot.forks.label("forks"),
        RepositorySnapshot.pushed_at.label("pushed_at"),
        func.row_number().over(
            partition_by=RepositorySnapshot.repository_id,
            order_by=(desc(RepositorySnapshot.collected_at), desc(RepositorySnapshot.id)),
        ).label("position"),
    ).where(RepositorySnapshot.repository_id.in_(repository_ids), RepositorySnapshot.valid.is_(True)).subquery()
    snapshots = {
        row.repository_id: row
        for row in session.execute(select(latest_snapshots).where(latest_snapshots.c.position == 1))
    }

    latest_tasks = select(
        CollectionTask.repository_id.label("repository_id"),
        CollectionTask.task_id.label("task_id"),
        CollectionTask.status.label("status"),
        func.row_number().over(
            partition_by=CollectionTask.repository_id,
            order_by=(desc(CollectionTask.created_at), desc(CollectionTask.task_id)),
        ).label("position"),
    ).where(CollectionTask.repository_id.in_(repository_ids)).subquery()
    tasks = {
        row.repository_id: row
        for row in session.execute(select(latest_tasks).where(latest_tasks.c.position == 1))
    }

    latest_analyses = select(
        AnalysisResult.repository_id.label("repository_id"),
        AnalysisResult.coverage.label("coverage"),
        func.row_number().over(
            partition_by=AnalysisResult.repository_id,
            order_by=(desc(AnalysisResult.source_collected_at), desc(AnalysisResult.result_id)),
        ).label("position"),
    ).where(AnalysisResult.repository_id.in_(repository_ids)).subquery()
    analyses = {
        row.repository_id: row
        for row in session.execute(select(latest_analyses).where(latest_analyses.c.position == 1))
    }

    datasets_by_repository: dict[int, set[str]] = {}
    for repository_id, dataset_id in session.execute(
        select(DatasetRepository.repository_id, DatasetRepository.dataset_id).where(DatasetRepository.repository_id.in_(repository_ids))
    ):
        datasets_by_repository.setdefault(repository_id, set()).add(dataset_id)

    historical_run_ids = [f"course150-v1-{repository_id}" for repository_id in repository_ids]
    historical_repository_ids = set(session.scalars(
        select(MaintenanceRun.repository_id).where(MaintenanceRun.run_id.in_(historical_run_ids))
    ))

    now = utc_now()
    refresh_hours = get_settings().base_refresh_hours
    rows = []
    for repo in repositories:
        snapshot = snapshots.get(repo.repository_id)
        task = tasks.get(repo.repository_id)
        analysis = analyses.get(repo.repository_id)
        datasets = datasets_by_repository.get(repo.repository_id, set())
        has_historical_data = COURSE_RESEARCH_ID in datasets and repo.repository_id in historical_repository_ids

        if analysis is not None:
            status = "partial" if analysis.coverage == "partial" else "completed"
        elif task is None:
            status = "not_started"
        elif task.status in ("queued", "running"):
            status = "queued" if task.status == "queued" else "processing"
        else:
            status = task.status if task.status in {"partial", "failed"} else "not_started"

        if has_historical_data and status in {"not_started", "failed"}:
            status = "completed" if status == "not_started" else "partial"
        collected = snapshot.collected_at if snapshot is not None else None
        data_status = "missing" if collected is None else ("fresh" if now - collected <= timedelta(hours=refresh_hours) else "stale")
        rows.append({
            "repository_id": repo.repository_id,
            "full_name": repo.full_name,
            "description": repo.description,
            "language": repo.language,
            "stars": snapshot.stars if snapshot is not None else None,
            "forks": snapshot.forks if snapshot is not None else None,
            "created_at": iso_z(repo.created_at),
            "pushed_at": iso_z(snapshot.pushed_at if snapshot is not None else repo.pushed_at),
            "archived": repo.archived,
            "analysis_status": status,
            "data_status": data_status,
            "last_successful_collection_at": iso_z(collected),
            "latest_task_id": task.task_id if task is not None else None,
            "datasets": sorted(datasets),
            "has_historical_data": has_historical_data,
        })
    return rows


def summary(session: Session, repo: Repository) -> dict[str, Any]:
    return summaries(session, [repo])[0]


def preview(payload: dict[str, Any], already_in_library: bool) -> dict[str, Any]:
    repository_id = payload.get("id")
    full_name = payload.get("full_name")
    if not isinstance(repository_id, int) or isinstance(repository_id, bool) or repository_id <= 0 or not isinstance(full_name, str):
        raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 仓库预览缺少有效 ID 或 full_name")
    from backend.app.integrations.github.client import validate_full_name

    owner, name = validate_full_name(full_name)
    full_name = f"{owner}/{name}"
    archived, is_fork = payload.get("archived"), payload.get("fork")
    if not isinstance(archived, bool) or not isinstance(is_fork, bool):
        raise AppError(502, "GITHUB_UPSTREAM_ERROR", "GitHub 仓库预览缺少有效 archived 或 fork 字段")
    stars = payload.get("stargazers_count")
    forks = payload.get("forks_count")
    return {
        "repository_id": repository_id,
        "full_name": full_name,
        "html_url": f"https://github.com/{full_name}",
        "description": payload.get("description") if isinstance(payload.get("description"), str) else None,
        "language": payload.get("language") if isinstance(payload.get("language"), str) else None,
        "stars": stars if isinstance(stars, int) and not isinstance(stars, bool) and stars >= 0 else None,
        "forks": forks if isinstance(forks, int) and not isinstance(forks, bool) and forks >= 0 else None,
        "archived": archived,
        "is_fork": is_fork,
        "already_in_library": already_in_library,
        "github_updated_at": iso_z(parse_github_datetime(payload.get("updated_at"))),
    }


def membership_exists(session: Session, repository_id: int) -> bool:
    membership = session.get(DatasetRepository, (LIBRARY_ID, repository_id))
    return membership is not None and membership.selection_source is None


def enqueue_add(session: Session, github_payload: dict[str, Any], auto_analyze: bool, depth: str, idempotency_key: str | None) -> tuple[dict[str, Any], int]:
    begin_immediate(session)
    repo = repository_from_github(session, github_payload)
    session.flush()
    membership = session.get(DatasetRepository, (LIBRARY_ID, repo.repository_id))
    created = membership is None or membership.selection_source is not None
    if membership is None:
        session.add(DatasetRepository(dataset_id=LIBRARY_ID, repository_id=repo.repository_id))
    elif membership.selection_source is not None:
        # Adding an imported sample from the UI is an explicit choice to make it a personal repository.
        membership.selection_source = None
        membership.added_at = utc_now()
    task = None
    if auto_analyze and (created or latest_analysis(session, repo.repository_id) is None):
        task = make_task(
            session,
            repo.repository_id,
            depth,
            scope_kind="window",
            window_days=180,
            progress_motion="forward",
            idempotency_key=idempotency_key,
        )
    elif auto_analyze:
        task = session.scalar(select(CollectionTask).where(CollectionTask.repository_id == repo.repository_id, CollectionTask.status.in_(["queued", "running"])).order_by(desc(CollectionTask.created_at)).limit(1))
    result = {
        "repository_id": repo.repository_id,
        "membership_created": created,
        "analysis_status": ("queued" if task and task.status == "queued" else ("processing" if task and task.status == "running" else analysis_status(session, repo.repository_id))),
        "task_id": task.task_id if task else None,
    }
    session.commit()
    return result, 201 if created else 200


def enqueue_refresh(
    session: Session,
    repository_id: int,
    depth: str,
    idempotency_key: str | None,
    force: bool = False,
    scope_kind: str = "quick",
    window_days: int = 90,
) -> dict[str, Any]:
    if session.get(Repository, repository_id) is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "本地仓库不存在")
    begin_immediate(session)
    existing_ids = {task.task_id for task in session.scalars(select(CollectionTask).where(CollectionTask.repository_id == repository_id, CollectionTask.status.in_(["queued", "running"]))).all()}
    if not existing_ids and not force and depth == "basic":
        snapshot = latest_snapshot(session, repository_id)
        analysis = latest_analysis(session, repository_id, "basic")
        if snapshot and analysis and analysis.source_collected_at == snapshot.collected_at and utc_now() - snapshot.collected_at <= timedelta(hours=get_settings().base_refresh_hours):
            completed = session.scalar(
                select(CollectionTask)
                .where(CollectionTask.repository_id == repository_id, CollectionTask.depth == "basic", CollectionTask.status.in_(["succeeded", "partial"]))
                .order_by(desc(CollectionTask.finished_at))
                .limit(1)
            )
            if completed:
                result = {"task_id": completed.task_id, "reused": True, "status": completed.status}
                session.commit()
                return result
    task = make_task(session, repository_id, depth, scope_kind=scope_kind, window_days=window_days, idempotency_key=idempotency_key)
    result = {"task_id": task.task_id, "reused": task.task_id in existing_ids, "status": task.status}
    session.commit()
    return result


def add_idempotency_response(session: Session, operation: str, key: str | None, payload: dict[str, Any], status_code: int) -> tuple[dict[str, Any], int]:
    if not key:
        return payload, status_code
    from backend.app.persistence.models import RequestIdempotency

    now = utc_now()
    row = session.get(RequestIdempotency, key)
    if row and row.expires_at > now:
        if row.operation != operation:
            raise AppError(409, "CONFLICTING_OPERATION", "Idempotency-Key 已用于其他操作")
        return json.loads(row.response_json), row.status_code
    if row:
        session.delete(row)
    old_tasks = session.scalars(select(CollectionTask).where(CollectionTask.idempotency_key == key)).all()
    for task in old_tasks:
        task.idempotency_key = None
    session.add(RequestIdempotency(key=key, operation=operation, created_at=now, expires_at=now + timedelta(hours=24), response_json=json.dumps(payload), status_code=status_code))
    session.commit()
    return payload, status_code


def cached_idempotency_response(session: Session, operation: str, key: str | None) -> tuple[dict[str, Any], int] | None:
    if not key:
        return None
    from backend.app.persistence.models import RequestIdempotency

    row = session.get(RequestIdempotency, key)
    if row is None:
        return None
    if row.expires_at <= utc_now():
        session.delete(row)
        for task in session.scalars(select(CollectionTask).where(CollectionTask.idempotency_key == key)).all():
            task.idempotency_key = None
        session.commit()
        return None
    if row.operation != operation:
        raise AppError(409, "CONFLICTING_OPERATION", "Idempotency-Key 已用于其他操作")
    return json.loads(row.response_json), row.status_code
