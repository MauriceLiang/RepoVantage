#!/usr/bin/env python3
"""停用 ML-03 并记录回退事件；不会批准或启用模型。"""
import argparse
import fcntl
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def disable(registry_path: Path, event_path: Path, reason: str) -> bool:
    reason = reason.strip()
    if not reason or len(reason) > 500:
        raise ValueError('必须提供不超过 500 字的回退原因')
    lock_path = registry_path.with_suffix(registry_path.suffix + '.lock')
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        document = json.loads(registry_path.read_text(encoding='utf-8'))
        entries = [item for item in document['models'] if item.get('model_id') == 'ML-03']
        if document.get('registry_version') != 1 or len(entries) != 1:
            raise ValueError('无效的 ML-03 注册表')
        entry = entries[0]
        previous = entry['runtime_state']
        if previous == 'disabled':
            return False
        if previous not in {'research_only', 'approved', 'shadow', 'canary', 'active'}:
            raise ValueError('无效的模型状态')
        entry['runtime_state'] = 'disabled'
        entry['reason'] = reason
        encoded = (json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
        mode = registry_path.stat().st_mode & 0o777
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=registry_path.parent, prefix='.registry-', delete=False) as stream:
                temporary = Path(stream.name)
                os.fchmod(stream.fileno(), mode)
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, registry_path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        event_path.parent.mkdir(parents=True, exist_ok=True)
        event = {'at': datetime.now(UTC).isoformat(), 'model_id': 'ML-03', 'version': entry.get('version'),
                 'from': previous, 'to': 'disabled', 'reason': reason}
        with event_path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reason', required=True, help='记录停用原因')
    args = parser.parse_args()
    changed = disable(ROOT/'ml-production/registry.json', ROOT/'ml-production/logs/registry_events.jsonl', args.reason)
    print('ML-03 已停用；后续请求回退统计。' if changed else 'ML-03 已处于停用状态。')


if __name__ == '__main__':
    main()
