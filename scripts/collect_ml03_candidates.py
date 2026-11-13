#!/usr/bin/env python3
"""仅采集仓库元数据并按冻结规则选取外部留出集；不计算模型特征。"""
import argparse
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path

from backend.app.core.clock import iso_z, parse_github_datetime, utc_now
from backend.app.core.exceptions import AppError
from backend.app.integrations.github.client import GitHubClient
from scripts.collect_ml_holdout import digest
from scripts.repair_issue_comments import atomic_json


RECENT = datetime(2026, 8, 11)
HISTORY_START = datetime(2025, 11, 3)


def collect(pool_path, output, delay):
    pool = json.loads(pool_path.read_text())
    output.mkdir(parents=True, exist_ok=True)
    metadata = output / 'manifest.json'
    fingerprint = digest(pool_path)
    if metadata.exists() and json.loads(metadata.read_text())['pool_sha256'] != fingerprint:
        raise ValueError('输出目录属于不同候选池')
    if not metadata.exists():
        atomic_json(metadata, {'pool_sha256': fingerprint, 'count': len(pool['repositories'])})
    with GitHubClient(on_response=lambda _response: time.sleep(delay) if delay else None) as github:
        for item in pool['repositories']:
            path = output / 'profiles' / f"{item['repository_id']}.json"
            if path.exists():
                continue
            try:
                profile, status, _ = github.get_repository_by_id(item['repository_id'])
                created = profile.get('created_at') if isinstance(profile, dict) else None
                pushed = profile.get('pushed_at') if isinstance(profile, dict) else None
                created_at = parse_github_datetime(created) if isinstance(created, str) else None
                pushed_at = parse_github_datetime(pushed) if isinstance(pushed, str) else None
                valid = bool(profile and profile.get('id') == item['repository_id'] and profile.get('private') is False and created_at and created_at <= HISTORY_START)
                reason = None if valid else 'invalid_private_or_less_than_52_weeks_history'
                activity = 'recent' if pushed_at and pushed_at >= RECENT else 'not_recent' if pushed_at else 'unknown'
                atomic_json(path, {**item, 'eligible': valid, 'reason': reason, 'activity_proxy': activity,
                                  'created_at': created, 'pushed_at': pushed, 'full_name_at_capture': profile.get('full_name') if profile else None,
                                  'captured_at': iso_z(utc_now()), 'http_status': status})
            except AppError as exc:
                if exc.code == 'GITHUB_RATE_LIMITED':
                    raise SystemExit('GitHub 限流；已保存断点，请稍后继续。') from exc
                atomic_json(path, {**item, 'eligible': False, 'reason': exc.code, 'captured_at': iso_z(utc_now())})
            print(f"{item['repository_id']}: captured", flush=True)


def select(pool_path, capture, protocol, output):
    if output.exists():
        raise FileExistsError(output)
    pool = json.loads(pool_path.read_text())
    settings = json.loads(protocol.read_text())
    if digest(pool_path) != settings['pool_sha256'] or json.loads((capture/'manifest.json').read_text())['pool_sha256'] != digest(pool_path):
        raise ValueError('候选池哈希与冻结协议不一致')
    expected = {row['repository_id'] for row in pool['repositories']}
    files = {int(path.stem): path for path in (capture/'profiles').glob('*.json')}
    if set(files) != expected:
        raise ValueError('候选池元数据未完整采集')
    groups = {}
    for item in pool['repositories']:
        row = json.loads(files[item['repository_id']].read_text())
        if row['repository_id'] != item['repository_id'] or row['stratum'] != item['stratum']:
            raise ValueError('候选身份或分层不一致')
        groups.setdefault(item['stratum'], []).append(row)
    selected, rejected = [], []
    for group, rows in sorted(groups.items()):
        ordered = sorted((row for row in rows if row.get('eligible')), key=lambda row: hashlib.sha256(f"ml03:20261109:{group}:{row['repository_id']}".encode()).hexdigest())
        chosen = []
        for activity in ('recent', 'not_recent'):
            chosen.extend([row for row in ordered if row['activity_proxy'] == activity][:2])
        for row in ordered:
            if len(chosen) >= 4:
                break
            if row not in chosen:
                chosen.append(row)
        if len(chosen) != 4:
            raise ValueError(f'候选分层有效仓库不足：{group}')
        selected.extend({key: row.get(key) for key in ('repository_id','full_name','stratum','stars_at_original_snapshot','activity_proxy','created_at','pushed_at','full_name_at_capture')} for row in chosen)
        chosen_ids = {row['repository_id'] for row in chosen}
        rejected.extend({'repository_id': row['repository_id'], 'stratum': group,
                         'reason': row.get('reason') or 'not_selected_by_frozen_stratified_hash'}
                        for row in rows if row['repository_id'] not in chosen_ids)
    atomic_json(output, {'version': 'ml03-external-holdout-v1', 'frozen_at': iso_z(utc_now()),
                         'protocol_sha256': digest(protocol), 'pool_sha256': digest(pool_path),
                         'candidate_profile_hashes': {str(k): digest(v) for k,v in sorted(files.items())},
                         'selection': '冻结协议确定的语言/Star 分层、最近推送代理和固定哈希，未使用模型特征或结果。',
                         'repositories': selected, 'excluded_or_not_selected': rejected})
    print(json.dumps({'selected': len(selected), 'unselected': len(rejected)}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='action', required=True)
    a = sub.add_parser('collect')
    a.add_argument('--pool', type=Path, required=True); a.add_argument('--output', type=Path, required=True); a.add_argument('--delay', type=float, default=0.5)
    b = sub.add_parser('freeze')
    b.add_argument('--pool', type=Path, required=True); b.add_argument('--capture', type=Path, required=True)
    b.add_argument('--protocol', type=Path, required=True); b.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'collect':
        if args.delay < 0: parser.error('delay 不能为负')
        collect(args.pool, args.output, args.delay)
    else:
        select(args.pool, args.capture, args.protocol, args.output)


if __name__ == '__main__':
    main()
