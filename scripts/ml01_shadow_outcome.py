#!/usr/bin/env python3
"""按冻结协议采集 ML-01 到期分支证据；未知情况不能产生正式标签。"""
import argparse
import fcntl
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from backend.app.core.clock import iso_z, parse_github_datetime, utc_now
from backend.app.core.exceptions import AppError
from backend.app.integrations.github.client import GitHubClient
from scripts.collect_ml_holdout import digest
from scripts.repair_issue_comments import atomic_json

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'dataprepare/MachineLearn/run/p0-reproduction-v2'
PREDICTIONS = RUN / 'prospective_shadow_predictions.json'
PROTOCOL = RUN / 'prospective_shadow_protocol.json'
MANIFEST = RUN / 'prospective_shadow_manifest.json'
MODEL = ROOT / 'dataprepare/MachineLearn/run/s1-20261109-v1/activity/commit/research_model.joblib'
SNAPSHOTS = ROOT / 'dataprepare/MachineLearn/run/prospective-shadow-v2/repositories'
OUTPUT = ROOT / 'dataprepare/MachineLearn/run/ml01-shadow-outcome-v3'
TASK_LOCK = ROOT / 'ml-production/scheduling/task_lock.json'


def validate_task_code():
    lock = json.loads(TASK_LOCK.read_text())
    allowed = {'scripts/ml01_shadow_outcome.py', 'scripts/collect_ml_holdout.py', 'scripts/repair_issue_comments.py',
               'backend/app/integrations/github/client.py', 'backend/app/core/clock.py', 'backend/app/core/config.py',
               'backend/app/core/exceptions.py', 'pyproject.toml', 'uv.lock',
               'ml-production/scheduling/com.repovantage.ml01-shadow-20261207.plist'}
    if set(lock.get('hashes', {})) != allowed or lock.get('python_version') != sys.version.split()[0]:
        raise ValueError('定时任务代码或 Python 版本清单无效')
    for name in allowed:
        if digest(ROOT/name) != lock['hashes'][name]:
            raise ValueError(f'定时任务文件哈希已改变：{name}')
    installed = Path.home()/'Library/LaunchAgents/com.repovantage.ml01-shadow-20261207.plist'
    if installed.exists() and digest(installed) != lock['hashes']['ml-production/scheduling/com.repovantage.ml01-shadow-20261207.plist']:
        raise ValueError('已安装的定时任务与冻结配置不一致')


def dt(value):
    if not isinstance(value, str):
        raise ValueError('无效时间')
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def validate_inputs():
    validate_task_code()
    prediction = json.loads(PREDICTIONS.read_text())
    protocol = json.loads(PROTOCOL.read_text())
    if (prediction['manifest_sha256'] != digest(MANIFEST) or prediction['protocol_sha256'] != digest(PROTOCOL)
            or prediction['model_sha256'] != digest(MODEL) or protocol['manifest_sha256'] != digest(MANIFEST)
            or protocol['model_sha256'] != digest(MODEL)):
        raise ValueError('冻结模型、名单或协议哈希不一致')
    start, end = dt(prediction['target_start']), dt(prediction['target_end_exclusive'])
    if end - start != timedelta(weeks=4) or dt(prediction['generated_at']) >= start:
        raise ValueError('冻结预测的目标窗口无效')
    ids = set()
    for row in prediction['predictions']:
        repo = row['repository_id']
        path = SNAPSHOTS/f'{repo}.json'
        if repo in ids or row['snapshot_sha256'] != digest(path):
            raise ValueError('仓库快照哈希或身份不一致')
        ids.add(repo)
    if len(ids) != prediction['complete_repositories'] or len(ids) != 40:
        raise ValueError('冻结的完整仓库集合发生变化')
    return prediction


def observe_head(github, row):
    profile, status, _ = github.get_repository_by_id(row['repository_id'])
    branch = profile.get('default_branch') if isinstance(profile, dict) else None
    if not profile or profile.get('id') != row['repository_id'] or profile.get('private') is not False or not isinstance(branch, str):
        raise AppError(502, 'GITHUB_UPSTREAM_ERROR', '仓库身份或默认分支无法核实')
    response = github._request('GET', f"/repositories/{row['repository_id']}/commits/{quote(branch, safe='')}")
    body = response.json()
    sha = body.get('sha') if isinstance(body, dict) else None
    if not isinstance(sha, str) or len(sha) != 40 or any(ch not in '0123456789abcdefABCDEF' for ch in sha):
        raise AppError(502, 'GITHUB_UPSTREAM_ERROR', '默认分支 SHA 无效')
    return {'repository_id': row['repository_id'], 'branch': branch, 'head_sha': sha,
            'observed_at': iso_z(utc_now()), 'profile_http_status': status, 'head_http_status': response.status_code}


