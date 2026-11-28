"""Persist, reuse, and expose recent weekly activity observations."""
import hashlib
import json
from pathlib import Path

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.analytics.course_ml_features import FEATURE_SCHEMA_VERSION, InsufficientCourseData, build_weekly_features
from backend.app.core.clock import iso_z, parse_github_datetime, utc_now
from backend.app.core.config import get_settings
from backend.app.core.exceptions import AppError
from backend.app.persistence.db import begin_immediate
from backend.app.persistence.models import MaintenanceRun, MaintenanceWeek, Repository
from backend.app.services.repositories import make_task
from backend.app.services.maintenance_collection import _week_end

PATTERN_DISPLAY_NAMES = {
    "持续活动型": "持续提交型",
    "集中活动型": "集中提交型",
    "阶段波动型": "提交波动型",
    "低活动型": "低提交活动型",
}


def _hash_source(weeks, head, start, end):
    payload = {"weeks": weeks, "head_sha": head, "history_start": start, "history_end": end}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _archive_hash(relative):
    root = get_settings().raw_data_path.resolve()
    path = Path(relative)
    target = (root / path).resolve()
    if path.is_absolute() or not target.is_relative_to(root) or target.suffixes[-2:] != [".json", ".gz"] or target.stat().st_size > 16_000_000:
        raise ValueError("无效的来源归档")
    digest = hashlib.sha256()
    with target.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def persist_maintenance(session: Session, run_id, result, archive_path):
    if session.get(MaintenanceRun, run_id):
        raise ValueError("同一运行不能重复写入")
    weeks = result.get("weeks", [])
    source_hash = _hash_source(weeks, result.get("head_sha"), result["history_start"], result["history_end"])
    details = {key: result.get(key) for key in ("coverage_reasons", "source_audits", "default_branch", "snapshot_at",
                                                "limitations", "reason", "lookback_weeks", "requested_start",
                                                "request_estimate")}
    details["archive_sha256"] = _archive_hash(archive_path)
    session.add(MaintenanceRun(run_id=run_id, repository_id=result["repository_id"], status=result["status"],
                               history_start=parse_github_datetime(result["history_start"]), history_end=parse_github_datetime(result["history_end"]),
                               captured_at=parse_github_datetime(result["captured_at"]), head_sha=result.get("head_sha"),
                               source_sha256=source_hash, archive_path=archive_path, details_json=json.dumps(details, ensure_ascii=False)))
    session.flush()
    for row in weeks:
        session.add(MaintenanceWeek(run_id=run_id, week_start=parse_github_datetime(row["week_start_utc"]),
                                    week_end=parse_github_datetime(row["week_end_exclusive_utc"]), commits=row["commits"], prs_created=row["prs_created"],
                                    commit_coverage=row["commit_coverage"], pr_created_coverage=row["pr_created_coverage"]))


def enqueue_maintenance(session, repository_id, lookback_weeks=12):
    if lookback_weeks not in {12, 24}:
        raise AppError(422, "VALIDATION_ERROR", "维护活动窗口只支持 12 或 24 个完整 UTC 周")
    begin_immediate(session)
    if session.get(Repository, repository_id) is None:
        session.rollback()
        raise AppError(404, "RESOURCE_NOT_FOUND", "本地仓库不存在")
    now, current_end = utc_now(), _week_end(utc_now())
    candidates = session.scalars(select(MaintenanceRun).where(
        MaintenanceRun.repository_id == repository_id, MaintenanceRun.status == "complete",
        MaintenanceRun.history_end == current_end,
    ).order_by(desc(MaintenanceRun.captured_at), desc(MaintenanceRun.run_id))).all()
    for run in candidates:
        weeks = session.scalars(select(MaintenanceWeek).where(MaintenanceWeek.run_id == run.run_id)).all()
        if run.captured_at > now or not run.archive_path:
            continue
        try:
            details = json.loads(run.details_json)
            if (not isinstance(details, dict)
                    or type(details.get("lookback_weeks")) is not int
                    or details["lookback_weeks"] < lookback_weeks
                    or _archive_hash(run.archive_path) != details.get("archive_sha256")):
                continue
        except (OSError, TypeError, ValueError):
            continue
        session.commit()
        return {"task_id": None, "status": "cached", "reused": True, "run_id": run.run_id,
                "lookback_weeks": lookback_weeks}
    scope = json.dumps({"lookback_weeks": lookback_weeks})
    task = make_task(session, repository_id, "deep", scope_kind="maintenance", scope_json=scope)
    task_id, state = task.task_id, task.status
    session.commit()
    return {"task_id": task_id, "status": state, "reused": False, "run_id": None,
            "lookback_weeks": lookback_weeks}


