from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import case, delete, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, load_only

from backend.app.api.dependencies import get_github_client, get_session
from backend.app.api.helpers import envelope, pagination
from backend.app.core.exceptions import AppError
from backend.app.integrations.github.client import GitHubClient, validate_full_name
from backend.app.persistence.db import begin_immediate
from backend.app.persistence.models import DatasetRepository, Repository, RepositoryGroup, RepositoryGroupMember, RepositorySnapshot
from backend.app.schemas.analytics import RepositoryListResponse
from backend.app.schemas.common import SuccessEnvelope
from backend.app.schemas.repositories import (
    AddRepositoryGroupMembersRequest,
    AddRepositoryRequest,
    AddRepositoryResponse,
    CreateRepositoryGroupRequest,
    RepositoryGroupResponse,
)
from backend.app.services.repositories import LIBRARY_ID, add_idempotency_response, cached_idempotency_response, enqueue_add, summaries
from backend.app.services.curated_library import curated_library_status, import_curated_library


router = APIRouter(prefix="/library", tags=["library"])


@router.get("/curated-import/status")
def get_curated_import_status(request: Request, session: Session = Depends(get_session)):
    return envelope(request, curated_library_status(session))


@router.post("/curated-import")
def post_curated_import(request: Request, session: Session = Depends(get_session)):
    return envelope(request, import_curated_library(session))


@router.post("/repositories", response_model=SuccessEnvelope[AddRepositoryResponse], status_code=201, responses={200: {"model": SuccessEnvelope[AddRepositoryResponse]}})
def add_repository(
    request: Request,
    body: AddRepositoryRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    session: Session = Depends(get_session),
    github: GitHubClient = Depends(get_github_client),
):
    cached = cached_idempotency_response(session, "library.add", idempotency_key)
    if cached:
        response.status_code = cached[1]
        return envelope(request, cached[0])
    owner, repo_name = validate_full_name(body.full_name)
    payload, _status, _etag = github.get_repository(f"{owner}/{repo_name}")
    if not payload or payload.get("private") is not False:
        raise AppError(404, "REPOSITORY_NOT_FOUND", "仓库不存在或不可公开访问")
    data, status_code = enqueue_add(session, payload, body.auto_analyze, body.depth, idempotency_key)
    data, status_code = add_idempotency_response(session, "library.add", idempotency_key, data, status_code)
    response.status_code = status_code
    return envelope(request, data)


@router.get("/repositories", response_model=SuccessEnvelope[RepositoryListResponse])
def list_repositories(
    request: Request,
    q: str | None = Query(default=None, max_length=100),
    language: str | None = None,
    status: str | None = Query(default=None, pattern="^(not_started|queued|processing|completed|partial|failed)$"),
    sort: str = Query(default="name", pattern="^(name|stars|last_collected)$"),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    # Imported research/featured samples remain available in their own datasets.
    # The personal repository screen contains only repositories explicitly added by the user.
    filters = [DatasetRepository.dataset_id == LIBRARY_ID, DatasetRepository.selection_source.is_(None)]
    if q:
        filters.append(Repository.full_name.ilike(f"%{q}%") | Repository.description.ilike(f"%{q}%"))
    if language:
        filters.append(Repository.language == language)
    statement = select(Repository).join(DatasetRepository, DatasetRepository.repository_id == Repository.repository_id).where(*filters)

    reverse = order == "desc"
    if sort == "name":
        sort_value = func.lower(Repository.full_name)
    else:
        snapshot_column = RepositorySnapshot.stars if sort == "stars" else RepositorySnapshot.collected_at
        sort_value = (
            select(snapshot_column)
            .where(RepositorySnapshot.repository_id == Repository.repository_id, RepositorySnapshot.valid.is_(True))
            .order_by(desc(RepositorySnapshot.collected_at), desc(RepositorySnapshot.id))
            .limit(1)
            .scalar_subquery()
        )
    null_rank = case((sort_value.is_(None), 1), else_=0)
    ordering = (
        [sort_value.desc() if reverse else sort_value.asc(), Repository.repository_id.asc()]
        if sort == "name"
        else [null_rank.desc() if reverse else null_rank.asc(), sort_value.desc() if reverse else sort_value.asc(), Repository.repository_id.asc()]
    )
    statement = statement.options(load_only(
        Repository.repository_id,
        Repository.full_name,
        Repository.description,
        Repository.language,
        Repository.created_at,
        Repository.pushed_at,
        Repository.archived,
    ))
    start = (page - 1) * per_page
    if status:
        rows = summaries(session, session.scalars(statement.order_by(*ordering)).all())
        rows = [row for row in rows if row["analysis_status"] == status]
        total = len(rows)
        items = rows[start : start + per_page]
    else:
        total = session.scalar(
            select(func.count(Repository.repository_id))
            .join(DatasetRepository, DatasetRepository.repository_id == Repository.repository_id)
            .where(*filters)
        ) or 0
        repositories = session.scalars(statement.order_by(*ordering).offset(start).limit(per_page)).all()
        items = summaries(session, repositories)
    return envelope(request, {"items": items}, pagination=pagination(page, per_page, total))


@router.delete("/repositories/{repository_id}", status_code=204)
def remove_repository(repository_id: int, session: Session = Depends(get_session)):
    repo = session.get(Repository, repository_id)
    if repo is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "本地仓库不存在")
    membership = session.get(DatasetRepository, (LIBRARY_ID, repository_id))
    if membership and membership.selection_source is None:
        session.delete(membership)
        session.commit()
    return Response(status_code=204)


