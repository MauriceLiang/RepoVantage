#!/usr/bin/env python3
"""从本地研究采集库构建覆盖 300 个默认仓库的历史事件包。"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import sqlite3
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dataprepare/MachineLearn/run/repo-evaluation-2026-v1/collection.sqlite3"
COURSE = ROOT / "data/datasets/course-research-300-v1"
OUTPUT = ROOT / "data/datasets/course-research-events-300-v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse(value: str | None) -> datetime | None:
    if value is None:
        return None
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("历史事件时间缺少时区")
    return result.astimezone(timezone.utc)


def build(source_path: Path, course_root: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"拒绝覆盖已有事件包：{output}")
    with gzip.open(course_root / "weekly_features.json.gz", "rt", encoding="utf-8") as stream:
        weekly = json.load(stream)
    with gzip.open(course_root / "repositories.json.gz", "rt", encoding="utf-8") as stream:
        repository_ids = {int(row["repository_id"]) for row in json.load(stream)}
    if len(repository_ids) != 300 or len(weekly) != 300 * 12:
        raise ValueError("默认仓库包须包含 300 个仓库及各 12 周聚合数据")

    source = sqlite3.connect(f"{source_path.resolve().as_uri()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    try:
        metadata = dict(source.execute("SELECT key,value FROM metadata WHERE key IN ('dataset_id','time_scope')"))
        if metadata.get("dataset_id") != "repo-evaluation-2026-v1":
            raise ValueError("研究采集库的数据集 ID 不匹配")
        scope = json.loads(metadata["time_scope"])
        end = parse(scope["analysis_as_of"])
        start = parse(scope["pr_commit_window_start"])
        issue_start = parse(scope["issue_window_start"])
        weekly_end = parse(scope["weekly_period_end_exclusive"])
        if not end or not start or not issue_start or not weekly_end or end - start < timedelta(days=180) or end - issue_start < timedelta(days=180):
            raise ValueError("研究采集库没有覆盖完整的 180 天分析窗口")
        placeholders = ",".join("?" for _ in repository_ids)
        ids = sorted(repository_ids)
        present = {row[0] for row in source.execute(
            f"SELECT repository_id FROM repositories WHERE repository_id IN ({placeholders})", ids
        )}
        if present != repository_ids:
            raise ValueError("研究采集库与默认 300 仓库清单不一致")

        with tempfile.TemporaryDirectory(prefix="course-test-events-") as temporary:
            sqlite_path = Path(temporary) / "events.sqlite3"
            target = sqlite3.connect(sqlite_path)
            target.executescript("""
                CREATE TABLE repositories (repository_id INTEGER PRIMARY KEY, created_at TEXT NOT NULL);
                CREATE TABLE coverage (repository_id INTEGER NOT NULL, module TEXT NOT NULL, status TEXT NOT NULL,
                                       PRIMARY KEY(repository_id,module)) WITHOUT ROWID;
                CREATE TABLE commits (repository_id INTEGER NOT NULL, sha TEXT NOT NULL, event_at TEXT NOT NULL,
                                      author_key TEXT, PRIMARY KEY(repository_id,sha)) WITHOUT ROWID;
                CREATE TABLE issues (repository_id INTEGER NOT NULL, id INTEGER NOT NULL, number INTEGER NOT NULL,
                                     created_at TEXT NOT NULL, closed_at TEXT, updated_at TEXT, comments_count INTEGER,
                                     PRIMARY KEY(repository_id,id)) WITHOUT ROWID;
                CREATE TABLE pulls (repository_id INTEGER NOT NULL, id INTEGER NOT NULL, number INTEGER NOT NULL,
                                    created_at TEXT NOT NULL, closed_at TEXT, merged_at TEXT, updated_at TEXT,
                                    draft INTEGER, PRIMARY KEY(repository_id,id)) WITHOUT ROWID;
                CREATE TABLE releases (repository_id INTEGER NOT NULL, id INTEGER NOT NULL, name TEXT, published_at TEXT,
                                       draft INTEGER NOT NULL, prerelease INTEGER NOT NULL,
                                       PRIMARY KEY(repository_id,id)) WITHOUT ROWID;
            """)
            counts = Counter()
            week_counts = Counter()
            weeks_start = weekly_end - timedelta(weeks=12)

            profiles = list(source.execute(
                f"SELECT repository_id,created_at FROM repository_profiles WHERE repository_id IN ({placeholders})", ids
            ))
            if len(profiles) != 300 or any(parse(row["created_at"]) is None for row in profiles):
                raise ValueError("默认仓库的创建时间不完整")
            target.executemany("INSERT INTO repositories VALUES (?,?)", (tuple(row) for row in profiles))

            def count_week(repository_id: int, kind: str, value: str | None) -> None:
                at = parse(value)
                if at is not None and weeks_start <= at < weekly_end:
                    monday = (at - timedelta(days=at.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
                    week_counts[(repository_id, monday.isoformat().replace("+00:00", "Z"), kind)] += 1

            for row in source.execute(
                f"SELECT repository_id,module,status FROM module_state WHERE repository_id IN ({placeholders})", ids
            ):
                if row["module"] in {"commits", "issues", "pull_requests_created", "pull_requests_updated", "releases"}:
                    target.execute("INSERT INTO coverage VALUES (?,?,?)", tuple(row))
            if target.execute("SELECT count(*) FROM coverage").fetchone()[0] != 300 * 5:
                raise ValueError("默认仓库的模块覆盖状态不完整")

            authors: dict[tuple[int, int], str] = {}
            for row in source.execute(
                f"SELECT repository_id,commit_sha,committer_date,author_date,author_id FROM commits WHERE repository_id IN ({placeholders})", ids
            ):
                at_text = row["committer_date"] or row["author_date"]
                at = parse(at_text)
                if at is None or not start <= at < end:
                    continue
                author = row["author_id"]
                key = None
                if type(author) is int and author > 0:
                    identity = (row["repository_id"], author)
                    if identity not in authors:
                        token = hashlib.sha256(f"{identity[0]}:{identity[1]}".encode()).hexdigest()[:16]
                        authors[identity] = f"匿名账号 {token}"
                    key = authors[identity]
                target.execute("INSERT INTO commits VALUES (?,?,?,?)", (row["repository_id"], row["commit_sha"], at_text, key))
                count_week(row["repository_id"], "commits", at_text)
                counts["commits"] += 1

            for row in source.execute(
                f"SELECT repository_id,issue_id,number,created_at,closed_at,updated_at,comments_count FROM issues WHERE is_pull_request=0 AND repository_id IN ({placeholders})", ids
            ):
                created, closed = parse(row["created_at"]), parse(row["closed_at"])
                if created is None or not (start <= created < end or closed is not None and start <= closed < end):
                    continue
                target.execute("INSERT INTO issues VALUES (?,?,?,?,?,?,?)", tuple(row))
                counts["issues"] += 1

            for row in source.execute(
                f"SELECT repository_id,pull_request_id,number,created_at,closed_at,merged_at,updated_at,draft FROM pull_requests WHERE repository_id IN ({placeholders})", ids
            ):
                created, closed, merged = (parse(row[key]) for key in ("created_at", "closed_at", "merged_at"))
                if created is None or not any(value is not None and start <= value < end for value in (created, closed, merged)):
                    continue
                target.execute("INSERT INTO pulls VALUES (?,?,?,?,?,?,?,?)", tuple(row))
                count_week(row["repository_id"], "prs_opened", row["created_at"])
                count_week(row["repository_id"], "prs_merged", row["merged_at"])
                counts["pulls"] += 1

            for row in source.execute(
                f"SELECT repository_id,release_id,name,published_at,draft,prerelease FROM releases WHERE repository_id IN ({placeholders})", ids
            ):
                if row["draft"] not in (0, 1) or row["prerelease"] not in (0, 1):
                    raise ValueError("Release 状态缺失，无法导出")
                target.execute("INSERT INTO releases VALUES (?,?,?,?,?,?)", tuple(row))
                counts["releases"] += 1

            for row in weekly:
                for kind in ("commits", "prs_opened", "prs_merged"):
                    if row[kind] is not None and week_counts[(row["repository_id"], row["week_start_utc"], kind)] != row[kind]:
                        raise ValueError(f"历史事件与 12 周聚合不一致：仓库 {row['repository_id']}，{kind}")
            target.commit()
            target.close()
            output.mkdir(parents=True)
            archive = output / "events.sqlite3.gz"
            with sqlite_path.open("rb") as src, archive.open("xb") as raw:
                with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as dst:
                    shutil.copyfileobj(src, dst)
            manifest = {
                "schema_version": 1, "dataset_id": "course-test-events-v1",
                "source_dataset_id": metadata["dataset_id"], "sample_dataset_id": "course-research-300-v1",
                "repository_count": len(repository_ids),
                "window_start": start.isoformat().replace("+00:00", "Z"),
                "window_end": end.isoformat().replace("+00:00", "Z"),
                "source_as_of": scope["analysis_as_of"], "issue_created_since": scope["issue_window_start"],
                "record_counts": dict(counts), "archive_sha256": sha256(archive),
                "sqlite_sha256": sha256(sqlite_path), "sqlite_size": sqlite_path.stat().st_size,
            }
            (output / "dataset.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return manifest
    finally:
        source.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--course", type=Path, default=COURSE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = build(args.source, args.course, args.output)
    print(json.dumps({"repositories": result["repository_count"], "record_counts": result["record_counts"],
                      "sqlite_size": result["sqlite_size"]}, ensure_ascii=False))
