#!/usr/bin/env python3
"""Build a small, redacted 300-repository course research snapshot bundle."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from scripts.course_split import (
    DEFAULT_PROFILES,
    DEFAULT_SOURCE,
    EXPECTED_SOURCE_SHA256,
    load_languages,
    load_weekly,
    sha256_file,
    validate_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPLIT = ROOT / "ml/course/splits/repositories-150-150-v1.json"
DEFAULT_OUTPUT = ROOT / "data/datasets/course-research-300-v1"
EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
CREDENTIAL = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+[A-Za-z0-9._-]{20,})", re.IGNORECASE)


def sha256(path: Path) -> str:
    return sha256_file(path)


def redact(value):
    if isinstance(value, str):
        return CREDENTIAL.sub("[已移除凭据]", EMAIL.sub("[已移除邮箱]", value))
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def read_profiles(path: Path) -> dict[str, dict]:
    result = {}
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            repository_id = str(int(row["repository_id"]))
            if repository_id in result:
                raise ValueError(f"duplicate profile repository_id: {repository_id}")
            result[repository_id] = row
    return result


def canonical_gzip_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as compressed:
            compressed.write((json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode())


def write_json(path: Path, value) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n")


def build_bundle(source: Path, profiles_path: Path, split_path: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing bundle: {output}")
    source_hash = sha256(source)
    if source_hash != EXPECTED_SOURCE_SHA256:
        raise ValueError(f"weekly feature source SHA-256 mismatch: {source_hash}")
    profile_hash = sha256(profiles_path)
    split_hash = sha256(split_path)
    manifest = json.loads(split_path.read_text(encoding="utf-8"))
    grouped = load_weekly(source)
    validate_manifest(manifest, list(grouped))
    profiles = read_profiles(profiles_path)
    if set(profiles) != set(grouped):
        raise ValueError("profile and weekly feature repository IDs differ")
    languages = load_languages(profiles_path)
    train_ids, test_ids = set(manifest["train_repository_ids"]), set(manifest["test_repository_ids"])

    repositories = []
    weekly_records = []
    snapshot_times = []
    for repository_id, all_weeks in grouped.items():
        profile = profiles[repository_id]
        if profile.get("snapshot_at"):
            snapshot_times.append(profile["snapshot_at"])
        row_role = "train" if repository_id in train_ids else "test"
        repositories.append({
            "repository_id": int(repository_id),
            "full_name": redact(profile.get("full_name_at_capture")),
            "html_url": f"https://github.com/{profile.get('full_name_at_capture', '')}",
            "description": redact(profile.get("description")),
            "language": languages[repository_id],
            "topics": redact(profile.get("topics") if isinstance(profile.get("topics"), list) else []),
            "license_spdx": profile.get("license_spdx"),
            "created_at": profile.get("created_at"),
            "pushed_at": profile.get("pushed_at"),
            "github_updated_at": profile.get("updated_at"),
            "archived": bool(profile.get("archived")),
            "is_fork": bool(profile.get("is_fork")),
            "size_kb": profile.get("size") if type(profile.get("size")) is int else None,
            "stars": profile.get("stargazers_count") if type(profile.get("stargazers_count")) is int else None,
            "forks": profile.get("forks_count") if type(profile.get("forks_count")) is int else None,
            "snapshot_at": profile.get("snapshot_at"),
            "fetched_at": profile.get("fetched_at"),
            "http_status": profile.get("http_status"),
            "response_etag": profile.get("response_etag"),
            "sample_role": row_role,
        })
        for week in all_weeks[-12:]:
            weekly_records.append({
                "repository_id": int(repository_id),
                "sample_role": row_role,
                "week_start_utc": week["period_start"],
                "week_end_exclusive_utc": week["period_end"],
                "commits": int(week["commits_observed"]) if week.get("commits_observed") not in (None, "") else None,
                "commit_coverage": week["commit_coverage"],
                "prs_opened": int(week["pr_opened"]) if week.get("pr_opened") not in (None, "") else None,
                "pr_opened_coverage": week["pr_opened_coverage"],
                "prs_merged": int(week["pr_merged"]) if week.get("pr_merged") not in (None, "") else None,
                "pr_merged_coverage": week["pr_merged_coverage"],
                "data_coverage": week["data_coverage"],
            })

    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    canonical_gzip_json(output / "repositories.json.gz", repositories)
    canonical_gzip_json(output / "weekly_features.json.gz", weekly_records)
    with (output / "split_manifest.json").open("xb") as stream:
        stream.write(split_path.read_bytes())
    observation_start = min(row["week_start_utc"] for row in weekly_records)
    observation_end = max(row["week_end_exclusive_utc"] for row in weekly_records)
    metadata = {
        "schema_version": 1,
        "dataset_id": "course-research-300-v1",
        "version": "course-research-300-v1",
        "dataset_name": "300 仓库课程研究样本（历史快照）",
        "source_dataset_id": manifest["dataset_id"],
        "source_sha256": source_hash,
        "profiles_sha256": profile_hash,
        "split_manifest_sha256": split_hash,
        "split_version": manifest["split_version"],
        "split_seed": manifest["seed"],
        "generated_at": datetime.now().astimezone().isoformat(),
        "data_as_of": max(snapshot_times) if snapshot_times else observation_end,
        "observation_window": {"start": observation_start, "end_exclusive": observation_end, "weeks": 12},
        "total_repositories": len(repositories),
        "weekly_records": len(weekly_records),
        "repositories_with_12_complete_commit_weeks": sum(
            all(row["commit_coverage"] in {"complete", "true_zero"}
                for row in weekly_records if row["repository_id"] == repository["repository_id"])
            for repository in repositories
        ),
        "split_counts": {"train": len(train_ids), "test": len(test_ids)},
        "coverage": {
            "commit_week_complete_or_true_zero": sum(row["commit_coverage"] in {"complete", "true_zero"} for row in weekly_records),
            "commit_week_partial": sum(row["commit_coverage"] == "partial" for row in weekly_records),
            "commit_week_failed": sum(row["commit_coverage"] == "failed" for row in weekly_records),
            "pr_opened_week_complete_or_true_zero": sum(row["pr_opened_coverage"] in {"complete", "true_zero"} for row in weekly_records),
            "pr_merged_week_complete_or_true_zero": sum(row["pr_merged_coverage"] in {"complete", "true_zero"} for row in weekly_records),
            "pr_merged_week_partial_concurrent_change": sum(row["pr_merged_coverage"] == "partial_concurrent_change" for row in weekly_records),
            "commits_in_complete_or_true_zero_weeks": sum(
                row["commits"] or 0 for row in weekly_records if row["commit_coverage"] in {"complete", "true_zero"}),
            "prs_opened_in_complete_or_true_zero_weeks": sum(
                row["prs_opened"] or 0 for row in weekly_records if row["pr_opened_coverage"] in {"complete", "true_zero"}),
            "prs_merged_in_complete_or_true_zero_weeks": sum(
                row["prs_merged"] or 0 for row in weekly_records if row["pr_merged_coverage"] in {"complete", "true_zero"}),
        },
        "source": "本地 repo-evaluation-2026-v1 聚合数据；不重新访问 GitHub",
        "quality": "partial",
        "limitations": [
            "仓库来自既有课程研究样本，不是 GitHub 全体仓库的随机样本。",
            "提交周统计反映采集时默认分支可见历史，不是精确历史分支快照。",
            "partial、failed、not_applicable 与 true_zero 状态保持区分；缺失记录不解释为零。",
            "150/150 是同一历史数据集上的重新分组回测，不是全新外部或前瞻性验证。",
            "周级聚合数据不包含 issue / PR 正文、原始事件、checkpoint、token 或续采日志。",
        ],
    }
    write_json(output / "dataset.json", metadata)
    (output / "README.md").write_text(
        "# 300 仓库课程研究样本\n\n"
        "该包提供 300 个仓库的最近 12 个完整 UTC 周聚合、仓库资料和 150/150 固定样本角色。"
        "它是课程历史快照，不代表 GitHub 总体，也不是实时数据。\n",
        encoding="utf-8",
    )
    (output / "DATA_NOTICE.md").write_text(
        "只用于 RepoVantage 课程研究和演示。Commit、PR 周聚合保留原始覆盖状态。"
        "没有完整覆盖的指标不得补成真实零；在线新采集数据优先于本快照。\n",
        encoding="utf-8",
    )
    files = sorted(path for path in output.rglob("*") if path.is_file())
    checksum_lines = [f"{sha256(path)}  {path.relative_to(output).as_posix()}" for path in files]
    (output / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="ascii")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    parser.add_argument("--split-manifest", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    metadata = build_bundle(args.source, args.profiles, args.split_manifest, args.output)
    total_bytes = sum(path.stat().st_size for path in args.output.rglob("*") if path.is_file())
    if total_bytes > 256 * 1024 * 1024:
        raise ValueError(f"bundle exceeds 256 MiB: {total_bytes}")
    print(json.dumps({"bundle": str(args.output), "dataset_id": metadata["dataset_id"],
                      "repositories": metadata["total_repositories"], "weekly_records": metadata["weekly_records"],
                      "size_bytes": total_bytes}, ensure_ascii=False))


if __name__ == "__main__":
    main()