def group_repository_ids(session: Session, group_id: int) -> list[int]:
    return list(session.scalars(
        select(RepositoryGroupMember.repository_id)
        .where(RepositoryGroupMember.group_id == group_id)
        .order_by(RepositoryGroupMember.repository_id)
    ))


def lock_group(session: Session, group_id: int) -> RepositoryGroup:
    begin_immediate(session)
    group = session.get(RepositoryGroup, group_id, with_for_update=True)
    if group is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "分组不存在")
    return group


def require_library_repositories(session: Session, repository_ids: set[int]) -> None:
    if not repository_ids:
        return
    library_ids = set(session.scalars(
        select(DatasetRepository.repository_id)
        .where(
            DatasetRepository.dataset_id == LIBRARY_ID,
            DatasetRepository.selection_source.is_(None),
            DatasetRepository.repository_id.in_(repository_ids),
        )
        .order_by(DatasetRepository.repository_id)
        .with_for_update()
    ))
    if library_ids != repository_ids:
        raise AppError(409, "REPOSITORY_NOT_IN_LIBRARY", "请先将仓库添加到我的仓库")


@router.get("/groups", response_model=SuccessEnvelope[list[RepositoryGroupResponse]])
def list_groups(request: Request, session: Session = Depends(get_session)):
    rows = session.execute(
        select(RepositoryGroup.id, RepositoryGroup.name, RepositoryGroupMember.repository_id)
        .outerjoin(RepositoryGroupMember)
        .order_by(RepositoryGroup.id, RepositoryGroupMember.repository_id)
    )
    groups: dict[int, RepositoryGroupResponse] = {}
    for group_id, name, repository_id in rows:
        if group_id not in groups:
            groups[group_id] = RepositoryGroupResponse(id=group_id, name=name, repository_ids=[])
        if repository_id is not None:
            groups[group_id].repository_ids.append(repository_id)
    return envelope(request, list(groups.values()))


@router.post("/groups", response_model=SuccessEnvelope[RepositoryGroupResponse], status_code=201)
def create_group(request: Request, body: CreateRepositoryGroupRequest, session: Session = Depends(get_session)):
    begin_immediate(session)
    requested = set(body.repository_ids)
    require_library_repositories(session, requested)
    group = RepositoryGroup(name=body.name)
    session.add(group)
    try:
        session.flush()
        session.add_all(
            RepositoryGroupMember(group_id=group.id, repository_id=repository_id, dataset_id=LIBRARY_ID)
            for repository_id in requested
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        if session.scalar(select(RepositoryGroup.id).where(RepositoryGroup.name == body.name)) is not None:
            raise AppError(409, "GROUP_NAME_IN_USE", "已有同名分组")
        raise
    return envelope(request, RepositoryGroupResponse(id=group.id, name=group.name, repository_ids=sorted(requested)))


@router.post("/groups/{group_id}/repositories", response_model=SuccessEnvelope[RepositoryGroupResponse])
def add_group_repositories(
    request: Request,
    group_id: int,
    body: AddRepositoryGroupMembersRequest,
    session: Session = Depends(get_session),
):
    group = lock_group(session, group_id)
    requested = set(body.repository_ids)
    require_library_repositories(session, requested)

    existing = set(group_repository_ids(session, group_id))
    session.add_all(
        RepositoryGroupMember(group_id=group_id, repository_id=repository_id, dataset_id=LIBRARY_ID)
        for repository_id in requested - existing
    )
    session.commit()
    return envelope(request, RepositoryGroupResponse(id=group.id, name=group.name, repository_ids=sorted(existing | requested)))


@router.delete("/groups/{group_id}/repositories/{repository_id}", response_model=SuccessEnvelope[RepositoryGroupResponse])
def remove_group_repository(request: Request, group_id: int, repository_id: int, session: Session = Depends(get_session)):
    group = lock_group(session, group_id)
    session.execute(delete(RepositoryGroupMember).where(
        RepositoryGroupMember.group_id == group_id,
        RepositoryGroupMember.repository_id == repository_id,
    ))
    result = RepositoryGroupResponse(id=group.id, name=group.name, repository_ids=group_repository_ids(session, group_id))
    session.commit()
    return envelope(request, result)
