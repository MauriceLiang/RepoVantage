#!/usr/bin/env python3
"""以逐 Issue 检查点补采评论；不会改写已有采集库。"""
import argparse
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

from backend.app.core.clock import parse_github_datetime
from backend.app.core.exceptions import AppError
from backend.app.integrations.github.client import GitHubClient
from backend.app.services.issue_comment_repair import collect_issue_comments


def atomic_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True, help="包含 analysis_as_of 和 issues 的 JSON 文件")
    parser.add_argument("--output", type=Path, required=True, help="专用增量输出目录")
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    args = parser.parse_args()
    if args.delay_seconds < 0:
        parser.error("delay-seconds 必须非负")
    raw = args.manifest.read_bytes()
    manifest = json.loads(raw)
    asof = parse_github_datetime(manifest.get("analysis_as_of"))
    issues = manifest.get("issues")
    if not asof or not isinstance(issues, list) or not issues:
        parser.error("manifest 必须包含有效的 analysis_as_of 和非空 issues 列表")
    fingerprint = hashlib.sha256(raw).hexdigest()
    args.output.mkdir(parents=True, exist_ok=True)
    checkpoint = args.output / "manifest.json"
    if checkpoint.exists() and json.loads(checkpoint.read_text(encoding="utf-8")).get("input_sha256") != fingerprint:
        parser.error("输出目录属于不同的输入清单，请使用新目录")
    if not checkpoint.exists():
        atomic_json(checkpoint, {"input_sha256": fingerprint, "analysis_as_of": manifest["analysis_as_of"], "issue_count": len(issues)})
    with GitHubClient(unbounded=True) as github:
        for item in issues:
            repository, number = item.get("repository"), item.get("issue_number")
            if not isinstance(repository, str) or type(number) is not int or number <= 0:
                parser.error("每条 Issue 必须有 repository 和正整数 issue_number")
            key = hashlib.sha256(f"{repository.lower()}#{number}".encode()).hexdigest()
            output = args.output / "issues" / f"{key}.json"
            if output.exists() and json.loads(output.read_text(encoding="utf-8")).get("coverage") == "complete_current_snapshot":
                continue
            try:
                record = collect_issue_comments(github, repository, number, asof)
                atomic_json(output, record)
                print(f"{repository}#{number}: {record['coverage']}", flush=True)
                if record.get("pagination_error") == "GITHUB_RATE_LIMITED":
                    raise SystemExit("GitHub 限流；已保存断点，请在限流解除后重新运行。")
            except AppError as exc:
                atomic_json(output, {"repository": repository, "issue_number": number, "coverage": "coverage_uncertain", "error_code": exc.code})
                if exc.code == "GITHUB_RATE_LIMITED":
                    raise SystemExit("GitHub 限流；已保存断点，请在限流解除后重新运行。") from exc
                print(f"{repository}#{number}: {exc.code}", flush=True)
            if args.delay_seconds:
                time.sleep(args.delay_seconds)


if __name__ == "__main__":
    main()
