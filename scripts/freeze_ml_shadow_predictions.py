#!/usr/bin/env python3
"""冻结影子预测及未来标签边界；本脚本不计算或推测未来标签。"""
import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'dataprepare/MachineLearn/research_s1'))
from common import dt, features, sha256  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    for name in ('manifest', 'protocol', 'collection', 'model', 'output'):
        parser.add_argument(f'--{name}', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    manifest = json.loads(args.manifest.read_text())
    protocol = json.loads(args.protocol.read_text())
    collection = json.loads((args.collection / 'manifest.json').read_text())
    if (manifest['model_sha256'] != sha256(args.model) or collection['input_sha256'] != sha256(args.manifest)
            or protocol['manifest_sha256'] != sha256(args.manifest) or protocol['model_sha256'] != sha256(args.model)):
        raise ValueError('模型或采集清单与冻结方案不一致')
    paths = {int(path.stem): path for path in (args.collection / 'repositories').glob('*.json')}
    expected = {row['repository_id'] for row in manifest['repositories']}
    if set(paths) != expected:
        raise ValueError('采集未完成或包含未冻结仓库')
    records, excluded = [], Counter()
    for item in manifest['repositories']:
        path = paths[item['repository_id']]
        record = json.loads(path.read_text())
        if record.get('repository_id') != item['repository_id']:
            raise ValueError('仓库身份不一致')
        if record.get('status') != 'complete_snapshot':
            excluded[record.get('status', 'missing')] += 1
            continue
        weekly = record['weekly_commits']
        if len(weekly) != 12 or any(type(value) is not int or value < 0 for value in weekly):
            raise ValueError('每周计数无效')
        start, end = dt(record['history_start']), dt(record['history_end'])
        rebuilt, seen = [0] * 12, set()
        for event in record['events']:
            stamp = dt(event['event_at'])
            if event['sha'] in seen or not start <= stamp < end:
                raise ValueError('历史事件无效')
            seen.add(event['sha'])
            rebuilt[(stamp - start).days // 7] += 1
        if rebuilt != weekly or end - start != timedelta(weeks=12) or dt(record['snapshot_recorded_at']) < end:
            raise ValueError('历史窗口或计数不一致')
        records.append({'repository_id': item['repository_id'], 'repository': item['selected_full_name'], 'stratum': item['stratum'],
                        'history_start': record['history_start'], 'history_end': record['history_end'],
                        'snapshot_recorded_at': record['snapshot_recorded_at'], 'default_branch': record['default_branch'],
                        'head_sha_observed': record['head_sha_observed'], 'snapshot_sha256': sha256(path), 'weekly_commits': weekly})
    if not records:
        raise ValueError('没有覆盖完整的影子仓库')
    model = joblib.load(args.model)['model']
    predictions = np.asarray(model.predict(np.asarray([features(row['weekly_commits']) for row in records])))
    if not np.isfinite(predictions).all() or np.any(predictions < 0):
        raise ValueError('模型预测无效')
    generated = datetime.now(timezone.utc)
    target_start = (generated + timedelta(minutes=2)).replace(second=0, microsecond=0)
    for row, prediction in zip(records, predictions):
        row['prediction'] = float(prediction)
        row['baseline_last_4_weeks'] = sum(row['weekly_commits'][-4:])
        row['baseline_last_12_week_mean'] = sum(row['weekly_commits']) / 3
    result = {'status': 'shadow_research_only', 'generated_at': generated.isoformat(),
              'target_start': target_start.isoformat(), 'target_end_exclusive': (target_start + timedelta(weeks=4)).isoformat(),
              'selected_repositories': len(expected), 'complete_repositories': len(records), 'excluded': dict(excluded),
              'manifest_sha256': sha256(args.manifest), 'protocol_sha256': sha256(args.protocol), 'model_sha256': sha256(args.model), 'predictions': records,
              'limitations': ['在预测生成后才开始未来四周窗口，标签尚未成熟。',
                              '历史特征锚定采集时 SHA；预测起点非 UTC 周一，需单独验证。',
                              '目标窗口结束时须另行捕获可证明时点的分支状态；当前快照不能证明过去的分支成员关系。',
                              '此候选此前回溯留出集未达标；本影子研究不会自动批准或部署模型。']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({key: result[key] for key in ('status', 'generated_at', 'target_start', 'target_end_exclusive', 'selected_repositories', 'complete_repositories', 'excluded')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
