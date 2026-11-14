#!/usr/bin/env python3
"""补采冻结仓库的 Release 历史；当前可见快照不保证恢复已删除的历史。"""
import argparse
import json
import time
from pathlib import Path

from backend.app.core.clock import iso_z, parse_github_datetime, utc_now
from backend.app.core.exceptions import AppError
from backend.app.integrations.github.client import GitHubClient
from scripts.collect_ml_holdout import digest
from scripts.repair_issue_comments import atomic_json


def collect_repo(github, candidate, max_pages):
    repository_id = candidate['repository_id']
    profile, _, _ = github.get_repository_by_id(repository_id)
    if not profile or profile.get('id') != repository_id:
        raise AppError(502, 'GITHUB_UPSTREAM_ERROR', '仓库身份不一致')
    created_value = profile.get('created_at')
    created = parse_github_datetime(created_value) if isinstance(created_value, str) else None
    if profile.get('private') is not False or created is None:
        return {**candidate, 'status': 'coverage_uncertain', 'coverage_reasons': ['profile_invalid']}
    pages = []
    def observe(page):
        pages.append({'page': page.page_index, 'request_url': page.request_url, 'next_url': page.next_url,
                      'http_status': page.http_status, 'observed_count': len(page.records), 'has_next': page.has_next,
                      'first_page_ids': [item.get('id') for item in page.records] if page.page_index == 1 else None})
    path = f'/repositories/{repository_id}/releases'
    result = github.list_paginated_detailed(path, {}, on_page=observe, max_pages=max_pages, collect_raw_pages=False)
    errors = []
    if not result.complete or result.error_code:
        errors.append('pagination_incomplete')
    if pages and pages[-1]['observed_count'] == 100 and not pages[-1]['has_next']:
        errors.append('full_terminal_page_unverified')
    releases, seen = [], set()
    for item in result.items:
        release_id = item.get('id')
        if type(release_id) is not int or release_id in seen:
            errors.append('invalid_or_duplicate_release')
            continue
        seen.add(release_id)
        if type(item.get('draft')) is not bool:
            errors.append('invalid_draft_status')
            continue
        if item['draft']:
            continue
        published_value = item.get('published_at')
        published = parse_github_datetime(published_value) if isinstance(published_value, str) else None
        if published is None:
            errors.append('invalid_published_at')
            continue
        releases.append({'id': release_id, 'published_at': iso_z(published), 'prerelease': item.get('prerelease') is True})
    pagination_error = result.error_code
    if pagination_error != 'GITHUB_RATE_LIMITED':
        head = github.list_paginated_detailed(path, {}, max_pages=1, collect_raw_pages=False)
        if head.error_code or [item.get('id') for item in head.items] != (pages[0]['first_page_ids'] if pages else []):
            errors.append('head_changed_or_unavailable')
        if head.error_code == 'GITHUB_RATE_LIMITED':
            pagination_error = head.error_code
    return {**candidate, 'full_name_at_capture': profile.get('full_name'), 'created_at': iso_z(created),
            'captured_at': iso_z(utc_now()), 'status': 'complete_current_snapshot' if not errors else 'coverage_uncertain',
            'coverage_reasons': sorted(set(errors)), 'pagination_error': pagination_error, 'pages': pages, 'releases': releases,
            'limitations': ['当前可见 Release 不证明历史时点的发布、删除或草稿状态。']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-pages', type=int, default=50)
    parser.add_argument('--delay-seconds', type=float, default=0.5)
    args = parser.parse_args()
    if args.max_pages < 1 or args.delay_seconds < 0:
        parser.error('分页预算必须为正，延迟不能为负')
    protocol = json.loads(args.protocol.read_text())
    if digest(args.manifest) != protocol['manifest_sha256']:
        raise ValueError('冻结清单哈希不一致')
    manifest = json.loads(args.manifest.read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    checkpoint = args.output / 'manifest.json'
    if checkpoint.exists() and json.loads(checkpoint.read_text()).get('protocol_sha256') != digest(args.protocol):
        raise ValueError('输出目录属于不同的冻结方案')
    if not checkpoint.exists():
        atomic_json(checkpoint, {'protocol_sha256': digest(args.protocol), 'repository_count': len(manifest['repositories'])})
    with GitHubClient(on_response=lambda _response: time.sleep(args.delay_seconds) if args.delay_seconds else None) as github:
        for item in manifest['repositories']:
            path = args.output / 'repositories' / f"{item['repository_id']}.json"
            if path.exists() and json.loads(path.read_text()).get('status') == 'complete_current_snapshot':
                continue
            try:
                record = collect_repo(github, item, args.max_pages)
                atomic_json(path, record)
                print(f"{item['selected_full_name']}: {record['status']}", flush=True)
                if record.get('pagination_error') == 'GITHUB_RATE_LIMITED':
                    raise SystemExit('GitHub 限流；已保存断点。')
            except AppError as exc:
                atomic_json(path, {**item, 'status': 'coverage_uncertain', 'error_code': exc.code})
                if exc.code == 'GITHUB_RATE_LIMITED':
                    raise SystemExit('GitHub 限流；已保存断点。') from exc
                print(f"{item['selected_full_name']}: {exc.code}", flush=True)


if __name__ == '__main__':
    main()
