#!/usr/bin/env python3
"""冻结新仓库并保存预测之前的默认分支快照，启动 ML-01 前瞻影子研究。"""
import argparse
import gzip
import hashlib
import json
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

from backend.app.core.clock import iso_z, parse_github_datetime, utc_now
from backend.app.core.exceptions import AppError
from backend.app.integrations.github.client import GitHubClient
from scripts.collect_ml_holdout import digest
from scripts.repair_issue_comments import atomic_json


def freeze(reserves, coverage, previous, model, output):
    if output.exists():
        raise FileExistsError(output)
    groups = json.loads(reserves.read_text())['reserves']
    with gzip.open(coverage, 'rt', encoding='utf-8') as stream:
        excluded = {json.loads(line)['repository_id'] for line in stream}
    excluded.update(item['repository_id'] for item in json.loads(previous.read_text())['repositories'])
    selected = []
    for group, rows in sorted(groups.items()):
        candidates = [row for row in rows if type(row.get('repository_id')) is int and row['repository_id'] not in excluded]
        candidates.sort(key=lambda row: hashlib.sha256(f"shadow-20261109:{group}:{row['repository_id']}".encode()).hexdigest())
        chosen = []
        for row in candidates:
            if row['repository_id'] not in excluded:
                chosen.append({'repository_id': row['repository_id'], 'selected_full_name': row['full_name'], 'stratum': group})
                excluded.add(row['repository_id'])
            if len(chosen) == 3:
                break
        if len(chosen) != 3:
            raise ValueError(f'新候选不足：{group}')
        selected.extend(chosen)
    atomic_json(output, {'version': 'ml01-prospective-shadow-v1', 'frozen_at': iso_z(utc_now()), 'repositories': selected,
                         'model_sha256': digest(model), 'source_sha256': {str(path): digest(path) for path in (reserves, coverage, previous)},
                         'selection': '每个语言/Star 分层按固定哈希选 3 个，排除历史 300 仓库及已评分的 45 仓库。',
                         'policy': '研究影子预测，不向产品展示；目标和基线先冻结，未来四周结束前没有标签。'})


