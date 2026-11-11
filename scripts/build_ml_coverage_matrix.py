#!/usr/bin/env python3
"""按仓库及来源模块构建研究数据覆盖矩阵，不把缺失转换为零。"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


MODULES = ("profile", "pull_requests_created", "pull_requests_updated", "commits", "issues", "issue_comments", "releases", "tags")
ALLOWED = {"complete", "true_zero"}


def build_matrix(coverage_rows, issue_audit):
    groups = {}
    for row in coverage_rows:
        repository_id, module = row["repository_id"], row["module"]
        if module not in MODULES:
            raise ValueError(f"unknown module: {module}")
        item = groups.setdefault(repository_id, {"repository_id": repository_id, "repository": row["selected_full_name"]})
        if item["repository"] != row["selected_full_name"] or module in item:
            raise ValueError(f"duplicate or conflicting module coverage: {repository_id}/{module}")
        item[module] = row["status"]
    uncertain = {item["repository_id"] for item in issue_audit["affected_repositories"]}
    uncertain.update(item["repository_id"] for item in issue_audit["repositories_with_full_terminal_page_at_300_or_more"])
    result = []
    for repository_id, item in sorted(groups.items()):
        missing = set(MODULES) - item.keys()
        if missing:
            raise ValueError(f"missing module coverage for {repository_id}: {sorted(missing)}")
        item["ml01_source_usable"] = item["commits"] in ALLOWED
        item["ml02_source_usable"] = item["pull_requests_created"] in ALLOWED
        item["ml03_sources_usable"] = item["ml01_source_usable"] and item["ml02_source_usable"]
        item["issue_comment_audit"] = "coverage_uncertain" if repository_id in uncertain else "not_independently_certified"
        item["release_source_usable"] = item["releases"] in ALLOWED
        result.append(item)
    return result


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--issue-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.manifest.exists():
        raise FileExistsError("请选择新的输出文件，避免覆盖历史数据")
    with gzip.open(args.coverage, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    result = build_matrix(rows, json.loads(args.issue_audit.read_text(encoding="utf-8")))
    import pyarrow as pa
    import pyarrow.parquet as pq

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(result), args.output, compression="zstd")
    canonical = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    args.manifest.write_text(json.dumps({"version": "coverage-matrix-v1", "rows": len(result), "semantic_sha256": hashlib.sha256(canonical).hexdigest(),
                                         "inputs_sha256": {str(args.coverage): digest(args.coverage), str(args.issue_audit): digest(args.issue_audit)},
                                         "parquet_sha256": digest(args.output), "pyarrow_version": pa.__version__,
                                         "note": "source_usable 是模块覆盖筛选而不是模型发布准入；历史 Issue 评论未获独立认证。"}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