def _empty_pattern(reason, *, run=None, evidence=None):
    return {"status": "insufficient_data", "method": "none", "reason_code": reason,
            "model_id": None, "model_version": None, "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "pattern_id": None, "pattern_name": None, "display_name": None,
            "as_of_utc": iso_z(run.history_end) if run else None,
            "history_start": iso_z(run.history_start) if run else None,
            "source_run_id": run.run_id if run else None, "source_sha256": run.source_sha256 if run else None,
            "collected_at": iso_z(run.captured_at) if run else None, "coverage": {"commits": "unknown", "pull_requests_created": "unknown"}, "window_weeks": 0,
            "evidence": evidence or {}, "limitations": ["未知或未覆盖周不作为零活动；维护画像不代表仓库质量。"]}


def maintenance_observation(session: Session, repository_id):
    """Return the latest archived weekly evidence regardless of its age."""
    run = session.scalar(select(MaintenanceRun).where(MaintenanceRun.repository_id == repository_id)
                         .order_by(desc(MaintenanceRun.captured_at), desc(MaintenanceRun.run_id)).limit(1))
    if run is None:
        return {"maintenance_pattern": _empty_pattern("not_collected"), "weeks": [], "features": None,
                "activity_trend": {"status": "insufficient_data", "method": "none", "reason_code": "not_collected", "notes": []}}
    if run.status == "insufficient_history":
        pattern = _empty_pattern("insufficient_history", run=run)
        return {"maintenance_pattern": pattern, "weeks": [], "features": None,
                "activity_trend": {"status": "insufficient_data", "method": "none", "reason_code": "insufficient_history", "notes": []}}
    if not run.archive_path:
        pattern = _empty_pattern("source_archive_unavailable", run=run)
        return {"maintenance_pattern": pattern, "weeks": [], "features": None,
                "activity_trend": {"status": "insufficient_data", "method": "none", "reason_code": "source_archive_unavailable", "notes": []}}
    try:
        details = json.loads(run.details_json)
        if not isinstance(details, dict):
            raise ValueError("maintenance details are invalid")
    except (TypeError, ValueError):
        pattern = _empty_pattern("source_archive_unavailable", run=run)
        return {"maintenance_pattern": pattern, "weeks": [], "features": None,
                "activity_trend": {"status": "insufficient_data", "method": "none", "reason_code": "source_archive_unavailable", "notes": []}}
    historical_course_snapshot = (details.get("dataset_id") == "course-research-300-v1"
                                  and details.get("data_source") == "course_research_historical_snapshot")
    try:
        if _archive_hash(run.archive_path) != details.get("archive_sha256"):
            raise ValueError("archive hash mismatch")
    except (OSError, TypeError, ValueError):
        pattern = _empty_pattern("source_archive_unavailable", run=run)
        return {"maintenance_pattern": pattern, "weeks": [], "features": None,
                "activity_trend": {"status": "insufficient_data", "method": "none", "reason_code": "source_archive_unavailable", "notes": []}}
    db_rows = session.scalars(select(MaintenanceWeek).where(MaintenanceWeek.run_id == run.run_id).order_by(MaintenanceWeek.week_start)).all()
    weeks = [{"week_start_utc": iso_z(row.week_start), "week_end_exclusive_utc": iso_z(row.week_end),
              "commits": row.commits, "prs_created": row.prs_created, "commit_coverage": row.commit_coverage,
              "pr_created_coverage": row.pr_created_coverage} for row in db_rows]
    if _hash_source(weeks, run.head_sha, iso_z(run.history_start), iso_z(run.history_end)) != run.source_sha256:
        pattern = _empty_pattern("source_integrity_mismatch", run=run)
        return {"maintenance_pattern": pattern, "weeks": [], "features": None,
                "activity_trend": {"status": "insufficient_data", "method": "none", "reason_code": "source_integrity_mismatch", "notes": []}}
    try:
        features = build_weekly_features(weeks)
    except InsufficientCourseData as exc:
        covered = [row for row in weeks if row["commit_coverage"] in {"complete", "true_zero"}]
        counts = [row["commits"] for row in covered]
        source_audits = details.get("source_audits") if isinstance(details.get("source_audits"), dict) else {}
        commit_audit = source_audits.get("commits") if isinstance(source_audits.get("commits"), dict) else {}
        request_estimate = details.get("request_estimate") if isinstance(details.get("request_estimate"), dict) else {}
        budget_exhausted = commit_audit.get("budget_exhausted") is True
        reason = "maintenance_page_budget_exceeded" if budget_exhausted else exc.reason
        evidence = {"commit_coverage": "partial", "commit_observed_weeks": len(weeks),
                    "commit_complete_weeks": len(covered), "commits_in_complete_weeks": sum(counts),
                    "commit_active_weeks_in_complete_weeks": sum(value > 0 for value in counts),
                    "commit_observed_partial_lower_bound": sum(row["commits"] for row in weeks),
                    "commit_partial_weeks": sum(row["commit_coverage"] == "partial" for row in weeks)}
        for key, value in (("commit_page_budget", commit_audit.get("page_budget")),
                           ("commit_pages_fetched", commit_audit.get("pages_fetched")),
                           ("github_request_estimate", request_estimate.get("total"))):
            if type(value) is int and value >= 0:
                evidence[key] = value
        pattern = _empty_pattern(reason, run=run, evidence=evidence)
        pattern["coverage"] = {"commits": "partial", "pull_requests_created": "complete" if all(
            row["pr_created_coverage"] in {"complete", "true_zero"} for row in weeks) else "partial_or_unavailable"}
        if budget_exhausted:
            pattern["limitations"].append("近期 Commit 详细采集超过课程版请求预算；未完整覆盖的数据未进入模型。")
        return {"maintenance_pattern": pattern, "weeks": weeks, "features": None,
                "activity_trend": {"status": "partial_data", "method": "none", "reason_code": reason, "notes": ["Commit 覆盖不完整，不将缺失周计为零。"]}}
    recent = weeks[-12:]
    counts = [row["commits"] for row in recent]
    prs = [row["prs_created"] for row in recent] if all(row["pr_created_coverage"] in {"complete", "true_zero"} for row in recent) else None
    evidence = {"window_weeks": len(weeks), "commit_observed_weeks": len(weeks),
                "commit_total_window": sum(row["commits"] for row in weeks)}
    coverage = {"commits": "complete" if run.status == "complete" else "partial",
                "pull_requests_created": "complete" if prs is not None else "partial_or_unavailable"}
    if len(counts) == 12:
        evidence.update({"commit_total_12w": sum(counts), "commit_active_weeks_12w": sum(value > 0 for value in counts),
                         "commit_active_fraction_12w": sum(value > 0 for value in counts) / 12,
                         "commit_longest_zero_weeks_12w": max((len(segment) for segment in "".join("0" if value == 0 else "1" for value in counts).split("1")), default=0)})
    if prs is not None:
        evidence["pr_created_total_12w"] = sum(prs)
        evidence["pr_active_weeks_12w"] = sum(value > 0 for value in prs)
    source_audits = details.get("source_audits") if isinstance(details.get("source_audits"), dict) else {}
    commit_audit = source_audits.get("commits") if isinstance(source_audits.get("commits"), dict) else {}
    request_estimate = details.get("request_estimate") if isinstance(details.get("request_estimate"), dict) else {}
    if isinstance(commit_audit, dict):
        for key, value in (("commit_page_budget", commit_audit.get("page_budget")),
                           ("commit_pages_fetched", commit_audit.get("pages_fetched"))):
            if type(value) is int and value >= 0:
                evidence[key] = value
    if isinstance(request_estimate, dict) and type(request_estimate.get("total")) is int:
        evidence["github_request_estimate"] = request_estimate["total"]
    pattern = {"status": "available", "method": "statistical_baseline", "reason_code": None,
               "model_id": None, "model_version": None, "feature_schema_version": FEATURE_SCHEMA_VERSION,
               "pattern_id": None, "pattern_name": None, "display_name": None, "as_of_utc": iso_z(run.history_end),
               "history_start": iso_z(run.history_start), "source_run_id": run.run_id,
               "source_sha256": run.source_sha256, "collected_at": iso_z(run.captured_at), "coverage": coverage,
               "window_weeks": len(weeks), "evidence": evidence,
               "limitations": ["仅描述可核验的近期行为，不代表仓库质量、健康度或技术采用价值。",
                               "Commit 按当前默认分支可见记录；最近完整 UTC 周以外的数据不参与模型。"]}
    from backend.app.services.course_ml import analyze_course_models
    analysis = analyze_course_models(recent)
    pattern.update(analysis["maintenance_pattern"])
    pattern["display_name"] = PATTERN_DISPLAY_NAMES.get(pattern.get("pattern_name"))
    pattern.update({"as_of_utc": iso_z(run.history_end), "history_start": iso_z(run.history_start),
                    "source_run_id": run.run_id, "source_sha256": run.source_sha256,
                    "collected_at": iso_z(run.captured_at), "coverage": coverage,
                    "window_weeks": len(weeks), "evidence": evidence})
    pattern["limitations"] = ["模式依据采集时默认分支最近 12 个完整 UTC 周的 Commit 活动；不包含 PR、Issue 或社区总体活跃度判断。",
                              "模式不代表仓库质量、健康度或技术采用价值；24 周扩展只提供额外事实背景。"]
    if historical_course_snapshot:
        pattern["limitations"].append(f"数据来自截至 {details.get('data_as_of') or iso_z(run.history_end)} 的固定课程历史快照；更新的在线维护记录优先。")
        analysis["activity_trend"].setdefault("notes", []).append("预测起点为固定历史快照的观察窗口结束时间，不表示当前实时活动。")
    return {"maintenance_pattern": pattern, "weeks": weeks, "features": features,
            "activity_trend": analysis["activity_trend"]}


def maintenance_pattern(session: Session, repository_id):
    return maintenance_observation(session, repository_id)["maintenance_pattern"]
