"""Shared validation limits, bundle metadata, and input value helpers."""

import json
import re
from typing import Any
from backend.app.core.config import PROJECT_ROOT

BUNDLE_ROOT = (PROJECT_ROOT / "data" / "datasets" / "featured-v1").resolve()
BUNDLE_MAX_BYTES = 256 * 1024 * 1024
UNCOMPRESSED_MAX_BYTES = 1024 * 1024 * 1024
MAX_RECORDS = 1_000_000
MODULES = ("commits", "issues", "pulls", "releases")
FEATURED_LIBRARY_SEEDED_KEY = "featured_library_seeded_v1"
DATA_FILES = (
    "repositories.jsonl.gz",
    "snapshots.jsonl.gz",
    "memberships.jsonl.gz",
    "analysis.jsonl.gz",
    "insights.jsonl.gz",
    "coverage.jsonl.gz",
    *(f"events/{module}.jsonl.gz" for module in MODULES),
    *(f"details/{module}.jsonl.gz" for module in MODULES),
)
REQUIRED_FILES = {"dataset.json", *DATA_FILES, "README.md", "DATA_NOTICE.md"}
SCHEMA_FILES = {"schemas/repository.schema.json", "schemas/event.schema.json", "schemas/coverage.schema.json"}
ALLOWED_FILES = REQUIRED_FILES | SCHEMA_FILES
HASH_LINE = re.compile(r"^([a-f0-9]{64})  (.+)$")
EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
CREDENTIAL_PATTERN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+[A-Za-z0-9._-]{20,})", re.IGNORECASE)
MACHINE_PATH_PATTERN = re.compile(r"(?:/Users/[^\s\"<>]+|/private/var/[^\s\"<>]+|[A-Z]:\\Users\\[^\s\"<>]+)")

class BundleError(ValueError):
    """数据包不存在、已损坏、存在安全问题或使用了不支持的格式。"""


def _positive_int(value: Any) -> int | None:
    return value if type(value) is int and value > 0 else None


def _nonnegative_int(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _contains_sensitive_data(value: Any) -> bool:
    """递归检查数据包中的邮箱、凭据和本机路径，防止导入敏感内容。"""
    if isinstance(value, dict):
        return any(
            str(key).casefold() in {"email", "email_address"} or _contains_sensitive_data(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_sensitive_data(item) for item in value)
    if isinstance(value, str):
        return bool(EMAIL_PATTERN.search(value) or CREDENTIAL_PATTERN.search(value) or MACHINE_PATH_PATTERN.search(value))
    return False


def _json_object(value: str | None) -> dict[str, Any]:
    """读取可选状态 JSON；缺失、格式错误或非对象时返回空字典。"""
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}

