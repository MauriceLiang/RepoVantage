"""离线校验精选数据集目录或 ZIP 文件，不连接 GitHub 或数据库。"""

import argparse
import json
import sys
from pathlib import Path

from backend.app.services.dataset_import import BundleError, verify_dataset_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="bundle directory or ZIP")
    args = parser.parse_args()
    try:
        print(json.dumps(verify_dataset_bundle(args.source), ensure_ascii=False, indent=2))
    except (OSError, BundleError) as exc:
        print(f"dataset bundle verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
