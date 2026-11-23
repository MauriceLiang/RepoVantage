"""insight releases domain queries."""

import json
from backend.app.core.exceptions import AppError
from backend.app.persistence.models import Repository
from backend.app.pipeline.collection_archive import iter_module_records
from backend.app.pipeline.raw_archive import read_archive

from backend.app.services.insight_record_helpers import _latest_insight_run


def repository_release_detail(session, repository_id, release_id):
    if session.get(Repository, repository_id) is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "本地仓库不存在")
    run = _latest_insight_run(session, repository_id)
    for archive_path in json.loads(run.source_archive_paths_json) if run else []:
        if not isinstance(archive_path, str):
            continue
        try:
            archive = read_archive(archive_path)
        except FileNotFoundError:
            continue
        try:
            for item in iter_module_records(archive.get("releases")):
                if item.get("id") == release_id:
                    return {
                        "id": str(release_id),
                        "name": item.get("name") if isinstance(item.get("name"), str) else None,
                        "body": item.get("body") if isinstance(item.get("body"), str) else None,
                    }
        except (OSError, ValueError, TypeError):
            continue
    from backend.app.services.course_test_events import historical_release_detail
    historical = historical_release_detail(session, repository_id, release_id)
    if historical is not None:
        return historical
    if run is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "尚无可读取 Release 说明的采集归档")
    raise AppError(404, "RESOURCE_NOT_FOUND", "当前采集归档中没有该 Release 说明，请重新采集仓库数据")


