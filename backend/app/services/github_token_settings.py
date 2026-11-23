"""Manage the local GitHub API token without returning its value to the browser."""
import json
import os
import tempfile

from backend.app.core.config import PROJECT_ROOT, get_settings
from backend.app.core.exceptions import AppError


ENV_FILE = PROJECT_ROOT / ".env"
TOKEN_ENV_NAME = "GITHUB_TOKEN"


def get_github_token_status() -> dict[str, bool]:
    return {
        "configured": bool(get_settings().github_token),
        "managed_by_environment": bool(os.environ.get(TOKEN_ENV_NAME)),
    }


def save_github_token(token: str) -> dict[str, bool]:
    _ensure_token_is_managed_by_file()
    normalized = token.strip()
    if not normalized or len(normalized) > 500 or any(character.isspace() for character in normalized):
        raise AppError(422, "VALIDATION_ERROR", "GitHub token 不能为空，且不能包含空白字符")
    _write_env_value(TOKEN_ENV_NAME, normalized)
    get_settings.cache_clear()
    return get_github_token_status()


def delete_github_token() -> dict[str, bool]:
    _ensure_token_is_managed_by_file()
    _write_env_value(TOKEN_ENV_NAME, "")
    get_settings.cache_clear()
    return get_github_token_status()


def _ensure_token_is_managed_by_file() -> None:
    if os.environ.get(TOKEN_ENV_NAME):
        raise AppError(
            409,
            "CONFLICTING_OPERATION",
            "GITHUB_TOKEN 由进程环境变量提供；请修改启动环境后重启服务。",
        )


def _write_env_value(key: str, value: str) -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    replacement = f"{key}={json.dumps(value)}"
    replaced = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        name = line.partition("=")[0].strip().removeprefix("export ").strip()
        if name == key:
            lines[index] = replacement
            replaced = True
    if not replaced:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(replacement)

    contents = "\n".join(lines).rstrip("\n") + "\n"
    file_descriptor, temporary_name = tempfile.mkstemp(prefix=".env.", dir=PROJECT_ROOT)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(contents)
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, ENV_FILE)
        os.chmod(ENV_FILE, 0o600)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
