"""Build and serve the separate local machine-learning observability frontend."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
API_URL = "http://127.0.0.1:8501"
CONSOLE_URL = "http://127.0.0.1:8502"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建并启动独立机器学习观测台（8502）")
    return parser.parse_args()


def check_api(api_url: str) -> bool:
    try:
        with urlopen(f"{api_url.rstrip('/')}/healthz", timeout=2) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def main() -> int:
    parse_args()
    npm = shutil.which("npm")
    if not npm:
        print("未找到 npm。请安装 Node.js 后重试。", file=sys.stderr)
        return 2
    if not check_api(API_URL):
        print(f"主站 API 未就绪：{API_URL}/healthz。请先在另一个终端启动 8501 主站。", file=sys.stderr)
        return 2

    if not (FRONTEND_DIR / "node_modules" / ".bin" / "vite").exists():
        print("正在安装前端依赖…", flush=True)
        subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=FRONTEND_DIR, check=True)

    print("正在构建机器学习观测台…", flush=True)
    subprocess.run([npm, "run", "build:ml"], cwd=FRONTEND_DIR, check=True)

    env = os.environ.copy()
    env["ML_API_TARGET"] = API_URL
    print(f"机器学习观测台已启动：{CONSOLE_URL}", flush=True)
    print("按 Ctrl+C 停止观测台；主站 8501 和 Worker 会继续运行。", flush=True)
    return subprocess.run(
        [npm, "run", "preview:ml", "--", "--host", "127.0.0.1", "--port", "8502", "--strictPort"],
        cwd=FRONTEND_DIR,
        env=env,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
