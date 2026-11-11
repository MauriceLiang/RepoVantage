"""Course-version ML outcomes: three recent-activity tasks with explicit fallback states."""
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.exceptions import AppError
from backend.app.persistence.models import Dataset, DatasetRepository, Repository
from backend.app.analytics.course_ml_features import recent_commit_change


def model_decisions():
    from backend.app.services.course_ml import PATTERN_ARTIFACT, TREND_ARTIFACT, _artifact
    definitions = (
        ("M1-maintenance-pattern", PATTERN_ARTIFACT, "描述近 12 周行为；聚类不代表质量。"),
        ("M2-activity-trend", TREND_ARTIFACT, "只在活动证据足够时输出未来四周类别；不输出概率或精确数量。"),
    )
    models = []
    for model_id, artifact_name, reason in definitions:
        artifact = _artifact(artifact_name)
        models.append({"model_id": model_id, "status": "available" if artifact else "model_unavailable",
                       "reason": reason, "version": artifact.get("version") if artifact else None})
    models.append({"model_id": "M3-activity-anomaly", "status": "baseline_only",
                   "reason": "IsolationForest 仅保留研究；产品只显示待核查的 MAD 统计提示，真实人工复核尚未完成。",
                   "version": "mad-12w-v1"})
    return {"models": models}


def repository_evaluation(session: Session, repository_id: int):
    repository = session.get(Repository, repository_id)
    if repository is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "本地仓库不存在")
    from backend.app.services.maintenance import maintenance_observation
    observation = maintenance_observation(session, repository_id)
    membership = session.get(DatasetRepository, ("course-research-300-v1", repository_id))
    research_sample = None
    dataset = session.get(Dataset, "course-research-300-v1")
    if membership and membership.selection_tier in {"train", "test"} and dataset:
        try:
            metadata = json.loads(dataset.source_metadata_json or "{}")
        except (TypeError, ValueError):
            metadata = {}
        window = metadata.get("observation_window") if isinstance(metadata.get("observation_window"), dict) else {}
        research_sample = {
            "dataset_id": "course-research-300-v1",
            "dataset_version": str(metadata.get("version") or dataset.rules_version or "course-research-300-v1"),
            "sample_role": membership.selection_tier,
            "data_as_of": metadata.get("data_as_of"),
            "observation_start": window.get("start"),
            "observation_end_exclusive": window.get("end_exclusive"),
        }
    return {"repository_id": repository_id, "metrics": [],
            "maintenance_pattern": observation["maintenance_pattern"],
            "recent_activity_change": recent_commit_change(observation["weeks"]),
            "activity_trend": observation["activity_trend"],
            "activity_anomaly": observation["activity_anomaly"],
            "research_sample": research_sample,
            "limitations": ["课程设计版仅包含维护行为聚类、未来四周活跃趋势分类和活动异常提示。",
                            "未来活动预测只输出无概率类别；低活跃或覆盖不足时回退为事实统计。"]}
