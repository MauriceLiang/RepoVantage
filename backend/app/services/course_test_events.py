"""使用随应用分发的历史事件快照生成仓库分析。"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import sqlite3
import tempfile
from collections import Counter
from datetime import datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from statistics import median

from backend.app.analytics.chart_data import build_chart_data
from backend.app.analytics.insights import calculate_insights, quality as insight_quality
from backend.app.core.clock import iso_z, parse_github_datetime, utc_naive, utc_now
from backend.app.core.config import PROJECT_ROOT, get_settings
from backend.app.core.exceptions import AppError
from backend.app.persistence.models import DatasetRepository, MaintenanceRun, Repository

BUNDLE = PROJECT_ROOT / "data/datasets/course-research-events-300-v1"
ORIGIN = "course-test-events-v1"
COURSE_DATASET_ID = "course-research-300-v1"
MAX_SQLITE_BYTES = 256 * 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@lru_cache(maxsize=4)
def _prepare_snapshot(raw_root: Path, manifest_mtime: int, archive_mtime: int, archive_size: int):
    del manifest_mtime, archive_mtime, archive_size  # 文件变化时重新校验缓存。
    manifest_path, archive = BUNDLE / "dataset.json", BUNDLE / "events.sqlite3.gz"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("历史事件清单格式无效")
        expected_size = manifest["sqlite_size"]
        sqlite_hash = manifest.get("sqlite_sha256")
        if (manifest.get("schema_version") != 1 or manifest.get("dataset_id") != ORIGIN
                or manifest.get("sample_dataset_id") != COURSE_DATASET_ID or manifest.get("repository_count") != 300
                or not isinstance(sqlite_hash, str) or len(sqlite_hash) != 64 or any(char not in "0123456789abcdef" for char in sqlite_hash)
                or type(expected_size) is not int or not 0 < expected_size <= MAX_SQLITE_BYTES
                or _sha256(archive) != manifest.get("archive_sha256")):
            raise ValueError("历史事件包校验失败")
        target = raw_root / COURSE_DATASET_ID / f"events-{sqlite_hash}.sqlite3"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.stat().st_size != expected_size or _sha256(target) != manifest.get("sqlite_sha256"):
                raise ValueError("历史事件归档校验失败")
        else:
            with tempfile.NamedTemporaryFile(prefix=".course-test-events-", dir=target.parent, delete=False) as stream:
                temporary = Path(stream.name)
            try:
                digest, size = hashlib.sha256(), 0
                with gzip.open(archive, "rb") as source, temporary.open("wb") as destination:
                    while block := source.read(1024 * 1024):
                        size += len(block)
                        if size > expected_size:
                            raise ValueError("历史事件归档超过声明大小")
                        digest.update(block)
                        destination.write(block)
                if size != expected_size or digest.hexdigest() != manifest.get("sqlite_sha256"):
                    raise ValueError("历史事件归档校验失败")
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        return target, manifest
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppError(503, "COURSE_TEST_EVENTS_UNAVAILABLE", "历史事件数据无法校验或读取") from exc


def _snapshot():
    manifest, archive = BUNDLE / "dataset.json", BUNDLE / "events.sqlite3.gz"
    if not manifest.exists() and not archive.exists():
        return None
    try:
        manifest_stat, archive_stat = manifest.stat(), archive.stat()
    except OSError as exc:
        raise AppError(503, "COURSE_TEST_EVENTS_UNAVAILABLE", "历史事件数据包不完整") from exc
    return _prepare_snapshot(get_settings().raw_data_path.resolve(), manifest_stat.st_mtime_ns,
                             archive_stat.st_mtime_ns, archive_stat.st_size)


def historical_metric_summary(connection, manifest: dict, repository_id: int, window_days: int) -> dict | None:
    """为课程研究页计算其使用的耗时中位数，不构造未展示的图表序列。"""
    available_start = parse_github_datetime(manifest.get("window_start"))
    available_end = parse_github_datetime(manifest.get("window_end"))
    if available_start is None or available_end is None:
        raise AppError(503, "COURSE_TEST_EVENTS_UNAVAILABLE", "历史事件缺少有效观察窗口")
    start, end = available_end - timedelta(days=window_days), available_end
    if start < available_start or end > available_end or start >= end:
        return None

    try:
        states = dict(connection.execute("SELECT module,status FROM coverage WHERE repository_id=?", (repository_id,)))
        if set(states) != {"commits", "issues", "pull_requests_created", "pull_requests_updated", "releases"}:
            raise ValueError("历史仓库的模块覆盖记录不完整")
        profile = connection.execute("SELECT created_at FROM repositories WHERE repository_id=?", (repository_id,)).fetchone()
        created = parse_github_datetime(profile["created_at"]) if profile else None
        if created is None:
            raise ValueError("历史仓库缺少创建时间")

        lower, upper = iso_z(start), iso_z(end)
        issue_observed = connection.execute(
            "SELECT COUNT(*) FROM issues WHERE repository_id=? AND ((created_at>=? AND created_at<?) OR (closed_at>=? AND closed_at<?))",
            (repository_id, lower, upper, lower, upper),
        ).fetchone()[0]
        issue_rows = connection.execute(
            "SELECT created_at,closed_at FROM issues WHERE repository_id=? AND closed_at>=? AND closed_at<?",
            (repository_id, lower, upper),
        ).fetchall()
        issue_durations = []
        for row in issue_rows:
            opened, closed = parse_github_datetime(row["created_at"]), parse_github_datetime(row["closed_at"])
            if opened is not None and closed is not None and closed >= opened:
                issue_durations.append((closed - opened).total_seconds() / 3600)

        pull_observed = connection.execute(
            "SELECT COUNT(*) FROM pulls WHERE repository_id=? AND ((created_at>=? AND created_at<?) OR (closed_at>=? AND closed_at<?) OR (merged_at>=? AND merged_at<?))",
            (repository_id, lower, upper, lower, upper, lower, upper),
        ).fetchone()[0]
        pull_rows = connection.execute(
            "SELECT created_at,merged_at FROM pulls WHERE repository_id=? AND merged_at>=? AND merged_at<?",
            (repository_id, lower, upper),
        ).fetchall()
        pull_durations = []
        for row in pull_rows:
            opened, merged = parse_github_datetime(row["created_at"]), parse_github_datetime(row["merged_at"])
            if opened is not None and merged is not None and merged >= opened:
                pull_durations.append((merged - opened).total_seconds() / 3600)

        release_observed = connection.execute(
            "SELECT COUNT(*) FROM releases WHERE repository_id=? AND published_at<?", (repository_id, upper)
        ).fetchone()[0]
        release_rows = connection.execute(
            "SELECT published_at FROM releases WHERE repository_id=? AND published_at>=? AND published_at<? AND COALESCE(draft,0)=0 AND COALESCE(prerelease,0)=0",
            (repository_id, iso_z(end - timedelta(days=365)), upper),
        ).fetchall()
        formal_releases = sorted(
            value for row in release_rows if (value := parse_github_datetime(row["published_at"])) is not None
        )
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise AppError(503, "COURSE_TEST_EVENTS_UNAVAILABLE", "历史事件数据无法读取") from exc

    entire_window_exists = created <= start

    def coverage(statuses, observed: int, *, issue=False):
        if any(status in {"missing", "failed", "not_applicable"} for status in statuses):
            state = "partial" if observed else "not_collected"
        elif issue or not entire_window_exists or any(status not in {"complete", "true_zero"} for status in statuses):
            state = "partial"
        else:
            state = "complete"
        return {"coverage": state}

    issue_source = coverage([states["issues"]], issue_observed, issue=True)
    pull_source = coverage([states["pull_requests_created"], states["pull_requests_updated"]], pull_observed)
    release_source = coverage([states["releases"]], release_observed)
    gaps = [(right - left).total_seconds() / 86400 for left, right in zip(formal_releases, formal_releases[1:])]
    insights = {
        "issue_resolution": {
            "median_hours": median(issue_durations) if issue_durations else None,
            "quality": insight_quality(issue_source, len(issue_durations), insufficient=not issue_durations),
        },
        "pr_merges": {
            "median_hours": median(pull_durations) if pull_durations else None,
            "quality": insight_quality(pull_source, len(pull_durations), insufficient=not pull_durations),
        },
        "release_cadence": {
            "median_interval_days": median(gaps) if gaps else None,
            "quality": insight_quality(release_source, len(formal_releases), insufficient=len(formal_releases) < 2),
        },
    }
    return {"window_end": iso_z(end), "insights": insights}


def _event(kind: str, identifier, **values):
    row = {key: None for key in ("event_at", "created_at", "closed_at", "merged_at", "published_at", "updated_at", "author_key", "is_draft", "is_prerelease")}
    row.update(values)
    row.update({"event_type": kind, "source_item_id": str(identifier), "source_task_id": None})
    return row


def _repository_snapshot(session, repository_id: int):
    if session.get(DatasetRepository, (COURSE_DATASET_ID, repository_id)) is None:
        return None
    if session.get(MaintenanceRun, f"course150-v1-{repository_id}") is None:
        return None
    return _snapshot()


def prefer_historical(session, repository_id: int, window_days: int, run) -> bool:
    snapshot = _repository_snapshot(session, repository_id)
    if snapshot is None:
        return False
    _path, manifest = snapshot
    start = parse_github_datetime(manifest.get("window_start"))
    end = parse_github_datetime(manifest.get("window_end"))
    if start is None or end is None:
        raise AppError(503, "COURSE_TEST_EVENTS_UNAVAILABLE", "历史事件缺少有效观察窗口")
    if end - timedelta(days=window_days) < start:
        return False
    return run is None or run.status != "ready" or utc_naive(run.window_end) <= end


def historical_insights(session, repository_id: int, window_days: int, *, start=None, end=None):
    """按历史快照的实际覆盖范围计算指标；用户清除数据后不重新恢复。"""
    snapshot = _repository_snapshot(session, repository_id)
    if snapshot is None:
        return None
    path, manifest = snapshot
    available_start = parse_github_datetime(manifest.get("window_start"))
    available_end = parse_github_datetime(manifest.get("window_end"))
    if available_start is None or available_end is None:
        raise AppError(503, "COURSE_TEST_EVENTS_UNAVAILABLE", "历史事件缺少有效观察窗口")
    end = end or available_end
    start = start or end - timedelta(days=window_days)
    if start < available_start or end > available_end or start >= end:
        return None

    try:
        with sqlite3.connect(f"{path.as_uri()}?mode=ro&immutable=1", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            states = dict(connection.execute("SELECT module,status FROM coverage WHERE repository_id=?", (repository_id,)))
            if set(states) != {"commits", "issues", "pull_requests_created", "pull_requests_updated", "releases"}:
                raise ValueError("历史仓库的模块覆盖记录不完整")
            profile = connection.execute("SELECT created_at FROM repositories WHERE repository_id=?", (repository_id,)).fetchone()
            created = parse_github_datetime(profile["created_at"]) if profile else None
            if created is None:
                raise ValueError("历史仓库缺少创建时间")
            lower, upper = iso_z(start), iso_z(end)
            commit_rows = connection.execute(
                "SELECT sha,event_at,author_key FROM commits WHERE repository_id=? AND event_at>=? AND event_at<?", (repository_id, lower, upper)
            ).fetchall()
            issue_rows = connection.execute(
                "SELECT id,created_at,closed_at,updated_at FROM issues WHERE repository_id=? AND ((created_at>=? AND created_at<?) OR (closed_at>=? AND closed_at<?))",
                (repository_id, lower, upper, lower, upper),
            ).fetchall()
            pull_rows = connection.execute(
                "SELECT id,created_at,closed_at,merged_at,updated_at FROM pulls WHERE repository_id=? AND ((created_at>=? AND created_at<?) OR (closed_at>=? AND closed_at<?) OR (merged_at>=? AND merged_at<?))",
                (repository_id, lower, upper, lower, upper, lower, upper),
            ).fetchall()
            release_rows = connection.execute(
                "SELECT id,published_at,draft,prerelease FROM releases WHERE repository_id=? AND published_at<?", (repository_id, upper)
            ).fetchall()
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise AppError(503, "COURSE_TEST_EVENTS_UNAVAILABLE", "历史事件数据无法读取") from exc

    events = {
        "commits": [_event("commit", row["sha"], event_at=parse_github_datetime(row["event_at"]), author_key=row["author_key"]) for row in commit_rows],
        "issues": [_event("issue", row["id"], event_at=parse_github_datetime(row["closed_at"]), created_at=parse_github_datetime(row["created_at"]), closed_at=parse_github_datetime(row["closed_at"]), updated_at=parse_github_datetime(row["updated_at"])) for row in issue_rows],
        "pulls": [_event("pull_request", row["id"], event_at=parse_github_datetime(row["merged_at"]), created_at=parse_github_datetime(row["created_at"]), closed_at=parse_github_datetime(row["closed_at"]), merged_at=parse_github_datetime(row["merged_at"]), updated_at=parse_github_datetime(row["updated_at"])) for row in pull_rows],
        "releases": [_event("release", row["id"], event_at=parse_github_datetime(row["published_at"]), published_at=parse_github_datetime(row["published_at"]), is_draft=bool(row["draft"]), is_prerelease=bool(row["prerelease"])) for row in release_rows],
    }
    entire_window_exists = created <= start

    def coverage(statuses, *, observed=0, issue=False, interval_start=None):
        if any(status in {"missing", "failed", "not_applicable"} for status in statuses):
            state = "partial" if observed else "not_collected"
        elif issue or not entire_window_exists or any(status not in {"complete", "true_zero"} for status in statuses):
            state = "partial"
        else:
            state = "complete"
        return {"coverage": state, "requested_interval": [iso_z(interval_start or available_start), iso_z(available_end)],
                "observed_records": 0, "rejected_records": 0, "invalid_event_times": 0}

    sources = {
        "commits": coverage([states["commits"]], observed=len(events["commits"])),
        "issues": coverage([states["issues"]], observed=len(events["issues"]), issue=True,
                           interval_start=parse_github_datetime(manifest.get("issue_created_since"))),
        "pulls": coverage([states["pull_requests_created"], states["pull_requests_updated"]], observed=len(events["pulls"])),
        "releases": coverage([states["releases"]], observed=len(events["releases"]), interval_start=end - timedelta(days=365)),
    }
    for module, rows in events.items():
        sources[module]["observed_records"] = len(rows)
    metrics = calculate_insights(events, sources, start, end)
    from backend.app.services.insights import _insight_status, _observed_event_counts
    for metric in metrics.values():
        metric["source_kind"] = "course_test_events_v1"
    return {
        "repository_id": repository_id, "run_id": None, "metric_version": "insights-v1", "status": _insight_status(metrics),
        "window_start": iso_z(start), "window_end": iso_z(end), "timezone": "UTC", "analyzed_at": manifest["source_as_of"],
        "source_task_ids": [], "source_archive_paths": [], "origin": ORIGIN, "sources": sources,
        "insights": metrics, "chart_data": build_chart_data(events, sources, start, end),
        "requested_window_days": window_days, "window_available": True, "available_window_days": 180,
        "window_reason": None, "calculation_basis": ORIGIN, "calculated_at": iso_z(utc_now()),
        "event_source_task_ids": [], "observed_counts": _observed_event_counts(events, start, end),
        "limitations": [
            f"历史快照的观察窗口截至 {iso_z(available_end)}，不代表实时数据。",
            f"Issue 样本只包含 {manifest['issue_created_since']} 起创建的记录，较早创建后关闭的 Issue 可能缺失。",
            "历史事件未保存提交说明、Issue / PR 标题和正文；Commit 账号已匿名化。",
            "提交按采集时默认分支可见历史统计；对象状态来自采集时快照。",
        ],
    }


def historical_commit_activity(session, repository_id: int, *, page: int, per_page: int,
                               search: str | None, week_start, window_days: int | None):
    snapshot = _repository_snapshot(session, repository_id)
    if snapshot is None:
        return None
    path, manifest = snapshot
    end = parse_github_datetime(manifest["window_end"])
    start = end - timedelta(days=window_days or 90)
    lower, upper = start, end
    if week_start is not None:
        week_begin = datetime.combine(week_start, time.min)
        lower, upper = max(start, week_begin), min(end, week_begin + timedelta(days=7))
    try:
        with sqlite3.connect(f"{path.as_uri()}?mode=ro&immutable=1", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            state = connection.execute("SELECT status FROM coverage WHERE repository_id=? AND module='commits'", (repository_id,)).fetchone()
            if state is None:
                raise ValueError("缺少 Commit 覆盖状态")
            profile = connection.execute("SELECT created_at FROM repositories WHERE repository_id=?", (repository_id,)).fetchone()
            created = parse_github_datetime(profile["created_at"]) if profile else None
            if created is None:
                raise ValueError("历史仓库缺少创建时间")
            rows = connection.execute(
                "SELECT sha,event_at,author_key FROM commits WHERE repository_id=? AND event_at>=? AND event_at<? ORDER BY event_at DESC,sha DESC",
                (repository_id, iso_z(lower), iso_z(upper)),
            ).fetchall() if lower < upper else []
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise AppError(503, "COURSE_TEST_EVENTS_UNAVAILABLE", "历史 Commit 记录无法读取") from exc
    repository = session.get(Repository, repository_id)
    if state["status"] in {"missing", "failed", "not_applicable"}:
        return None
    complete = state["status"] in {"complete", "true_zero"} and created <= start
    daily = Counter(row["event_at"][:10] for row in rows)
    author_counts = Counter(row["author_key"] for row in rows if row["author_key"])
    unidentified = sum(not row["author_key"] for row in rows)
    distribution = Counter(author_counts.values())
    text = (search or "").strip().casefold()
    filtered = [row for row in rows if not text or text in row["sha"].casefold() or text in (row["author_key"] or "").casefold()]
    items = [{"sha": row["sha"], "title": "（历史快照未保存提交说明）", "author": row["author_key"] or "未关联账号",
              "is_bot": None, "anonymous": row["author_key"] is None, "date": row["event_at"],
              "url": f"https://github.com/{repository.full_name}/commit/{row['sha']}"}
             for row in filtered[(page - 1) * per_page:page * per_page]]
    return {
        "available": True,
        "coverage": {"state": "complete" if complete else "partial", "label": "历史范围完整" if complete else "历史范围部分覆盖",
                     "detail": "只反映已保存的历史观察窗口"},
        "note": "历史快照保留提交时间和匿名账号，不包含提交说明，账号的 Bot 类型未知。",
        "window_start": iso_z(lower), "window_end": iso_z(upper), "commit_count": len(rows),
        "author_count": len(author_counts), "daily_counts": [{"date": day, "count": count} for day, count in sorted(daily.items())],
        "authors": [{"author": author, "commits": count, "is_bot": None, "anonymous": False}
                    for author, count in sorted(author_counts.items(), key=lambda item: (-item[1], item[0]))[:20]],
        "author_distribution": [{"commits": count, "authors": number} for count, number in sorted(distribution.items())],
        "unidentified_commit_count": unidentified, "items": items, "total": len(filtered),
    }


def historical_records(session, repository_id: int, module: str, *, window_days: int | None = None,
                       search: str | None = None, include_body: bool = False, merged_from=None, merged_to=None):
    snapshot = _repository_snapshot(session, repository_id)
    if snapshot is None:
        return None
    path, manifest = snapshot
    end = parse_github_datetime(manifest["window_end"])
    start = end - timedelta(days=window_days or 90)
    if module not in {"issues", "pulls"}:
        raise ValueError("不支持的历史记录类型")
    try:
        with sqlite3.connect(f"{path.as_uri()}?mode=ro&immutable=1", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            states = dict(connection.execute("SELECT module,status FROM coverage WHERE repository_id=?", (repository_id,)))
            required = ["issues"] if module == "issues" else ["pull_requests_created", "pull_requests_updated"]
            if any(key not in states for key in required):
                raise ValueError("缺少历史记录覆盖状态")
            if any(states[key] in {"missing", "failed", "not_applicable"} for key in required):
                return None
            columns = ("number,created_at,closed_at,comments_count" if module == "issues"
                       else "number,created_at,closed_at,merged_at,draft")
            rows = connection.execute(
                f"SELECT {columns} FROM {module} WHERE repository_id=? AND closed_at>=? AND closed_at<? ORDER BY closed_at DESC,number DESC",
                (repository_id, iso_z(start), iso_z(end)),
            ).fetchall()
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise AppError(503, "COURSE_TEST_EVENTS_UNAVAILABLE", "历史 Issue / PR 记录无法读取") from exc

    repository = session.get(Repository, repository_id)
    normalized_search = (search or "").strip().casefold()
    items = []
    for row in rows:
        if normalized_search and normalized_search not in str(row["number"]) and normalized_search not in "（历史快照未保存标题）":
            continue
        created, closed = parse_github_datetime(row["created_at"]), parse_github_datetime(row["closed_at"])
        if module == "issues":
            elapsed = (closed - created).total_seconds() / 86400 if created and closed and closed >= created else None
            item = {"number": row["number"], "title": "（历史快照未保存标题）", "created_at": row["created_at"],
                    "closed_at": row["closed_at"], "duration_days": round(elapsed, 1) if elapsed is not None else None,
                    "state": "closed", "url": f"https://github.com/{repository.full_name}/issues/{row['number']}"}
            if include_body:
                item.update({"body": None, "comments_count": row["comments_count"]})
        else:
            merged = parse_github_datetime(row["merged_at"])
            if merged_from or merged_to:
                lower = merged_from.replace(tzinfo=None) if merged_from else None
                upper = merged_to.replace(tzinfo=None) if merged_to else None
                if merged is None or created is None or merged < created or (lower and merged < lower) or (upper and merged >= upper):
                    continue
            elapsed = (merged - created).total_seconds() / 86400 if created and merged and merged >= created else None
            item = {"number": row["number"], "title": "（历史快照未保存标题）", "created_at": row["created_at"],
                    "closed_at": row["closed_at"], "merged_at": row["merged_at"],
                    "duration_days": round(elapsed, 1) if elapsed is not None else None,
                    "state": "merged" if merged else "closed", "draft": bool(row["draft"]), "comments_count": None,
                    "url": f"https://github.com/{repository.full_name}/pull/{row['number']}"}
            if include_body:
                item["body"] = None
        items.append(item)
    note = ("历史快照只包含采集起点之后创建的 Issue，较早创建后关闭的记录可能缺失；标题和正文未保存。"
            if module == "issues" else
            "历史快照的关闭未合并 PR 可能不完整；标题、正文和评论数未保存。")
    return {"available": True, "coverage": {"state": "partial", "label": "历史样本", "detail": note},
            "note": note, "window_start": iso_z(start), "window_end": iso_z(end), "items": items}


def historical_release_detail(session, repository_id: int, release_id: int):
    snapshot = _repository_snapshot(session, repository_id)
    if snapshot is None:
        return None
    path, _manifest = snapshot
    try:
        with sqlite3.connect(f"{path.as_uri()}?mode=ro&immutable=1", uri=True) as connection:
            release = connection.execute("SELECT name FROM releases WHERE repository_id=? AND id=?", (repository_id, release_id)).fetchone()
    except (OSError, sqlite3.Error) as exc:
        raise AppError(503, "COURSE_TEST_EVENTS_UNAVAILABLE", "历史 Release 记录无法读取") from exc
    return {"id": str(release_id), "name": release[0], "body": None} if release else None
