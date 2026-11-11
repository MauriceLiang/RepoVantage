"""Create and audit the frozen repository-level course ML split."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "dataprepare/MachineLearn/run/repo-evaluation-2026-v1/repository_weekly_features.csv.gz"
DEFAULT_PROFILES = ROOT / "dataprepare/MachineLearn/run/repo-evaluation-2026-v1/repository_profiles.jsonl.gz"
DEFAULT_MANIFEST = ROOT / "ml/course/splits/repositories-150-150-v1.json"
DEFAULT_AUDIT = ROOT / "reports/course-150-150/p1-split-audit.md"
EXPECTED_SOURCE_SHA256 = "5a463e44da2260d943a7851c872277984552fba3034e12eb8d5bb14c7c2c148d"
SPLIT_SEED = 20261111
ELIGIBLE_COMMIT_COVERAGE = {"complete", "true_zero"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_repository_id(value: Any) -> str:
    text = str(value)
    if not text.isascii() or not text.isdigit() or int(text) <= 0:
        raise ValueError(f"invalid repository_id: {value!r}")
    return str(int(text))


def id_list_sha256(ids: list[str]) -> str:
    payload = "\n".join(ids).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def load_weekly(source: Path) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    with gzip.open(source, "rt", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"repository_id", "repository", "period_start", "commits_observed", "commit_coverage", "data_coverage"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("weekly CSV is missing required columns")
        for row in reader:
            grouped[canonical_repository_id(row["repository_id"])].append(row)
    if len(grouped) != 300:
        raise ValueError(f"expected 300 repositories, found {len(grouped)}")
    for repository_id, rows in grouped.items():
        rows.sort(key=lambda row: row["period_start"])
        periods = [row["period_start"] for row in rows]
        if len(rows) != 52 or len(set(periods)) != 52:
            raise ValueError(f"{repository_id}: expected 52 unique weekly rows")
    return dict(sorted(grouped.items(), key=lambda item: int(item[0])))


def load_languages(profiles: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    with gzip.open(profiles, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            repository_id = canonical_repository_id(row.get("repository_id"))
            if repository_id in result:
                raise ValueError(f"duplicate profile repository_id: {repository_id}")
            language = row.get("primary_language")
            result[repository_id] = language.strip() if isinstance(language, str) and language.strip() else "未知"
    if len(result) != 300:
        raise ValueError(f"expected 300 repository profiles, found {len(result)}")
    return result


def make_split(repository_ids: list[str], seed: int = SPLIT_SEED) -> tuple[list[str], list[str]]:
    canonical = [canonical_repository_id(value) for value in repository_ids]
    if len(canonical) != len(set(canonical)) or len(canonical) != 300:
        raise ValueError("split requires 300 unique repository IDs")
    shuffled = sorted(canonical, key=int)
    random.Random(seed).shuffle(shuffled)
    return sorted(shuffled[:150], key=int), sorted(shuffled[150:], key=int)


def build_manifest(repository_ids: list[str], source_sha256: str, seed: int = SPLIT_SEED) -> dict[str, Any]:
    if source_sha256 != EXPECTED_SOURCE_SHA256:
        raise ValueError("source SHA-256 does not match the v4.4 frozen input")
    train_ids, test_ids = make_split(repository_ids, seed)
    manifest = {
        "dataset_id": "repo-evaluation-2026-v1",
        "split_version": "course-150-150-v1",
        "seed": seed,
        "split_unit": "repository_id",
        "split_method": "sort numeric repository IDs, then Python random.Random(seed).shuffle; first 150 train, remaining 150 test",
        "test_usage": "single_final_evaluation_only; do not use test features or labels for model selection",
        "repository_count": 300,
        "train_count": 150,
        "test_count": 150,
        "train_repository_ids": train_ids,
        "test_repository_ids": test_ids,
        "train_ids_sha256": id_list_sha256(train_ids),
        "test_ids_sha256": id_list_sha256(test_ids),
        "source_sha256": source_sha256,
    }
    validate_manifest(manifest, repository_ids)
    return manifest


def validate_manifest(manifest: dict[str, Any], repository_ids: list[str]) -> None:
    train = manifest.get("train_repository_ids")
    test = manifest.get("test_repository_ids")
    if not isinstance(train, list) or not isinstance(test, list):
        raise ValueError("train/test IDs must be lists")
    if len(train) != 150 or len(test) != 150:
        raise ValueError("split must contain exactly 150 train and 150 test IDs")
    if len(set(train)) != 150 or len(set(test)) != 150:
        raise ValueError("duplicate IDs within a split")
    if set(train) & set(test):
        raise ValueError("train and test IDs overlap")
    expected = {canonical_repository_id(value) for value in repository_ids}
    if set(train) | set(test) != expected:
        raise ValueError("split IDs do not exactly match the source repository IDs")
    if manifest.get("source_sha256") != EXPECTED_SOURCE_SHA256:
        raise ValueError("split source SHA-256 mismatch")
    if manifest.get("train_ids_sha256") != id_list_sha256(train):
        raise ValueError("train ID hash mismatch")
    if manifest.get("test_ids_sha256") != id_list_sha256(test):
        raise ValueError("test ID hash mismatch")


def _activity_tier(rows: list[dict[str, str]]) -> str:
    recent = rows[-12:]
    if any(row["commit_coverage"] not in ELIGIBLE_COMMIT_COVERAGE for row in recent):
        return "不可评估"
    try:
        total = sum(int(row["commits_observed"]) for row in recent)
    except (TypeError, ValueError) as exc:
        raise ValueError("complete Commit weeks must have integer counts") from exc
    if total == 0:
        return "0"
    if total < 10:
        return "1-9"
    if total < 100:
        return "10-99"
    return "100+"


def audit_markdown(
    manifest: dict[str, Any],
    grouped: dict[str, list[dict[str, str]]],
    languages: dict[str, str],
    split_sha256: str,
) -> str:
    train_ids = manifest["train_repository_ids"]
    test_ids = manifest["test_repository_ids"]
    roles = (("训练", train_ids), ("测试", test_ids))
    lines = [
        "# v4.4 P1：150/150 仓库分组审计",
        "",
        "- 数据集：`repo-evaluation-2026-v1`",
        f"- 划分版本：`{manifest['split_version']}`；固定种子：`{manifest['seed']}`",
        f"- 划分单位：`{manifest['split_unit']}`；源数据 SHA-256：`{manifest['source_sha256']}`",
        f"- 分组文件：`ml/course/splits/repositories-150-150-v1.json`；SHA-256：`{split_sha256}`",
        "- 方法：对数值排序的 300 个稳定 `repository_id` 用 Python `random.Random(seed)` 打乱一次，前 150 个作为训练组，其余 150 个作为测试组；未按结果重抽样。",
        "- 测试组在本轮 M1/M2 参数选择中禁用；分布表只用于描述随机分组的覆盖情况，不用于调参或筛除仓库。",
        "",
        "## 完整性与可评估性",
        "",
        "| 集合 | 仓库数 | M1 最近 12 周 Commit 覆盖可用 | M2 origin=48 特征及成熟 4 周标签可用 |",
        "|---|---:|---:|---:|",
    ]
    for label, ids in roles:
        m1 = sum(all(row["commit_coverage"] in ELIGIBLE_COMMIT_COVERAGE for row in grouped[rid][-12:]) for rid in ids)
        m2 = sum(all(row["commit_coverage"] in ELIGIBLE_COMMIT_COVERAGE for row in grouped[rid][36:52]) for rid in ids)
        lines.append(f"| {label} | {len(ids)} | {m1} | {m2} |")
    lines.extend(["", "## 语言分布", "", "| 语言 | 训练 | 测试 | 合计 |", "|---|---:|---:|---:|"])
    all_languages = sorted(set(languages.values()), key=str.casefold)
    for language in all_languages:
        train_count = sum(languages[rid] == language for rid in train_ids)
        test_count = sum(languages[rid] == language for rid in test_ids)
        lines.append(f"| {language} | {train_count} | {test_count} | {train_count + test_count} |")
    lines.extend(["", "## 最近 12 周 Commit 活动规模分布", "", "| 活动量（Commit） | 训练 | 测试 | 合计 |", "|---|---:|---:|---:|"])
    tiers = ("0", "1-9", "10-99", "100+", "不可评估")
    for tier in tiers:
        train_count = sum(_activity_tier(grouped[rid]) == tier for rid in train_ids)
        test_count = sum(_activity_tier(grouped[rid]) == tier for rid in test_ids)
        lines.append(f"| {tier} | {train_count} | {test_count} | {train_count + test_count} |")
    lines.extend([
        "",
        "## 解释边界",
        "",
        "- 这是既有 300 仓库历史数据上的重新分组回测，不是全新外部数据集或前瞻性验证。",
        "- M1/M2 只读取当前输入 schema 的 Commit 覆盖和周统计；PR、Issue、Release 的 partial 状态不被改写成 0，也不用于扩大 M1/M2 可评估数量。",
        "- 最近 12 周活动分层用于说明两组分布，不是重新划分或模型选择依据。",
        "- 测试组 150 个仓库是预留名单；实际测试样本数须由训练脚本根据任务级覆盖与标签成熟度另行报告。",
        "",
    ])
    return "\n".join(lines)


def write_new(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args()
    if args.manifest.exists() or args.audit.exists():
        parser.error("output exists; refusing to overwrite frozen split or audit")
    actual_sha256 = sha256_file(args.source)
    if actual_sha256 != EXPECTED_SOURCE_SHA256:
        parser.error(f"source SHA-256 mismatch: {actual_sha256}")
    grouped = load_weekly(args.source)
    languages = load_languages(args.profiles)
    if set(grouped) != set(languages):
        parser.error("weekly data and profile repository IDs differ")
    manifest = build_manifest(list(grouped), actual_sha256)
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    manifest_sha256 = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
    audit_text = audit_markdown(manifest, grouped, languages, manifest_sha256)
    write_new(args.manifest, manifest_text)
    write_new(args.audit, audit_text)
    print(f"manifest={args.manifest}")
    print(f"manifest_sha256={manifest_sha256}")
    print(f"audit={args.audit}")


if __name__ == "__main__":
    main()
