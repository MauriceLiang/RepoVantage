"""Import the versioned, purpose-grouped comparison repository catalogue."""

import json
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.clock import utc_now
from backend.app.core.config import PROJECT_ROOT
from backend.app.core.exceptions import AppError
from backend.app.persistence.db import begin_immediate
from backend.app.persistence.models import (
    ApplicationSetting,
    CollectionTask,
    Dataset,
    DatasetRepository,
    Repository,
    RepositoryGroup,
    RepositoryGroupMember,
)
from backend.app.services.repositories import LIBRARY_ID, make_task


MANIFEST_PATH = PROJECT_ROOT / "data" / "manifests" / "comparison-repositories-v1.json"
IMPORT_SETTING_KEY = "curated_comparison_repositories_v1"


def load_curated_manifest() -> dict[str, Any]:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AppError(500, "CURATED_MANIFEST_UNAVAILABLE", "仓库清单无法读取") from exc
    if not isinstance(manifest, dict) or manifest.get("manifest_id") != "comparison-repository-catalog-v1":
        raise AppError(500, "CURATED_MANIFEST_INVALID", "仓库清单格式无效")
    groups = manifest.get("groups")
    if not isinstance(groups, list) or not groups:
        raise AppError(500, "CURATED_MANIFEST_INVALID", "仓库清单没有分组")
    seen_ids: set[int] = set()
    seen_names: set[str] = set()
    seen_groups: set[str] = set()
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("name"), str) or not isinstance(group.get("repositories"), list):
            raise AppError(500, "CURATED_MANIFEST_INVALID", "仓库清单分组格式无效")
        group_name = group["name"].strip()
        if not group_name or group_name in seen_groups or len(group_name) > 80:
            raise AppError(500, "CURATED_MANIFEST_INVALID", "仓库清单分组名称无效或重复")
        seen_groups.add(group_name)
        for repository in group["repositories"]:
            repository_id = repository.get("repository_id") if isinstance(repository, dict) else None
            full_name = repository.get("full_name") if isinstance(repository, dict) else None
            if type(repository_id) is not int or repository_id <= 0 or not isinstance(full_name, str):
                raise AppError(500, "CURATED_MANIFEST_INVALID", "仓库清单项目格式无效")
            if repository_id in seen_ids or full_name.casefold() in seen_names:
                raise AppError(500, "CURATED_MANIFEST_INVALID", "仓库清单包含重复项目")
            seen_ids.add(repository_id)
            seen_names.add(full_name.casefold())
    if manifest.get("repository_count") != len(seen_ids):
        raise AppError(500, "CURATED_MANIFEST_INVALID", "仓库清单项目数量不匹配")
    collection = manifest.get("collection")
    if not isinstance(collection, dict) or type(collection.get("activity_window_days")) is not int or type(collection.get("maintenance_window_weeks")) is not int:
        raise AppError(500, "CURATED_MANIFEST_INVALID", "仓库清单采集范围无效")
    return manifest


