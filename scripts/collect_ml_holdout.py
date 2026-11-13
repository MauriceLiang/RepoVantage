#!/usr/bin/env python3
"""冻结未参与历史实验的仓库名单，并增量采集 Commit 独立复核数据。"""
import argparse
import gzip
import hashlib
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from backend.app.core.clock import iso_z, parse_github_datetime, utc_now
from backend.app.core.exceptions import AppError
from backend.app.integrations.github.client import GitHubClient
from scripts.repair_issue_comments import atomic_json


SEED = 20261109
ORIGIN = datetime(2026, 10, 5)
START = ORIGIN - timedelta(weeks=12)
END = ORIGIN + timedelta(weeks=4)


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def freeze(reserves, coverage, output, per_group):
    if output.exists() or per_group < 1:
        raise ValueError("清单必须是新文件，且每组数量为正")
    source = json.loads(reserves.read_text(encoding="utf-8"))["reserves"]
    with gzip.open(coverage, "rt", encoding="utf-8") as stream:
        existing = {json.loads(line)["repository_id"] for line in stream}
    selected, used = [], set(existing)
    for group, rows in sorted(source.items()):
        candidates = [row for row in rows if type(row.get("repository_id")) is int and row["repository_id"] not in existing]
        candidates.sort(key=lambda row: hashlib.sha256(f"{SEED}:{group}:{row['repository_id']}".encode()).hexdigest())
        chosen = []
        for row in candidates:
            if row["repository_id"] not in used:
                chosen.append({"repository_id": row["repository_id"], "selected_full_name": row["full_name"], "stratum": group})
                used.add(row["repository_id"])
            if len(chosen) == per_group:
                break
        if len(chosen) != per_group:
            raise ValueError(f"候选仓库不足：{group}")
        selected.extend(chosen)
    payload = {"version": "commit-unseen-holdout-v1", "seed": SEED, "origin": iso_z(ORIGIN), "history_start": iso_z(START),
               "target_end_exclusive": iso_z(END), "repositories": selected,
               "source_sha256": {str(reserves): digest(reserves), str(coverage): digest(coverage)},
               "selection": "每个原始语言/Star 分层按固定哈希选择，排除此前 300 个仓库；不可根据回测结果替换。",
               "predeclared_model": "s1-20261109-v1/activity/commit/research_model.joblib",
               "predeclared_baselines": ["last_4_weeks", "last_12_week_mean"],
               "gate": "至少30个完整仓库、至少15个历史非零仓库；相对两个基线均改善至少5%，逐仓库配对bootstrap区间下界大于0，且每个至少10仓库的规模层退化不超过5%。仍需解决默认分支历史成员关系。"}
    atomic_json(output, payload)


