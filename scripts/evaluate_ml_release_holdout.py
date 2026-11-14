#!/usr/bin/env python3
"""对冻结的新仓库做 Release 空窗回溯诊断，不得作为生产准入。"""
import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def sample(record, protocol):
    origin = timestamp(protocol['evaluation_origin'])
    start, end = timestamp(protocol['history_start']), timestamp(protocol['target_end_exclusive'])
    if record['status'] != 'complete_current_snapshot':
        return None, 'coverage_uncertain'
    if timestamp(record['created_at']) > start:
        return None, 'repository_too_young'
    weeks = [0] * 26
    future = 0
    for release in record['releases']:
        published = timestamp(release['published_at'])
        if start <= published < origin:
            weeks[(published - start).days // 7] += 1
        elif origin <= published < end:
            future += 1
    active = [index for index, count in enumerate(weeks) if count]
    if len(active) < 3:
        return None, 'fewer_than_three_active_release_weeks'
    median_gap = float(median(right - left for left, right in zip(active, active[1:])))
    since = 26 - active[-1]
    features = [sum(weeks[-4:]), sum(weeks[-12:]), sum(weeks), len(active), since, median_gap, since / max(1.0, median_gap)]
    return {'repository_id': record['repository_id'], 'repository': record['selected_full_name'],
            'features': features, 'actual': int(future == 0), 'gap_rule': float(since >= 2 * median_gap)}, None


def summary(y, prediction):
    import numpy as np
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

    both = len(np.unique(y)) == 2
    return {'brier': float(brier_score_loss(y, prediction)),
            'roc_auc': float(roc_auc_score(y, prediction)) if both else None,
            'pr_auc': float(average_precision_score(y, prediction)) if both else None}


def main():
    import joblib
    import numpy as np

    parser = argparse.ArgumentParser()
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--collection', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    if digest(args.manifest) != protocol['manifest_sha256'] or digest(args.model) != protocol['model_sha256']:
        raise ValueError('冻结清单或模型哈希不一致')
    if json.loads((args.collection / 'manifest.json').read_text())['protocol_sha256'] != digest(args.protocol):
        raise ValueError('采集记录不属于冻结方案')
    manifest = json.loads(args.manifest.read_text())
    expected = {item['repository_id'] for item in manifest['repositories']}
    files = list((args.collection / 'repositories').glob('*.json'))
    if {int(path.stem) for path in files} != expected:
        raise ValueError('仓库采集文件不完整或有额外记录')
    rows, excluded = [], Counter()
    for path in files:
        record = json.loads(path.read_text())
        if record['repository_id'] != int(path.stem):
            raise ValueError('仓库身份不一致')
        row, reason = sample(record, protocol)
        if reason:
            excluded[reason] += 1
        else:
            rows.append(row)
    rows.sort(key=lambda row: row['repository_id'])
    result = {'status': 'research_only', 'evaluation_type': 'new_unseen_repositories_retrospective_snapshot',
              'selected_repositories': len(expected), 'eligible_repositories': len(rows), 'excluded': dict(excluded),
              'positive_repositories': sum(row['actual'] for row in rows), 'approval_gate_passed': False,
              'limitations': ['Release 历史由当前可见快照重建，不能确认历史删除、草稿和修改。',
                              '每个仓库只评估一个时点；该结果不是独立时点的生产验收。'],
              'protocol_sha256': digest(args.protocol), 'model_sha256': digest(args.model)}
    if rows:
        x = np.asarray([row['features'] for row in rows], dtype=float)
        y = np.asarray([row['actual'] for row in rows], dtype=int)
        model = joblib.load(args.model)['model']
        prediction = model.predict_proba(x)[:, 1]
        base = np.full(len(rows), protocol['baseline_training_prevalence'])
        rule = np.asarray([row['gap_rule'] for row in rows], dtype=float)
        result['metrics'] = {'candidate': summary(y, prediction), 'training_prevalence': summary(y, base), 'gap_rule': summary(y, rule)}
        rng = np.random.default_rng(20261109)
        difference = (base - y) ** 2 - (prediction - y) ** 2
        boot = np.mean(difference[rng.integers(0, len(rows), size=(5000, len(rows)))], axis=1)
        result['brier_difference_baseline_minus_model_ci95'] = [float(v) for v in np.quantile(boot, [0.025, 0.975])]
        result['positive_support_sufficient_for_further_validation'] = int(y.sum()) >= protocol['minimum_independent_positive_repositories_for_further_validation']
        for row, probability in zip(rows, prediction):
            row['research_probability'] = float(probability)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'metrics.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    with (args.output / 'predictions.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['repository_id', 'repository', 'features', 'actual', 'gap_rule', 'research_probability'])
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
