from typing import Any

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_session
from backend.app.api.helpers import envelope
from backend.app.core.clock import iso_z
from backend.app.core.exceptions import AppError
from backend.app.persistence.models import ActivityWindow, Dataset, DatasetRepository, Repository, RepositorySnapshot
from backend.app.schemas.analytics import DatasetListResponse
from backend.app.schemas.common import SuccessEnvelope
from backend.app.services.analytics import get_datasets
from backend.app.services.dataset_import import dataset_coverage, featured_bundle_archive, featured_status, queue_featured_import


router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("", response_model=SuccessEnvelope[DatasetListResponse])
def datasets(request: Request, session: Session = Depends(get_session)):
    return envelope(request, {"items": get_datasets(session)})


@router.get("/featured/status", response_model=SuccessEnvelope[dict[str, Any]])
def get_featured_status(request: Request, session: Session = Depends(get_session)):
    return envelope(request, featured_status(session))


@router.post("/featured/import", response_model=SuccessEnvelope[dict[str, Any]], status_code=202)
def import_featured(
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    session: Session = Depends(get_session),
):
    result = queue_featured_import(session, idempotency_key)
    response.status_code = 200 if result.get("already_current") else 202
    return envelope(request, result)


@router.get("/featured/export", response_class=FileResponse)
def export_featured():
    path, filename = featured_bundle_archive()
    return FileResponse(path, media_type="application/zip", filename=filename, headers={"Cache-Control": "no-store"})


@router.get("/{dataset_id}/coverage", response_model=SuccessEnvelope[dict[str, Any]])
def get_dataset_coverage(dataset_id: str, request: Request, session: Session = Depends(get_session)):
    return envelope(request, dataset_coverage(session, dataset_id))


@router.get("/{dataset_id}/repositories")
def list_dataset_repositories(dataset_id: str, request: Request, session: Session = Depends(get_session)):
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "数据集不存在")

    memberships = session.execute(
        select(DatasetRepository, Repository)
        .join(Repository, Repository.repository_id == DatasetRepository.repository_id)
        .where(DatasetRepository.dataset_id == dataset_id, DatasetRepository.exclusion_status.is_(None))
        .order_by(DatasetRepository.selection_tier, Repository.full_name)
    ).all()
    repository_ids = [repository.repository_id for _membership, repository in memberships]
    if not repository_ids:
        return envelope(request, {
            "dataset_id": dataset.dataset_id,
            "name": dataset.name,
            "description": dataset.description,
            "frozen_at": iso_z(dataset.frozen_at),
            "sample_size": 0,
            "items": [],
        })

    snapshots = {}
    for snapshot in session.scalars(
        select(RepositorySnapshot)
        .where(RepositorySnapshot.repository_id.in_(repository_ids), RepositorySnapshot.valid.is_(True))
        .order_by(desc(RepositorySnapshot.collected_at), desc(RepositorySnapshot.id))
    ).all():
        snapshots.setdefault(snapshot.repository_id, snapshot)

    windows = {}
    for window in session.scalars(
        select(ActivityWindow)
        .where(ActivityWindow.repository_id.in_(repository_ids), ActivityWindow.depth == "deep")
        .order_by(desc(ActivityWindow.collected_at), desc(ActivityWindow.id))
    ).all():
        windows.setdefault(window.repository_id, window)

    items = []
    for membership, repository in memberships:
        snapshot = snapshots.get(repository.repository_id)
        window = windows.get(repository.repository_id)
        activity = None
        if window is not None:
            activity = {
                "window_start": iso_z(window.window_start),
                "window_end_exclusive": iso_z(window.window_end),
                "coverage": window.coverage,
                "collected_at": iso_z(window.collected_at),
                "commits": window.commits_count,
                "issues_opened": window.issues_opened_count,
                "issues_closed": window.issues_closed_count,
                "pulls_opened": window.pulls_opened_count,
                "pulls_merged": window.pulls_merged_count,
                "releases": window.releases_count,
            }
        items.append({
            "repository_id": repository.repository_id,
            "full_name": repository.full_name,
            "html_url": repository.html_url,
            "description": repository.description,
            "language": repository.language,
            "license_spdx": repository.license_spdx,
            "stars": snapshot.stars if snapshot else None,
            "forks": snapshot.forks if snapshot else None,
            "category": membership.selection_tier,
            "inclusion_reason": membership.inclusion_reason,
            "activity": activity,
        })
    return envelope(request, {
        "dataset_id": dataset.dataset_id,
        "name": dataset.name,
        "description": dataset.description,
        "frozen_at": iso_z(dataset.frozen_at),
        "sample_size": len(items),
        "items": items,
    })