def collect_repo(github, candidate, max_pages):
    repository_id = candidate["repository_id"]
    profile, _, _ = github.get_repository_by_id(repository_id)
    if not profile or profile.get("id") != repository_id:
        raise AppError(502, "GITHUB_UPSTREAM_ERROR", "仓库身份不一致")
    raw_created = profile.get("created_at")
    created = parse_github_datetime(raw_created) if isinstance(raw_created, str) else None
    if not created or profile.get("private") is not False or not profile.get("default_branch"):
        return {**candidate, "status": "not_applicable", "reason": "仓库不可公开访问或缺少建仓/默认分支信息"}
    if created > START:
        return {**candidate, "status": "not_applicable", "reason": "预测时点前不足 12 个完整周"}
    branch = profile["default_branch"]
    params = {"since": iso_z(START), "until": iso_z(END), "sha": branch}
    pages = []

    def page_observer(page):
        pages.append({"page": page.page_index, "request_url": page.request_url, "next_url": page.next_url,
                      "http_status": page.http_status, "observed_count": len(page.records), "has_next": page.has_next,
                      "first_page_shas": [item.get("sha") for item in page.records] if page.page_index == 1 else None})

    path = f"/repositories/{repository_id}/commits"
    result = github.list_paginated_detailed(path, params, on_page=page_observer, max_pages=max_pages, collect_raw_pages=False)
    errors = []
    if not result.complete or result.error_code:
        errors.append("pagination_incomplete")
    if pages and pages[-1]["observed_count"] == 100 and not pages[-1]["has_next"]:
        errors.append("full_terminal_page_unverified")
    events, seen = [], set()
    for item in result.items:
        commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
        committer = commit.get("committer") if isinstance(commit.get("committer"), dict) else {}
        author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
        committer_value, author_value = committer.get("date"), author.get("date")
        timestamp = parse_github_datetime(committer_value) if isinstance(committer_value, str) else None
        if timestamp is None and isinstance(author_value, str):
            timestamp = parse_github_datetime(author_value)
        sha = item.get("sha")
        if not isinstance(sha, str) or not sha or not timestamp or sha in seen:
            errors.append("invalid_or_duplicate_commit")
            continue
        seen.add(sha)
        if START <= timestamp < END:
            events.append({"sha": sha, "event_at": iso_z(timestamp), "committer_date": committer_value, "author_date": author_value})
    first_shas = pages[0]["first_page_shas"] if pages else []
    pagination_error = result.error_code
    if pagination_error != "GITHUB_RATE_LIMITED":
        head = github.list_paginated_detailed(path, params, max_pages=1, collect_raw_pages=False)
        if head.error_code or [item.get("sha") for item in head.items] != first_shas:
            errors.append("head_changed_or_unavailable")
        if head.error_code == "GITHUB_RATE_LIMITED":
            pagination_error = head.error_code
    try:
        profile_after, _, _ = github.get_repository_by_id(repository_id) if pagination_error != "GITHUB_RATE_LIMITED" else ({}, 0, None)
    except AppError as exc:
        profile_after = {}
        if exc.code == "GITHUB_RATE_LIMITED":
            pagination_error = exc.code
    if profile_after.get("default_branch") != branch:
        errors.append("default_branch_changed_or_unavailable")
    events.sort(key=lambda item: (item["event_at"], item["sha"]))
    weekly = [0] * 16
    for event in events:
        index = (parse_github_datetime(event["event_at"]) - START).days // 7
        weekly[index] += 1
    return {**candidate, "full_name_at_capture": profile.get("full_name"), "default_branch_at_capture": branch,
            "captured_at": iso_z(utc_now()), "status": "complete_current_snapshot" if not errors else "coverage_uncertain",
            "coverage_reasons": sorted(set(errors)), "pagination_error": pagination_error,
            "pages": pages, "weekly_commits": weekly, "events": events,
            "limitations": ["按采集时默认分支可见提交重建；不能证明提交在历史预测时点已进入默认分支。"]}


def collect(manifest_path, output, max_pages, delay):
    if max_pages < 1 or delay < 0:
        raise ValueError("分页预算必须为正，延迟不能为负")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fingerprint = digest(manifest_path)
    output.mkdir(parents=True, exist_ok=True)
    metadata = output / "manifest.json"
    if metadata.exists() and json.loads(metadata.read_text(encoding="utf-8")).get("input_sha256") != fingerprint:
        raise ValueError("输出目录属于不同的冻结清单")
    if not metadata.exists():
        atomic_json(metadata, {"input_sha256": fingerprint, "repository_count": len(manifest["repositories"]), "max_pages": max_pages})
    with GitHubClient(on_response=lambda _response: time.sleep(delay) if delay else None) as github:
        for candidate in manifest["repositories"]:
            path = output / "repositories" / f"{candidate['repository_id']}.json"
            if path.exists() and json.loads(path.read_text(encoding="utf-8")).get("status") in {"complete_current_snapshot", "not_applicable"}:
                continue
            try:
                record = collect_repo(github, candidate, max_pages)
                atomic_json(path, record)
                print(f"{candidate['selected_full_name']}: {record['status']}", flush=True)
                if record.get("pagination_error") == "GITHUB_RATE_LIMITED":
                    raise SystemExit("GitHub 限流；已保存断点，请稍后重试。")
            except AppError as exc:
                atomic_json(path, {**candidate, "status": "coverage_uncertain", "error_code": exc.code})
                if exc.code == "GITHUB_RATE_LIMITED":
                    raise SystemExit("GitHub 限流；已保存断点，请稍后重试。") from exc
                print(f"{candidate['selected_full_name']}: {exc.code}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("freeze")
    prepare.add_argument("--reserves", type=Path, required=True)
    prepare.add_argument("--coverage", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--per-group", type=int, default=3)
    run = commands.add_parser("collect")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--max-pages", type=int, default=10)
    run.add_argument("--delay-seconds", type=float, default=0.5)
    args = parser.parse_args()
    if args.command == "freeze":
        freeze(args.reserves, args.coverage, args.output, args.per_group)
    else:
        collect(args.manifest, args.output, args.max_pages, args.delay_seconds)


if __name__ == "__main__":
    main()
