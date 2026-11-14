#!/usr/bin/env python3
"""Restore the frozen course M1/M2 JSON artifacts captured at the v4.1 baseline."""
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "reports/ml/course-final-baseline.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    backups = manifest["restore_backups"]
    for name, expected in backups.items():
        source = ROOT / "ml/course/rollback" / name
        payload = source.read_bytes()
        if sha256(payload) != expected:
            raise SystemExit(f"Backup checksum mismatch: {source}")
        destination = ROOT / "ml/course/artifacts" / name
        destination.write_bytes(payload)
        if sha256(destination.read_bytes()) != expected:
            raise SystemExit(f"Restore verification failed: {destination}")
        print(f"Restored {destination.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