def collect_repo(github, item, max_pages):
    repository_id = item['repository_id']
    profile, _, _ = github.get_repository_by_id(repository_id)
    branch = profile.get('default_branch') if profile else None
    created_value = profile.get('created_at') if profile else None
    created = parse_github_datetime(created_value) if isinstance(created_value, str) else None
    if not profile or profile.get('id') != repository_id or profile.get('private') is not False or not isinstance(branch, str) or not branch or not created:
        return {**item, 'status': 'coverage_uncertain', 'reason': 'profile_invalid'}
    response = github._request('GET', f'/repositories/{repository_id}/commits/{quote(branch, safe="")}')
    head = response.json()
    sha = head.get('sha') if isinstance(head, dict) else None
    captured = utc_now()
    if not isinstance(sha, str) or len(sha) != 40 or any(c not in '0123456789abcdefABCDEF' for c in sha):
        return {**item, 'status': 'coverage_uncertain', 'reason': 'head_sha_invalid'}
    history_end = (captured - timedelta(days=captured.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    start = history_end - timedelta(weeks=12)
    if created > start:
        return {**item, 'status': 'not_applicable', 'reason': 'repository_younger_than_history'}
    pages = []
    def observe(page):
        pages.append({'page': page.page_index, 'request_url': page.request_url, 'next_url': page.next_url,
                      'http_status': page.http_status, 'observed_count': len(page.records), 'has_next': page.has_next})
    result = github.list_paginated_detailed(f'/repositories/{repository_id}/commits',
                {'sha': sha, 'since': iso_z(start), 'until': iso_z(history_end)}, on_page=observe,
                max_pages=max_pages, collect_raw_pages=False)
    errors = []
    if not result.complete or result.error_code:
        errors.append('pagination_incomplete')
    if pages and pages[-1]['observed_count'] == 100 and not pages[-1]['has_next']:
        errors.append('full_terminal_page_unverified')
    seen, events, weekly = set(), [], [0] * 12
    for item_value in result.items:
        commit = item_value.get('commit') if isinstance(item_value.get('commit'), dict) else {}
        committer = commit.get('committer') if isinstance(commit.get('committer'), dict) else {}
        author = commit.get('author') if isinstance(commit.get('author'), dict) else {}
        when = committer.get('date') or author.get('date')
        event_at = parse_github_datetime(when) if isinstance(when, str) else None
        event_sha = item_value.get('sha')
        if not event_at or not isinstance(event_sha, str) or not event_sha or event_sha in seen:
            errors.append('invalid_or_duplicate_commit')
            continue
        seen.add(event_sha)
        if start <= event_at < history_end:
            weekly[(event_at - start).days // 7] += 1
            events.append({'sha': event_sha, 'event_at': iso_z(event_at)})
    return {**item, 'full_name_at_capture': profile.get('full_name'), 'status': 'complete_snapshot' if not errors else 'coverage_uncertain',
            'coverage_reasons': sorted(set(errors)), 'pagination_error': result.error_code, 'default_branch': branch,
            'head_sha_observed': sha, 'snapshot_recorded_at': iso_z(captured), 'history_start': iso_z(start),
            'history_end': iso_z(history_end), 'weekly_commits': weekly, 'events': events, 'pages': pages,
            'limitations': ['SHA 固定了可见分支快照；Commit 时间戳不等于进入分支的时间。']}


def collect(manifest_path, output, max_pages, delay):
    if max_pages < 1 or delay < 0:
        raise ValueError('分页预算必须为正，延迟不能为负')
    manifest = json.loads(manifest_path.read_text())
    output.mkdir(parents=True, exist_ok=True)
    metadata = output / 'manifest.json'
    if metadata.exists() and json.loads(metadata.read_text()).get('input_sha256') != digest(manifest_path):
        raise ValueError('输出目录属于不同清单')
    if not metadata.exists():
        atomic_json(metadata, {'input_sha256': digest(manifest_path), 'repository_count': len(manifest['repositories'])})
    with GitHubClient(on_response=lambda _response: time.sleep(delay) if delay else None) as github:
        for item in manifest['repositories']:
            path = output / 'repositories' / f"{item['repository_id']}.json"
            if path.exists() and json.loads(path.read_text()).get('status') in {'complete_snapshot', 'not_applicable'}:
                continue
            try:
                record = collect_repo(github, item, max_pages)
                atomic_json(path, record)
                print(f"{item['selected_full_name']}: {record['status']}", flush=True)
                if record.get('pagination_error') == 'GITHUB_RATE_LIMITED':
                    raise SystemExit('GitHub 限流；已保存断点。')
            except AppError as exc:
                atomic_json(path, {**item, 'status': 'coverage_uncertain', 'error_code': exc.code})
                if exc.code == 'GITHUB_RATE_LIMITED':
                    raise SystemExit('GitHub 限流；已保存断点。') from exc
                print(f"{item['selected_full_name']}: {exc.code}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest='action', required=True)
    make = subs.add_parser('freeze')
    for name in ('reserves', 'coverage', 'previous', 'model', 'output'):
        make.add_argument(f'--{name}', type=Path, required=True)
    start = subs.add_parser('collect')
    start.add_argument('--manifest', type=Path, required=True)
    start.add_argument('--output', type=Path, required=True)
    start.add_argument('--max-pages', type=int, default=10)
    start.add_argument('--delay-seconds', type=float, default=0.5)
    args = parser.parse_args()
    if args.action == 'freeze':
        freeze(args.reserves, args.coverage, args.previous, args.model, args.output)
    else:
        collect(args.manifest, args.output, args.max_pages, args.delay_seconds)


if __name__ == '__main__':
    main()
