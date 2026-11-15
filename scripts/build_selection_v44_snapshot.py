"""Build a deterministic v4.4 metric snapshot from the frozen featured-v1 bundle."""
from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CANDIDATES = DATA / "manifests/selection-v44-candidates.json"
FEATURED = DATA / "datasets/featured-v1"
OUTPUT = DATA / "manifests/selection-v44-historical-1.json"
QUALITY = ROOT / "docs/research-v44/selection-v44-quality.json"
SOURCE_DATASET = "featured-v1"
METHODOLOGY = "selection-metrics-v1"
CUTOFF = datetime.fromisoformat("2026-10-22T08:32:31+00:00")
WEEK_START = datetime.fromisoformat("2026-07-27T00:00:00+00:00")
WEEK_END = datetime.fromisoformat("2026-10-19T00:00:00+00:00")
RELEASE_START = CUTOFF - timedelta(days=365)


def parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc)


def rows(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def metric(key: str, value: float | None, unit: str, sample_count: int | None,
           start: datetime, end: datetime, coverage: str, note: str | None = None) -> dict:
    return {
        "metric_key": key,
        "value": value,
        "unit": unit,
        "sample_count": sample_count,
        "window_start": start.isoformat().replace("+00:00", "Z"),
        "window_end_exclusive": end.isoformat().replace("+00:00", "Z"),
        "data_cutoff_at": CUTOFF.isoformat().replace("+00:00", "Z"),
        "source_dataset_id": SOURCE_DATASET,
        "coverage_status": coverage,
        "coverage_ratio": 1.0 if coverage in {"complete", "true_zero"} else 0.0,
        "methodology_version": METHODOLOGY,
        "notes": note,
    }


def main() -> None:
    policy = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    selected = [item for item in policy["repositories"] if item["disposition"] == "compare"]
    if len(selected) != 11:
        raise SystemExit(f"expected 11 baseline comparison repositories, found {len(selected)}")

    checksums = {}
    for line in (FEATURED / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        checksum, relative = line.split("  ", 1)
        checksums[relative] = checksum
    for relative, expected in checksums.items():
        actual = digest(FEATURED / relative)
        if actual != expected:
            raise SystemExit(f"featured-v1 checksum mismatch: {relative}")

    coverage_by_id = {int(item["repository_id"]): item for item in rows(FEATURED / "coverage.jsonl.gz")}
    event_groups: dict[str, dict[int, list[dict]]] = {}
    files = {"commits": "commits", "issues": "issues", "pulls": "pulls", "releases": "releases"}
    for event_type, filename in files.items():
        grouped: dict[int, list[dict]] = defaultdict(list)
        for item in rows(FEATURED / f"events/{filename}.jsonl.gz"):
            grouped[int(item["repository_id"])].append(item)
        event_groups[event_type] = grouped

    metric_records: list[dict] = []
    candidate_quality: list[dict] = []
    weekly_activity: list[dict] = []
    status_totals: Counter[str] = Counter()
    for candidate in selected:
        repo_id = int(candidate["github_repository_id"])
        source = coverage_by_id.get(repo_id)
        if source is None:
            raise SystemExit(f"featured-v1 coverage missing for {candidate['full_name']}")
        source_start, source_end = parse(source.get("window_start")), parse(source.get("window_end"))
        modules = source.get("modules", {})
        contained = bool(source_start and source_end and source_start <= WEEK_START and WEEK_END <= source_end)

        def state(module: str, start: datetime, end: datetime) -> str:
            coverage = modules.get(module, "not_collected")
            if coverage == "complete" and (module == "releases" or contained):
                return "complete"
            if coverage in {"partial", "budget_exhausted", "deferred", "unavailable"}:
                return "partial" if event_groups.get(module, {}).get(repo_id) else "failed"
            return "not_collected"

        commits = event_groups["commits"].get(repo_id, [])
        commit_weeks = [0] * 12
        for item in commits:
            event_at = parse(item.get("event_at"))
            if event_at and WEEK_START <= event_at < WEEK_END:
                commit_weeks[(event_at - WEEK_START).days // 7] += 1
        commit_count = sum(commit_weeks)
        commit_state = state("commits", WEEK_START, WEEK_END)
        metric_records.append({"repository_id": repo_id, **metric(
            "weekly_commit_mean", commit_count / 12 if commit_state == "complete" else None,
            "commits/week", 12 if commit_state == "complete" else None,
            WEEK_START, WEEK_END, "true_zero" if commit_state == "complete" and commit_count == 0 else commit_state,
            "12 个完整 UTC 周的 Commit 总数除以 12；提交量不代表质量。",
        )})

        pulls = event_groups["pulls"].get(repo_id, [])
        pr_weeks = [0] * 12
        for item in pulls:
            created = parse(item.get("created_at"))
            if created and WEEK_START <= created < WEEK_END:
                pr_weeks[(created - WEEK_START).days // 7] += 1
        pr_count = sum(pr_weeks)
        pr_state = state("pulls", WEEK_START, WEEK_END)
        metric_records.append({"repository_id": repo_id, **metric(
            "weekly_pr_open_mean", pr_count / 12 if pr_state == "complete" else None,
            "pull_requests/week", 12 if pr_state == "complete" else None,
            WEEK_START, WEEK_END, "true_zero" if pr_state == "complete" and pr_count == 0 else pr_state,
            "12 个完整 UTC 周内创建的 PR 总数除以 12；协作活动观察指标。",
        )})

        issues = event_groups["issues"].get(repo_id, [])
        issue_days = []
        for item in issues:
            closed, created = parse(item.get("closed_at")), parse(item.get("created_at"))
            if closed and created and WEEK_START <= closed < WEEK_END and closed >= created:
                issue_days.append((closed - created).total_seconds() / 86400)
        issue_state = state("issues", WEEK_START, WEEK_END)
        issue_value = median(issue_days) if issue_state == "complete" and len(issue_days) >= 5 else None
        metric_records.append({"repository_id": repo_id, **metric(
            "issue_closed_median_days", issue_value, "days", len(issue_days),
            WEEK_START, WEEK_END, "true_zero" if issue_state == "complete" and not issue_days else issue_state,
            "n<5 不给出中位数；5≤n<10 仅供探索，n≥10 才满足描述性比较门槛。",
        )})

        pr_days = []
        for item in pulls:
            merged, created = parse(item.get("merged_at")), parse(item.get("created_at"))
            if merged and created and WEEK_START <= merged < WEEK_END and merged >= created:
                pr_days.append((merged - created).total_seconds() / 86400)
        pr_merge_state = state("pulls", WEEK_START, WEEK_END)
        pr_value = median(pr_days) if pr_merge_state == "complete" and len(pr_days) >= 5 else None
        metric_records.append({"repository_id": repo_id, **metric(
            "pr_merged_median_days", pr_value, "days", len(pr_days),
            WEEK_START, WEEK_END, "true_zero" if pr_merge_state == "complete" and not pr_days else pr_merge_state,
            "n<5 不给出中位数；5≤n<10 仅供探索，n≥10 才满足描述性比较门槛。",
        )})

        release_rows = [
            parse(item.get("published_at")) for item in event_groups["releases"].get(repo_id, [])
            if item.get("is_draft") is False and item.get("is_prerelease") is False
        ]
        release_dates = sorted(value for value in release_rows if value and RELEASE_START <= value < CUTOFF)
        release_gaps = [(right - left).total_seconds() / 86400 for left, right in zip(release_dates, release_dates[1:])]
        release_state = state("releases", RELEASE_START, CUTOFF)
        metric_records.append({"repository_id": repo_id, **metric(
            "release_interval_median_days", median(release_gaps) if release_state == "complete" and release_gaps else None,
            "days", len(release_gaps), RELEASE_START, CUTOFF,
            "true_zero" if release_state == "complete" and not release_gaps else release_state,
            "365 天正式 Release 相邻间隔；不设置优劣方向，也不计入综合分。",
        )})
        candidate_quality.append({"repository_id": repo_id, "full_name": candidate["full_name"],
                                  "source_coverage": modules, "source_window_start": source.get("window_start"),
                                  "source_window_end": source.get("window_end"), "full_12_week_window_contained": contained})
        weekly_activity.append({
            "repository_id": repo_id,
            "weeks": [{
                "week_start": (WEEK_START + timedelta(weeks=index)).isoformat().replace("+00:00", "Z"),
                "commits": commit_weeks[index],
                "prs_opened": pr_weeks[index],
            } for index in range(12)],
        })

    for record in metric_records:
        status_totals[record["coverage_status"]] += 1
    body = {
        "schema_version": 1,
        "snapshot_version": "selection-v44-historical-1",
        "metric_policy": METHODOLOGY,
        "source_dataset": SOURCE_DATASET,
        "source_dataset_id": "featured-default",
        "source_quality_report": "data/manifests/featured-v1-quality-report.json",
        "source_sha256": {"checksum_manifest": digest(FEATURED / "SHA256SUMS"),
                          **{name: digest(FEATURED / f"events/{filename}.jsonl.gz") for name, filename in files.items()}},
        "as_of": CUTOFF.isoformat().replace("+00:00", "Z"),
        "activity_window": {"start": WEEK_START.isoformat().replace("+00:00", "Z"),
                            "end_exclusive": WEEK_END.isoformat().replace("+00:00", "Z"), "weeks": 12},
        "release_window": {"start": RELEASE_START.isoformat().replace("+00:00", "Z"),
                           "end_exclusive": CUTOFF.isoformat().replace("+00:00", "Z"), "days": 365},
        "metric_count": len(metric_records),
        "repository_count": len(selected),
        "metrics": metric_records,
        "weekly_activity": weekly_activity,
        "repository_coverage": candidate_quality,
        "http_requests": 0,
        "limitations": [
            "冻结精选案例样本，不代表 GitHub 随机样本或完整历史。",
            "窗口指标描述可观测活动，不代表代码质量、性能、安全或技术适用性。",
            "候选新增仓库尚无同一截止时间数据，保持待采集。",
        ],
    }
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    body["immutable_fingerprint"] = hashlib.sha256(canonical).hexdigest()
    OUTPUT.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    candidate_policy = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    all_statuses = ("complete", "partial", "failed", "not_collected", "true_zero")
    methods = {
        "weekly_commit_mean": "12 个完整 UTC 周内 Commit 总数除以 12。",
        "weekly_pr_open_mean": "12 个完整 UTC 周内新建 PR 总数除以 12。",
        "issue_closed_median_days": "观察窗口内已关闭 Issue 的 closed_at-created_at 中位数，n<5 时不输出数值。",
        "pr_merged_median_days": "观察窗口内已合并 PR 的 merged_at-created_at 中位数，n<5 时不输出数值。",
        "release_interval_median_days": "单独 365 天窗口内正式 Release 的相邻间隔中位数；不设方向。",
    }
    metrics_by_key: dict[str, list[dict]] = defaultdict(list)
    for record in metric_records:
        metrics_by_key[record["metric_key"]].append(record)
    metric_quality = {}
    for metric_key, records in metrics_by_key.items():
        sample_counts = [record["sample_count"] for record in records if record["sample_count"] is not None]
        state_counts = Counter(record["coverage_status"] for record in records)
        first = records[0]
        metric_quality[metric_key] = {
            "unit": first["unit"],
            "window_start": first["window_start"],
            "window_end_exclusive": first["window_end_exclusive"],
            "window_days": (parse(first["window_end_exclusive"]) - parse(first["window_start"])).days,
            "method": methods[metric_key],
            "repository_count": len(records),
            "value_count": sum(record["value"] is not None for record in records),
            "null_value_count": sum(record["value"] is None for record in records),
            "sample_count_min": min(sample_counts) if sample_counts else None,
            "sample_count_max": max(sample_counts) if sample_counts else None,
            "coverage_status_counts": {status: state_counts.get(status, 0) for status in all_statuses},
        }

    snapshot_by_repo = defaultdict(list)
    for record in metric_records:
        snapshot_by_repo[record["repository_id"]].append(record)
    selection_groups = []
    for scenario in candidate_policy["scenarios"]:
        group = [item for item in candidate_policy["repositories"] if item.get("scenario") == scenario["slug"]]
        compared = [item for item in group if item["disposition"] == "compare"]
        pending = [item for item in group if item["disposition"] == "supplement"]
        ready_ids = []
        for item in compared:
            records = {record["metric_key"]: record for record in snapshot_by_repo.get(int(item["github_repository_id"]), [])}
            if all(key in records and records[key]["value"] is not None and records[key]["coverage_status"] == "complete"
                   for key in methods):
                ready_ids.append(int(item["github_repository_id"]))
        selection_groups.append({
            "scenario": scenario["slug"],
            "candidate_count": len(group),
            "compare_repository_ids": [int(item["github_repository_id"]) for item in compared],
            "metrics_ready_repository_ids": ready_ids,
            "historical_snapshot_not_fully_comparable_repository_ids": [
                int(item["github_repository_id"]) for item in compared
                if int(item["github_repository_id"]) not in ready_ids
            ],
            "pending_collection_repository_ids": [int(item["github_repository_id"]) for item in pending],
        })

    quality = {
        "schema_version": 1,
        "snapshot_version": body["snapshot_version"],
        "source": SOURCE_DATASET,
        "as_of": body["as_of"],
        "selected_repositories": 11,
        "formal_comparison_candidates": 14,
        "supplement_repositories_pending": 3,
        "reference_repositories": 4,
        "baseline_repositories_reused": 15,
        "historical_comparison_candidates_reused": 11,
        "reference_candidates_reused": 4,
        "new_repository_profiles_added_without_metrics": 3,
        "new_repositories_collected": 0,
        "duplicate_github_ids": 0,
        "http_requests": 0,
        "metrics_by_coverage_status": {status: status_totals.get(status, 0) for status in all_statuses},
        "metrics_by_key": metric_quality,
        "selection_groups": selection_groups,
        "metric_thresholds": {"duration_n_lt_5": "insufficient_evidence", "duration_n_5_to_9": "exploratory", "duration_n_ge_10": "descriptive_comparison"},
        "repositories": candidate_quality,
        "fingerprint": body["immutable_fingerprint"],
        "quality_report_path": str(OUTPUT.relative_to(ROOT)),
    }
    QUALITY.parent.mkdir(parents=True, exist_ok=True)
    QUALITY.write_text(json.dumps(quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT.relative_to(ROOT)), "metrics": len(metric_records),
                      "statuses": dict(sorted(status_totals.items())), "fingerprint": body["immutable_fingerprint"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