def _stored_import(session: Session) -> dict[str, Any]:
    setting = session.get(ApplicationSetting, IMPORT_SETTING_KEY)
    if setting is None:
        return {}
    try:
        value = json.loads(setting.setting_value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _stored_task_ids(session: Session) -> list[str]:
    raw = _stored_import(session).get("task_ids", [])
    if not isinstance(raw, list):
        return []
    return list(dict.fromkeys(item for item in raw if isinstance(item, str)))


def _library_is_complete(session: Session, manifest: dict[str, Any]) -> bool:
    repositories = [repo for group in manifest["groups"] for repo in group["repositories"]]
    ids = {repo["repository_id"] for repo in repositories}
    library_ids = set(session.scalars(select(DatasetRepository.repository_id).where(
        DatasetRepository.dataset_id == LIBRARY_ID,
        DatasetRepository.selection_source.is_(None),
        DatasetRepository.repository_id.in_(ids),
    )))
    if library_ids != ids:
        return False

    groups = {group.name: group.id for group in session.scalars(select(RepositoryGroup)).all()}
    for group_spec in manifest["groups"]:
        group_id = groups.get(group_spec["name"])
        if group_id is None:
            return False
        expected_ids = {repo["repository_id"] for repo in group_spec["repositories"]}
        actual_ids = set(session.scalars(select(RepositoryGroupMember.repository_id).where(
            RepositoryGroupMember.group_id == group_id,
            RepositoryGroupMember.dataset_id == LIBRARY_ID,
            RepositoryGroupMember.repository_id.in_(expected_ids),
        )))
        if actual_ids != expected_ids:
            return False
    return True


def _task_counts(session: Session, task_ids: list[str]) -> dict[str, int]:
    if not task_ids:
        return {"total": 0, "queued": 0, "running": 0, "completed": 0, "failed": 0}
    tasks = session.scalars(select(CollectionTask).where(CollectionTask.task_id.in_(task_ids))).all()
    statuses = [task.status for task in tasks]
    return {
        "total": len(statuses),
        "queued": statuses.count("queued"),
        "running": statuses.count("running"),
        "completed": sum(status in {"succeeded", "partial"} for status in statuses),
        "failed": statuses.count("failed"),
    }


def curated_library_status(session: Session) -> dict[str, Any]:
    manifest = load_curated_manifest()
    complete = _library_is_complete(session, manifest)
    counts = _task_counts(session, _stored_task_ids(session))
    return {
        "available": True,
        "manifest_id": manifest["manifest_id"],
        "title": manifest["title"],
        "repository_count": manifest["repository_count"],
        "group_count": len(manifest["groups"]),
        "imported": complete,
        "collecting": counts["queued"] + counts["running"] > 0,
        "task_counts": counts,
    }


def import_curated_library(session: Session) -> dict[str, Any]:
    manifest = load_curated_manifest()
    begin_immediate(session)
    try:
        if _library_is_complete(session, manifest):
            counts = _task_counts(session, _stored_task_ids(session))
            session.commit()
            return {
                "already_imported": True,
                "repository_count": manifest["repository_count"],
                "group_count": len(manifest["groups"]),
                "queued_task_count": counts["queued"] + counts["running"],
                "task_counts": counts,
            }

        library = session.get(Dataset, LIBRARY_ID)
        if library is None:
            library = Dataset(
                dataset_id=LIBRARY_ID,
                name="我的仓库",
                type="library",
                description="仅包含用户主动导入或添加的仓库",
            )
            session.add(library)
            session.flush()

        existing_groups = {group.name: group for group in session.scalars(select(RepositoryGroup)).all()}
        group_rows: dict[str, RepositoryGroup] = {}
        for group_spec in manifest["groups"]:
            group = existing_groups.get(group_spec["name"])
            if group is None:
                group = RepositoryGroup(name=group_spec["name"])
                session.add(group)
                session.flush()
                existing_groups[group.name] = group
            group_rows[group_spec["name"]] = group

        started_at = utc_now()
        new_memberships = 0
        task_ids = _stored_task_ids(session)
        queued_task_ids: list[str] = []
        task_order = 0
        repository_specs = [repo for group in manifest["groups"] for repo in group["repositories"]]
        manifest_repository_ids = {repo["repository_id"] for repo in repository_specs}
        existing_repository_ids = set(session.scalars(select(Repository.repository_id).where(
            Repository.repository_id.in_(manifest_repository_ids),
        )))

        for group_spec in manifest["groups"]:
            group = group_rows[group_spec["name"]]
            for repo_spec in group_spec["repositories"]:
                repository_id = repo_spec["repository_id"]
                full_name = repo_spec["full_name"]
                repository = session.get(Repository, repository_id)
                same_name = session.scalar(select(Repository).where(Repository.full_name == full_name))
                if repository is not None and repository.full_name.casefold() != full_name.casefold():
                    raise AppError(409, "CURATED_REPOSITORY_ID_CONFLICT", f"仓库编号与清单不匹配：{full_name}")
                if same_name is not None and same_name.repository_id != repository_id:
                    raise AppError(409, "CURATED_REPOSITORY_NAME_CONFLICT", f"仓库名称与清单编号不匹配：{full_name}")
                if repository is None:
                    repository = Repository(
                        repository_id=repository_id,
                        full_name=full_name,
                        html_url=f"https://github.com/{full_name}",
                        description=None,
                        language=None,
                        topics_json="[]",
                        archived=False,
                        is_fork=False,
                    )
                    session.add(repository)
                    session.flush()

                membership = session.get(DatasetRepository, (LIBRARY_ID, repository_id))
                if membership is None:
                    session.add(DatasetRepository(dataset_id=LIBRARY_ID, repository_id=repository_id))
                    new_memberships += 1
                elif membership.selection_source is not None:
                    membership.selection_source = None
                session.flush()

                group_member = session.get(RepositoryGroupMember, (group.id, repository_id))
                if group_member is None:
                    session.add(RepositoryGroupMember(
                        group_id=group.id,
                        repository_id=repository_id,
                        dataset_id=LIBRARY_ID,
                    ))

        session.flush()
        scope_json = json.dumps({"lookback_weeks": manifest["collection"]["maintenance_window_weeks"]}, separators=(",", ":"))
        for group_spec in manifest["groups"]:
            for repo_spec in group_spec["repositories"]:
                repository_id = repo_spec["repository_id"]
                # A repository row means the catalogue entry is already in the local
                # system. Import should make it visible and grouped, but must not
                # silently recollect it just because its data is incomplete or stale.
                if repository_id in existing_repository_ids:
                    continue
                tasks = (
                    make_task(
                        session,
                        repository_id,
                        "deep",
                        scope_kind="window",
                        window_days=manifest["collection"]["activity_window_days"],
                        progress_motion="forward",
                    ),
                    make_task(
                        session,
                        repository_id,
                        "deep",
                        scope_kind="maintenance",
                        scope_json=scope_json,
                        progress_motion="forward",
                    ),
                )
                for task in tasks:
                    if task.task_id not in task_ids:
                        task_ids.append(task.task_id)
                    if task.status in {"queued", "running"}:
                        queued_task_ids.append(task.task_id)
                    # Distinct creation times make the queue follow manifest order,
                    # including when a fast local database rounds timestamps.
                    if task.created_at >= started_at and task.status == "queued":
                        task.created_at = started_at + timedelta(microseconds=task_order + 1)
                    task_order += 1

        setting = session.get(ApplicationSetting, IMPORT_SETTING_KEY)
        value = {
            "manifest_id": manifest["manifest_id"],
            "repository_count": manifest["repository_count"],
            "group_count": len(manifest["groups"]),
            "task_ids": task_ids,
            "imported_at": started_at.isoformat(),
        }
        if setting is None:
            session.add(ApplicationSetting(setting_key=IMPORT_SETTING_KEY, setting_value=json.dumps(value, ensure_ascii=False)))
        else:
            setting.setting_value = json.dumps(value, ensure_ascii=False)

        counts = _task_counts(session, task_ids)
        session.commit()
        return {
            # Existing catalogue rows are considered imported even when collection
            # has never run or has failed; users can start collection explicitly.
            "already_imported": existing_repository_ids == manifest_repository_ids,
            "repository_count": manifest["repository_count"],
            "new_repository_count": new_memberships,
            "existing_repository_count": len(existing_repository_ids),
            "group_count": len(manifest["groups"]),
            "queued_task_count": len(set(queued_task_ids)),
            "task_counts": counts,
        }
    except Exception:
        session.rollback()
        raise
