"""Validate and read the featured dataset bundle without writing database records."""

import gzip
import hashlib
import json
import logging
import re
import stat
import tempfile
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

from sqlalchemy import delete, desc, func, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.clock import iso_z, parse_github_datetime, utc_now
from backend.app.core.config import PROJECT_ROOT
from backend.app.core.exceptions import AppError
from backend.app.persistence.db import begin_immediate
from backend.app.persistence.models import (
    ActivityWindow,
    AnalysisResult,
    Dataset,
    DatasetImportJob,
    DatasetImportStagingRecord,
    DatasetRepository,
    ApplicationSetting,
    Repository,
    RepositoryActivityEvent,
    RepositoryInsightRun,
    RepositorySnapshot,
)
from backend.app.services.repositories import FEATURED_ID, LIBRARY_ID, repository_from_github

from backend.app.services.dataset_import_common import ALLOWED_FILES, BUNDLE_MAX_BYTES, UNCOMPRESSED_MAX_BYTES, MAX_RECORDS, MODULES, SCHEMA_FILES, HASH_LINE, BundleError, _positive_int, _contains_sensitive_data


def _load_bundle(root: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], str]:
    """导入前校验清单、允许的文件、校验和及记录内容。

    此函数只读取数据包；何时暂存或提交返回的记录由调用方决定。
    内容无效或不安全时抛出 BundleError，不进行部分导入。
    """
    root = root.resolve()
    manifest_path = root / "dataset.json"
    sums_path = root / "SHA256SUMS"
    if not manifest_path.is_file() or not sums_path.is_file():
        raise BundleError("数据包缺少 dataset.json 或 SHA256SUMS")
    if manifest_path.stat().st_size > 1_000_000 or sums_path.stat().st_size > 2_000_000:
        raise BundleError("数据包元信息超过大小限制")
    try:
        metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BundleError("dataset.json 无法解析") from exc
    if not isinstance(metadata, dict) or metadata.get("schema_version") != 1:
        raise BundleError("数据包 schema_version 不受支持")
    if metadata.get("dataset_id") != FEATURED_ID:
        raise BundleError("数据包 dataset_id 与内置精选集不匹配")
    version = metadata.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", version):
        raise BundleError("数据包版本号无效")
    total = metadata.get("total_repositories")
    if type(total) is not int or not 1 <= total <= 10_000:
        raise BundleError("total_repositories 无效")
    if parse_github_datetime(metadata.get("data_as_of")) is None:
        raise BundleError("data_as_of 必须是有效 ISO-8601 时间")
    sum_map = _read_checksums(root, sums_path)
    all_paths = list(root.rglob("*"))
    # 文件清单必须同时匹配允许列表和校验和清单，防止遗漏、额外文件及符号链接。
    if any(path.is_symlink() for path in all_paths):
        raise BundleError("数据包不允许包含符号链接")
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.relative_to(root).as_posix() != "SHA256SUMS"
    }
    if actual_files != ALLOWED_FILES or actual_files != set(sum_map):
        missing = sorted(ALLOWED_FILES - actual_files)
        extra = sorted(actual_files - ALLOWED_FILES)
        mismatch = missing or extra
        raise BundleError(f"数据包文件清单缺失或包含未声明文件: {', '.join(mismatch[:5])}")
    compressed_size = 0
    for relative, expected in sum_map.items():
        path = root / PurePosixPath(relative)
        target = path.resolve()
        if not target.is_relative_to(root) or not target.is_file() or path.is_symlink():
            raise BundleError("数据包包含不安全的文件路径")
        compressed_size += target.stat().st_size
        if compressed_size > BUNDLE_MAX_BYTES:
            raise BundleError("精选数据包超过 256 MiB 限制")
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise BundleError(f"SHA-256 校验失败: {relative}")
    bundle_hash = hashlib.sha256(sums_path.read_bytes()).hexdigest()

    records = {"repositories": _read_jsonl_gzip(root / "repositories.jsonl.gz")}
    repositories = records["repositories"]
    # 先确定数据包包含哪些仓库；后续所有成员、事件和详情都必须引用这些编号。
    repository_ids = {_positive_int(row.get("repository_id")) for row in repositories}
    if None in repository_ids or len(repository_ids) != len(repositories) or len(repositories) != total:
        raise BundleError("repositories.jsonl.gz 成员数量或仓库 ID 无效")
    full_names = [row.get("full_name") for row in repositories]
    if any(not isinstance(value, str) or not re.fullmatch(r"[^/\s]{1,100}/[^/\s]{1,100}", value) for value in full_names) or len(set(full_names)) != len(full_names):
        raise BundleError("仓库 full_name 缺失或重复")

    for name in ("snapshots", "memberships", "analysis", "insights", "coverage"):
        records[name] = _read_jsonl_gzip(root / f"{name}.jsonl.gz")
    for module in MODULES:
        records[f"events/{module}"] = _read_jsonl_gzip(root / f"events/{module}.jsonl.gz")
        records[f"details/{module}"] = _read_jsonl_gzip(root / f"details/{module}.jsonl.gz")
    schemas = []
    for relative in SCHEMA_FILES:
        try:
            schema = json.loads((root / relative).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise BundleError(f"schema 文件无法解析: {relative}") from exc
        if (
            not isinstance(schema, dict)
            or schema.get("type") != "object"
            or not isinstance(schema.get("required"), list)
            or not isinstance(schema.get("properties"), dict)
        ):
            raise BundleError(f"schema 文件结构无效: {relative}")
        schemas.append(schema)
    # 元数据、各类记录和说明文件都要检查敏感信息，不能只检查仓库正文。
    if _contains_sensitive_data(metadata) or any(_contains_sensitive_data(schema) for schema in schemas) or any(
        _contains_sensitive_data(row) for rows in records.values() for row in rows
    ):
        raise BundleError("数据包包含邮箱、凭证或机器绝对路径")
    for relative in ("README.md", "DATA_NOTICE.md"):
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise BundleError(f"数据说明文件无法读取: {relative}") from exc
        if _contains_sensitive_data(text):
            raise BundleError("数据包说明包含邮箱、凭证或机器绝对路径")
    for name in ("snapshots", "memberships", "analysis", "insights", "coverage", *(f"events/{module}" for module in MODULES), *(f"details/{module}" for module in MODULES)):
        if any(_positive_int(row.get("repository_id")) not in repository_ids for row in records[name]):
            raise BundleError(f"{name} 包含数据包外的 repository_id")
    if len(records["memberships"]) != total or len({_positive_int(row.get("repository_id")) for row in records["memberships"]}) != total:
        raise BundleError("精选数据集成员关系必须与仓库列表一一对应")
    if any(not isinstance(row.get("inclusion_reason"), str) or not row["inclusion_reason"].strip() for row in records["memberships"]):
        raise BundleError("精选数据集成员缺少人工纳入理由")
    if any(not isinstance(row.get("item"), dict) for module in MODULES for row in records[f"details/{module}"]):
        raise BundleError("详情文件中存在无效 item")
    for module in MODULES:
        event_ids = []
        expected_type = {"commits": "commit", "issues": "issue", "pulls": "pull_request", "releases": "release"}[module]
        for row in records[f"events/{module}"]:
            source_id = row.get("source_item_id")
            if row.get("event_type") != expected_type or not isinstance(source_id, str) or not source_id:
                raise BundleError(f"events/{module} 包含无效事件类型或 ID")
            event_ids.append((row["repository_id"], source_id))
        if len(event_ids) != len(set(event_ids)):
            raise BundleError(f"events/{module} 存在重复事件")
        if module in {"issues", "pulls"} and any("body" in row["item"] or "body_text" in row["item"] for row in records[f"details/{module}"]):
            raise BundleError(f"details/{module} 包含不允许分发的正文或邮箱字段")
    return metadata, records, bundle_hash


def _read_checksums(root: Path, sums_path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        lines = sums_path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise BundleError("SHA256SUMS 无法读取") from exc
    for line in lines:
        match = HASH_LINE.fullmatch(line)
        if not match:
            raise BundleError("SHA256SUMS 格式无效")
        digest, relative = match.groups()
        path = PurePosixPath(relative)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts) or "\\" in relative:
            raise BundleError("SHA256SUMS 包含不安全路径")
        if relative in result:
            raise BundleError("SHA256SUMS 存在重复路径")
        result[relative] = digest
    if not result or len(result) > 10_000:
        raise BundleError("SHA256SUMS 内容为空或过大")
    return result


def _read_jsonl_gzip(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or path.stat().st_size > BUNDLE_MAX_BYTES:
        raise BundleError(f"数据文件缺失或超过大小限制: {path.name}")
    rows = []
    uncompressed = 0
    try:
        with gzip.open(path, "rb") as stream:
            for line in stream:
                uncompressed += len(line)
                if uncompressed > UNCOMPRESSED_MAX_BYTES or len(line) > 8_000_000:
                    raise BundleError("JSONL 解压大小或单行长度超过限制")
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise BundleError(f"JSONL 必须逐行包含对象: {path.name}")
                rows.append(value)
                if len(rows) > MAX_RECORDS:
                    raise BundleError("数据包记录数量超过限制")
    except BundleError:
        raise
    except (OSError, EOFError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise BundleError(f"JSONL gzip 文件损坏: {path.name}") from exc
    return rows