def observe_events(github, row, pre, post, start, end):
    """保存可见事件和边界证据；对推测性的历史分支成员关系始终不自动准入。"""
    reasons = []
    if not pre or dt(pre['observed_at']) >= end:
        reasons.append('missing_pre_boundary_snapshot')
    if not post or dt(post['observed_at']) < end:
        reasons.append('missing_post_boundary_snapshot')
    if (pre and pre['branch'] != row['default_branch']) or (post and post['branch'] != row['default_branch']) or (pre and post and pre['branch'] != post['branch']):
        reasons.append('default_branch_changed')
    if pre and post and pre['head_sha'] != post['head_sha']:
        reasons.append('head_changed_across_boundary')
    compare = None
    events, pages = [], []
    if post:
        try:
            path = f"/repositories/{row['repository_id']}/compare/{row['head_sha_observed']}...{post['head_sha']}"
            response = github._request('GET', path, params={'per_page': 1})
            value = response.json()
            compare = {key: value.get(key) for key in ('status', 'ahead_by', 'behind_by', 'total_commits')} if isinstance(value, dict) else None
            if not compare or compare['status'] not in {'ahead', 'identical'} or compare['behind_by'] != 0:
                reasons.append('non_descendant_or_unverifiable_history')
            def observe(page):
                pages.append({'page': page.page_index, 'request_url': page.request_url, 'next_url': page.next_url,
                              'http_status': page.http_status, 'observed_count': len(page.records), 'has_next': page.has_next})
            result = github.list_paginated_detailed(f"/repositories/{row['repository_id']}/commits",
                         {'sha': post['head_sha'], 'since': start.isoformat(), 'until': end.isoformat()},
                         on_page=observe, max_pages=100, collect_raw_pages=False)
            if result.error_code == 'GITHUB_RATE_LIMITED':
                raise AppError(429, 'GITHUB_RATE_LIMITED', 'GitHub 限流')
            if not result.complete or result.error_code:
                reasons.append('incomplete_pagination')
            if pages and pages[-1]['observed_count'] == 100 and not pages[-1]['has_next']:
                reasons.append('full_terminal_page_unverified')
            seen = set()
            for item in result.items:
                commit = item.get('commit') if isinstance(item.get('commit'), dict) else {}
                committer = commit.get('committer') if isinstance(commit.get('committer'), dict) else {}
                author = commit.get('author') if isinstance(commit.get('author'), dict) else {}
                value = committer.get('date') or author.get('date')
                timestamp = parse_github_datetime(value) if isinstance(value, str) else None
                sha = item.get('sha')
                if timestamp is None or not isinstance(sha, str) or len(sha) != 40 or sha in seen:
                    reasons.append('invalid_or_duplicate_commit'); continue
                seen.add(sha)
                aware = timestamp.replace(tzinfo=timezone.utc)
                if start <= aware < end:
                    events.append({'sha': sha, 'event_at': iso_z(timestamp)})
        except AppError as exc:
            if exc.code == 'GITHUB_RATE_LIMITED':
                raise
            reasons.append(exc.code)
    else:
        reasons.append('head_unavailable')
    if not reasons:
        reasons.append('historical_membership_requires_independent_review')
    return {'repository_id': row['repository_id'], 'target_status': 'coverage_uncertain', 'eligible_for_scoring': False,
            'reasons': sorted(set(reasons)), 'pre_boundary': pre, 'post_boundary': post, 'compare_from_frozen_sha': compare,
            'visible_commit_timestamp_count': len(events), 'events': events, 'pages': pages,
            'limitations': ['统计为结束时可见分支上提交的 committer 时间，不证明提交进入分支的精确时刻。',
                            '两次相同 SHA 不能排除中间不可见的强推及恢复；自动程序不批准历史标签。']}


