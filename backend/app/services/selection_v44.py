"""Versioned, same-scenario evidence for the v4.4 selection workspace."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.clock import utc_now
from backend.app.core.config import PROJECT_ROOT
from backend.app.persistence.models import (
    Repository,
    SelectionCapabilityEvidence,
    SelectionMetricSnapshot,
    SelectionScenario,
    SelectionScenarioCandidate,
    SelectionSnapshotRelease,
)


POLICY_VERSION = "selection-v44-historical-1"
METHODOLOGY_VERSION = "selection-metrics-v1"
CANDIDATE_PATH = PROJECT_ROOT / "data/manifests/selection-v44-candidates.json"
SNAPSHOT_PATH = PROJECT_ROOT / "data/manifests/selection-v44-historical-1.json"
CAPABILITY_PATH = PROJECT_ROOT / "data/manifests/selection-v44-capabilities.json"

SCENARIO_DETAILS = {
    "go-http-api": {
        "category": "Go HTTP/API 服务端技术选型",
        "constraints": ["标准 net/http 中间件依赖", "框架接口方式", "部署环境", "许可证"],
    },
    "python-api": {
        "category": "Python Web API 技术选型",
        "constraints": ["目标 Python 版本", "ASGI/WSGI", "接口文档需求", "部署方式"],
    },
    "jvm-services": {
        "category": "JVM 后端服务框架选型",
        "constraints": ["Java 版本", "原生编译需要", "依赖生态", "部署环境"],
    },
    "frontend-ui": {
        "category": "前端交互 UI 技术选型",
        "constraints": ["语言偏好", "组件生态", "工程现状", "团队熟悉度", "许可"],
    },
}

SUPPLEMENT_METADATA = {
    44344606: ("go-chi/chi", "Lightweight, idiomatic and composable router for building Go HTTP services.", "Go"),
    435625572: ("litestar-org/litestar", "A flexible ASGI framework for building APIs and applications in Python.", "Python"),
    130884470: ("solidjs/solid", "A declarative, efficient and flexible JavaScript library for building user interfaces.", "JavaScript"),
}


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@lru_cache(maxsize=1)
def _historical_snapshot() -> dict:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def ensure_selection_v44(session: Session) -> dict:
    """Idempotently seed the reviewed candidate policy and immutable S1 metrics."""
    policy = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    if policy.get("policy_id") != "repovantage-v4.4-curation-v1" or snapshot.get("snapshot_version") != POLICY_VERSION:
        raise ValueError("v4.4 selection source version mismatch")

    scenario_ids: dict[str, int] = {}
    now = utc_now()
    for definition in policy["scenarios"]:
        details = SCENARIO_DETAILS[definition["slug"]]
        scenario = session.scalar(select(SelectionScenario).where(SelectionScenario.slug == definition["slug"]))
        if scenario is None:
            scenario = SelectionScenario(
                slug=definition["slug"],
                title=details["category"],
                category=details["category"],
                purpose=definition["decision_scope"],
                hard_constraints_json=_json(details["constraints"]),
                version=POLICY_VERSION,
                status="published",
                created_at=now,
                updated_at=now,
            )
            session.add(scenario)
            session.flush()
        scenario_ids[scenario.slug] = scenario.id

    candidate_by_id = {int(item["github_repository_id"]): item for item in policy["repositories"]}
    for position, item in enumerate(policy["repositories"]):
        repository_id = int(item["github_repository_id"])
        full_name = item["full_name"]
        repository = session.get(Repository, repository_id)
        if repository is None:
            supplement = SUPPLEMENT_METADATA.get(repository_id)
            if not supplement or supplement[0] != full_name:
                raise ValueError(f"repository profile is missing for reviewed candidate {full_name}")
            repository = Repository(
                repository_id=repository_id,
                full_name=full_name,
                html_url=item["url"],
                description=supplement[1],
                language=supplement[2],
                topics_json="[]",
                archived=False,
                is_fork=False,
                first_seen_at=now,
                last_seen_at=now,
            )
            session.add(repository)
            session.flush()
        elif repository.full_name.casefold() != full_name.casefold():
            raise ValueError(f"GitHub repository ID conflict for {repository_id}: {repository.full_name} != {full_name}")

        slug = item.get("scenario") if item["disposition"] != "reference" else None
        scenario_id = scenario_ids.get(slug)
        existing = session.scalar(
            select(SelectionScenarioCandidate).where(
                SelectionScenarioCandidate.scenario_id == scenario_id,
                SelectionScenarioCandidate.repository_id == repository_id,
            )
        ) if scenario_id is not None else session.scalar(
            select(SelectionScenarioCandidate).where(
                SelectionScenarioCandidate.scenario_id.is_(None),
                SelectionScenarioCandidate.repository_id == repository_id,
            )
        )
        if existing is None:
            role = item["disposition"]
            session.add(SelectionScenarioCandidate(
                scenario_id=scenario_id,
                repository_id=repository_id,
                role=role,
                reference_group=item["scenario"] if role == "reference" else None,
                source_order=position,
                inclusion_reason=item["decision_note"],
                eligibility="conditional" if full_name == "gofiber/fiber" else ("unknown" if role in {"reference", "supplement"} else "eligible"),
                evidence_refs_json=_json([item["url"]]),
                reviewed_at=_datetime("2026-11-14T00:00:00Z") if role != "supplement" else None,
                review_method="repovantage-v4.4-curation-v1",
                exclude_reason="不进入同类技术选型排名；保留作专题参考" if role == "reference" else None,
                metric_collection_status="pending_collection" if role == "supplement" else ("historical_snapshot" if role == "compare" else "reference_only"),
            ))

    capability_policy = json.loads(CAPABILITY_PATH.read_text(encoding="utf-8"))
    capability_scenario_id = scenario_ids[capability_policy["scenario"]]
    for item in capability_policy["evidence"]:
        existing = session.scalar(select(SelectionCapabilityEvidence).where(
            SelectionCapabilityEvidence.scenario_id == capability_scenario_id,
            SelectionCapabilityEvidence.repository_id == int(item["repository_id"]),
            SelectionCapabilityEvidence.capability_key == capability_policy["capability_key"],
        ))
        if existing is None:
            session.add(SelectionCapabilityEvidence(
                scenario_id=capability_scenario_id,
                repository_id=int(item["repository_id"]),
                capability_key=capability_policy["capability_key"],
                status=item["status"],
                applicable_version=capability_policy["applicable_version"],
                evidence_url=item["evidence_url"],
                source_checked_at=_datetime(capability_policy["source_checked_at"]),
                rationale=item["rationale"],
            ))

    metrics_by_repo: dict[int, list[dict]] = {}
    for record in snapshot["metrics"]:
        metrics_by_repo.setdefault(int(record["repository_id"]), []).append(record)
    for scenario_slug, scenario_id in scenario_ids.items():
        for item in policy["repositories"]:
            repository_id = int(item["github_repository_id"])
            if item.get("scenario") != scenario_slug or item["disposition"] != "compare":
                continue
            for record in metrics_by_repo.get(repository_id, []):
                start = _datetime(record["window_start"])
                end = _datetime(record["window_end_exclusive"])
                existing = session.scalar(select(SelectionMetricSnapshot.id).where(
                    SelectionMetricSnapshot.scenario_id == scenario_id,
                    SelectionMetricSnapshot.repository_id == repository_id,
                    SelectionMetricSnapshot.metric_key == record["metric_key"],
                    SelectionMetricSnapshot.window_start == start,
                    SelectionMetricSnapshot.window_end_exclusive == end,
                    SelectionMetricSnapshot.methodology_version == record["methodology_version"],
                ))
                if existing is None:
                    session.add(SelectionMetricSnapshot(
                        scenario_id=scenario_id,
                        repository_id=repository_id,
                        metric_key=record["metric_key"],
                        value=record["value"],
                        unit=record["unit"],
                        sample_count=record["sample_count"],
                        window_start=start,
                        window_end_exclusive=end,
                        data_cutoff_at=_datetime(record["data_cutoff_at"]),
                        source_dataset_id=record["source_dataset_id"],
                        coverage_status=record["coverage_status"],
                        coverage_ratio=record["coverage_ratio"],
                        methodology_version=record["methodology_version"],
                        notes=record.get("notes"),
                    ))

        release = session.scalar(select(SelectionSnapshotRelease).where(
            SelectionSnapshotRelease.scenario_id == scenario_id,
            SelectionSnapshotRelease.scenario_version == POLICY_VERSION,
        ))
        if release is None:
            fingerprint_source = _json({"scenario": scenario_slug, "snapshot": snapshot["immutable_fingerprint"]}).encode()
            fingerprint = hashlib.sha256(fingerprint_source).hexdigest()
            session.add(SelectionSnapshotRelease(
                scenario_id=scenario_id,
                scenario_version=POLICY_VERSION,
                source_dataset_refs_json=_json(["featured-v1"]),
                cutoff_at=_datetime(snapshot["as_of"]),
                window_policy_json=_json({"activity": snapshot["activity_window"], "release": snapshot["release_window"]}),
                quality_report_path="docs/research-v44/selection-v44-quality.json",
                status="published",
                immutable_fingerprint=fingerprint,
                published_at=_datetime(snapshot["as_of"]),
            ))
    session.commit()
    return {"scenarios": len(scenario_ids), "candidates": len(candidate_by_id), "snapshot_version": POLICY_VERSION}


def selection_sources_ready(session: Session) -> bool:
    """The frozen featured bundle must supply all 15 reviewed repository profiles."""
    policy = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    repository_ids = [
        int(item["github_repository_id"])
        for item in policy["repositories"]
        if item["disposition"] != "supplement"
    ]
    found = session.scalars(select(Repository.repository_id).where(Repository.repository_id.in_(repository_ids))).all()
    return len(found) == len(repository_ids)


def _metric_dict(item: SelectionMetricSnapshot) -> dict:
    return {
        "value": item.value,
        "unit": item.unit,
        "sample_count": item.sample_count,
        "window_start": item.window_start.isoformat() + "Z" if item.window_start else None,
        "window_end_exclusive": item.window_end_exclusive.isoformat() + "Z" if item.window_end_exclusive else None,
        "as_of": item.data_cutoff_at.isoformat() + "Z",
        "coverage_status": item.coverage_status,
        "coverage_ratio": item.coverage_ratio,
        "methodology_version": item.methodology_version,
        "source_dataset": item.source_dataset_id,
        "notes": item.notes,
    }


def _capability_payload(item: SelectionCapabilityEvidence) -> dict:
    return {
        "capability_key": item.capability_key,
        "status": item.status,
        "applicable_version": item.applicable_version,
        "evidence_url": item.evidence_url,
        "source_checked_at": item.source_checked_at.isoformat() + "Z",
        "rationale": item.rationale,
    }


def _candidate_payload(
    repository: Repository,
    candidate: SelectionScenarioCandidate,
    metrics: list[SelectionMetricSnapshot],
    capabilities: list[SelectionCapabilityEvidence] | None = None,
) -> dict:
    metric_map = {item.metric_key: _metric_dict(item) for item in metrics}
    capability_items = capabilities or []
    required = ("weekly_commit_mean", "weekly_pr_open_mean", "issue_closed_median_days", "pr_merged_median_days", "release_interval_median_days")
    metrics_ready = all(
        key in metric_map and metric_map[key]["value"] is not None and metric_map[key]["coverage_status"] == "complete"
        for key in required
    )
    return {
        "repository_id": repository.repository_id,
        "full_name": repository.full_name,
        "html_url": repository.html_url,
        "description": repository.description,
        "language": repository.language,
        "license_spdx": repository.license_spdx,
        "eligibility": candidate.eligibility,
        "role": candidate.role,
        "reference_group": candidate.reference_group,
        "metrics_ready": metrics_ready,
        "metric_collection_status": candidate.metric_collection_status,
        "inclusion_reason": candidate.inclusion_reason,
        "evidence_refs": json.loads(candidate.evidence_refs_json or "[]"),
        "metrics": metric_map,
        "capabilities": [_capability_payload(item) for item in capability_items],
        "capability_evidence_status": "reviewed" if capability_items else "not_reviewed",
    }


def _scenario_candidates(session: Session, scenario_id: int) -> list[dict]:
    rows = session.execute(
        select(SelectionScenarioCandidate, Repository)
        .join(Repository, Repository.repository_id == SelectionScenarioCandidate.repository_id)
        .where(SelectionScenarioCandidate.scenario_id == scenario_id)
        .order_by(SelectionScenarioCandidate.source_order)
    ).all()
    ids = [repository.repository_id for _candidate, repository in rows]
    metrics_by_repo: dict[int, list[SelectionMetricSnapshot]] = {}
    capabilities_by_repo: dict[int, list[SelectionCapabilityEvidence]] = {}
    if ids:
        metrics = session.scalars(select(SelectionMetricSnapshot).where(
            SelectionMetricSnapshot.scenario_id == scenario_id,
            SelectionMetricSnapshot.repository_id.in_(ids),
        ).order_by(SelectionMetricSnapshot.metric_key)).all()
        for item in metrics:
            metrics_by_repo.setdefault(item.repository_id, []).append(item)
        capabilities = session.scalars(select(SelectionCapabilityEvidence).where(
            SelectionCapabilityEvidence.scenario_id == scenario_id,
            SelectionCapabilityEvidence.repository_id.in_(ids),
        ).order_by(SelectionCapabilityEvidence.capability_key)).all()
        for item in capabilities:
            capabilities_by_repo.setdefault(item.repository_id, []).append(item)
    return [_candidate_payload(repository, candidate, metrics_by_repo.get(repository.repository_id, []),
                               capabilities_by_repo.get(repository.repository_id, []))
            for candidate, repository in rows]


def list_scenarios(session: Session) -> dict:
    policy = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    priority = {item["slug"]: item["priority"] for item in policy["scenarios"]}
    scenarios = session.scalars(select(SelectionScenario).where(SelectionScenario.status == "published")).all()
    scenarios.sort(key=lambda item: priority.get(item.slug, len(priority)))
    output = []
    for scenario in scenarios:
        release = session.scalar(select(SelectionSnapshotRelease).where(
            SelectionSnapshotRelease.scenario_id == scenario.id,
            SelectionSnapshotRelease.status == "published",
        ).order_by(SelectionSnapshotRelease.published_at.desc()).limit(1))
        candidates = _scenario_candidates(session, scenario.id)
        output.append({
            "slug": scenario.slug,
            "title": scenario.title,
            "category": scenario.category,
            "version": release.scenario_version if release else scenario.version,
            "status": scenario.status,
            "published_at": release.published_at.isoformat() + "Z" if release and release.published_at else None,
            "as_of": release.cutoff_at.isoformat() + "Z" if release else None,
            "candidate_count": len(candidates),
            "ready_count": sum(candidate["metrics_ready"] for candidate in candidates),
            "pending_count": sum(candidate["metric_collection_status"] == "pending_collection" for candidate in candidates),
        })
    return {"scenarios": output}


def get_scenario(session: Session, slug: str) -> dict | None:
    scenario = session.scalar(select(SelectionScenario).where(SelectionScenario.slug == slug, SelectionScenario.status == "published"))
    if scenario is None:
        return None
    release = session.scalar(select(SelectionSnapshotRelease).where(
        SelectionSnapshotRelease.scenario_id == scenario.id,
        SelectionSnapshotRelease.status == "published",
    ).order_by(SelectionSnapshotRelease.published_at.desc()).limit(1))
    return {
        "slug": scenario.slug,
        "title": scenario.title,
        "category": scenario.category,
        "purpose": scenario.purpose,
        "hard_constraints": json.loads(scenario.hard_constraints_json),
        "version": release.scenario_version if release else scenario.version,
        "status": scenario.status,
        "as_of": release.cutoff_at.isoformat() + "Z" if release else None,
        "source_datasets": json.loads(release.source_dataset_refs_json) if release else [],
        "window_policy": json.loads(release.window_policy_json) if release else {},
        "immutable_fingerprint": release.immutable_fingerprint if release else None,
        "candidates": _scenario_candidates(session, scenario.id),
    }


def get_candidate(session: Session, slug: str, repository_id: int) -> dict | None:
    scenario = session.scalar(select(SelectionScenario).where(SelectionScenario.slug == slug, SelectionScenario.status == "published"))
    if scenario is None:
        return None
    row = session.execute(
        select(SelectionScenarioCandidate, Repository)
        .join(Repository, Repository.repository_id == SelectionScenarioCandidate.repository_id)
        .where(SelectionScenarioCandidate.scenario_id == scenario.id, SelectionScenarioCandidate.repository_id == repository_id)
    ).first()
    if row is None:
        return None
    candidate, repository = row
    metrics = session.scalars(select(SelectionMetricSnapshot).where(
        SelectionMetricSnapshot.scenario_id == scenario.id,
        SelectionMetricSnapshot.repository_id == repository_id,
    )).all()
    capabilities = session.scalars(select(SelectionCapabilityEvidence).where(
        SelectionCapabilityEvidence.scenario_id == scenario.id,
        SelectionCapabilityEvidence.repository_id == repository_id,
    ).order_by(SelectionCapabilityEvidence.capability_key)).all()
    capability_items = [_capability_payload(item) for item in capabilities]
    return {
        "scenario": slug,
        "candidate": _candidate_payload(repository, candidate, metrics, capabilities),
        "capabilities": capability_items,
        "capability_evidence_status": "reviewed" if capabilities else "not_reviewed",
        "limitations": (["功能证据核验于指标快照之后，基于仓库默认分支，未绑定指标截止日的历史 Release。"] if capabilities else ["功能/兼容性硬约束尚未逐项录入官方证据；unknown 不代表不支持。"])
        + ["活动快照不代表代码质量、性能或安全。"],
    }


def get_scenario_viz(session: Session, slug: str) -> dict | None:
    detail = get_scenario(session, slug)
    if detail is None:
        return None
    weekly_by_repo = {int(item["repository_id"]): item["weeks"] for item in _historical_snapshot().get("weekly_activity", [])}
    series = []
    for candidate in detail["candidates"]:
        values = candidate["metrics"]
        series.append({
            "repository_id": candidate["repository_id"],
            "full_name": candidate["full_name"],
            "role": candidate["role"],
            "eligibility": candidate["eligibility"],
            "metrics_ready": candidate["metrics_ready"],
            "x": values.get("weekly_commit_mean"),
            "y": values.get("weekly_pr_open_mean"),
            "dimensions": [values.get(key) for key in (
                "weekly_commit_mean", "weekly_pr_open_mean", "issue_closed_median_days",
                "pr_merged_median_days", "release_interval_median_days",
            )],
            "metrics": values,
            "capabilities": candidate["capabilities"],
            "weekly_activity": weekly_by_repo.get(candidate["repository_id"]),
        })
    return {
        "scenario": slug,
        "snapshot_version": detail["version"],
        "as_of": detail["as_of"],
        "activity_window": detail["window_policy"].get("activity"),
        "release_window": detail["window_policy"].get("release"),
        "candidates": series,
        "ranking_available": False,
        "ranking_reason": "此版本不生成 GitHub 总分；新补充候选尚未进入统一窗口。",
    }


def list_references(session: Session) -> list[dict]:
    rows = session.execute(
        select(SelectionScenarioCandidate, Repository)
        .join(Repository, Repository.repository_id == SelectionScenarioCandidate.repository_id)
        .where(SelectionScenarioCandidate.scenario_id.is_(None), SelectionScenarioCandidate.role == "reference")
        .order_by(SelectionScenarioCandidate.source_order)
    ).all()
    return [{"repository_id": repository.repository_id, "full_name": repository.full_name,
             "description": repository.description, "language": repository.language,
             "html_url": repository.html_url, "reference_group": candidate.reference_group,
             "reason": candidate.inclusion_reason}
            for candidate, repository in rows]