def notify_failure(message, output):
    atomic_json(output/'last_failure.json', {'at': iso_z(utc_now()), 'message': message})
    try:
        subprocess.run(['/usr/bin/osascript', '-e', 'display notification "影子采集失败，请查看 RepoVantage 运行日志" with title "RepoVantage"'],
                       timeout=10, check=False, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        pass


def run(output=OUTPUT, *, rehearsal=False):
    prediction = validate_inputs()
    output.mkdir(parents=True, exist_ok=True)
    start, end = dt(prediction['target_start']), dt(prediction['target_end_exclusive'])
    now = datetime.now(timezone.utc)
    if not rehearsal and now < end - timedelta(minutes=2):
        print(f'armed: target_end={end.isoformat()}', flush=True)
        return 0
    lockfile = output/'run.lock'
    with lockfile.open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('already running', flush=True)
            return 0
        if not rehearsal and (output/'completed.json').exists():
            print('already completed', flush=True)
            return 0
        if not rehearsal:
            attempt_file = output/'attempts.json'
            attempts = json.loads(attempt_file.read_text()).get('attempts', 0) if attempt_file.exists() else 0
            if attempts >= 3:
                notify_failure('三次尝试均未完成，请人工检查并补救。', output)
                print('retry limit reached; manual intervention required', flush=True)
                return 0
            atomic_json(attempt_file, {'attempts': attempts + 1, 'last_started_at': iso_z(utc_now())})
        try:
            with GitHubClient(on_response=lambda _response: time.sleep(.2)) as github:
                if rehearsal:
                    row = prediction['predictions'][0]
                    head = observe_head(github, row)
                    atomic_json(output/'rehearsal.json', {'status': 'pass', 'checked_at': iso_z(utc_now()),
                                'repository_id': row['repository_id'], 'head_observation': head,
                                'target_labels_created': False, 'predictions_sha256': digest(PREDICTIONS)})
                    print('rehearsal passed; no future labels created', flush=True)
                    return 0
                for row in prediction['predictions']:
                    path = output/'pre'/f"{row['repository_id']}.json"
                    if path.exists() or datetime.now(timezone.utc) >= end:
                        continue
                    try:
                        atomic_json(path, observe_head(github, row))
                    except AppError as exc:
                        if exc.code == 'GITHUB_RATE_LIMITED': raise
                        atomic_json(path, {'repository_id': row['repository_id'], 'error_code': exc.code})
                while datetime.now(timezone.utc) < end:
                    time.sleep(min(5, max(.1, (end - datetime.now(timezone.utc)).total_seconds())))
                for row in prediction['predictions']:
                    path = output/'post'/f"{row['repository_id']}.json"
                    if path.exists(): continue
                    try:
                        atomic_json(path, observe_head(github, row))
                    except AppError as exc:
                        if exc.code == 'GITHUB_RATE_LIMITED': raise
                        atomic_json(path, {'repository_id': row['repository_id'], 'error_code': exc.code})
                for row in prediction['predictions']:
                    path = output/'repositories'/f"{row['repository_id']}.json"
                    if path.exists(): continue
                    before = output/'pre'/f"{row['repository_id']}.json"
                    after = output/'post'/f"{row['repository_id']}.json"
                    pre = json.loads(before.read_text()) if before.exists() else None
                    post = json.loads(after.read_text()) if after.exists() else None
                    if pre and 'error_code' in pre: pre = None
                    if post and 'error_code' in post: post = None
                    atomic_json(path, observe_events(github, row, pre, post, start, end))
            atomic_json(output/'completed.json', {'status': 'captured_review_required', 'completed_at': iso_z(utc_now()),
                        'repositories': len(prediction['predictions']), 'excluded_at_freeze': prediction['excluded'],
                        'prediction_sha256': digest(PREDICTIONS), 'automatic_release': False,
                        'note': '所有结果保留 coverage_uncertain，必须独立核验历史成员关系后才可考虑评分。'})
            print('captured; independent review required', flush=True)
            return 0
        except Exception as exc:
            notify_failure(f'{type(exc).__name__}: {str(exc)[:300]}', output)
            print(f'capture failed: {type(exc).__name__}', flush=True)
            return 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rehearsal', action='store_true')
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    try:
        code = run(args.output, rehearsal=args.rehearsal)
    except Exception as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        notify_failure(f'{type(exc).__name__}: {str(exc)[:300]}', args.output)
        print(f'input validation failed: {type(exc).__name__}', flush=True)
        code = 1
    raise SystemExit(code)


if __name__ == '__main__':
    main()
