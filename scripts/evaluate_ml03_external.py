#!/usr/bin/env python3
"""对预先冻结的外部仓库执行一次 ML-03 验证；绝不自动批准模型。"""
import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import silhouette_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.analytics.maintenance_features import SCALE_NAMES, SHAPE_NAMES, build_maintenance_features  # noqa: E402
from scripts.ml03_feature_parity import equivalent  # noqa: E402


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def silhouette(values, labels):
    return float(silhouette_score(values, labels)) if 1 < len(set(labels)) < len(labels) else None


def main():
    parser = argparse.ArgumentParser()
    for name in ('manifest', 'lock', 'evaluator-lock', 'collection', 'protocol', 'development', 'output'):
        parser.add_argument(f'--{name}', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('正式外部评估结果已存在，禁止覆盖')
    evaluator_lock = json.loads(args.evaluator_lock.read_text())
    for filename, expected_hash in evaluator_lock['hashes'].items():
        if digest(ROOT/filename) != expected_hash:
            raise ValueError(f'评估代码哈希不一致：{filename}')
    lock = json.loads(args.lock.read_text())
    for filename, expected in lock['hashes'].items():
        if digest(ROOT/filename) != expected:
            raise ValueError(f'冻结文件哈希不一致：{filename}')
    if digest(args.manifest) != lock['hashes']['ml-production/manifests/ml03_external_holdout.json']:
        raise ValueError('外部名单不属于冻结版本')
    if json.loads((args.collection/'manifest.json').read_text())['lock_sha256'] != digest(args.lock):
        raise ValueError('外部采集不属于冻结版本')
    manifest, protocol = json.loads(args.manifest.read_text()), json.loads(args.protocol.read_text())
    expected = {item['repository_id'] for item in manifest['repositories']}
    paths = {int(path.stem): path for path in (args.collection/'repositories').glob('*.json')}
    if len(expected) != 60 or set(paths) != expected:
        raise ValueError('外部采集未完成或存在未冻结仓库')
    candidate = joblib.load(args.development/'model.joblib')
    baseline = joblib.load(args.development/'size_baseline.joblib')
    numeric = json.loads((args.development/'numeric_model.json').read_text())
    dev = json.loads((args.development/'metrics_development.json').read_text())
    rows, excluded = [], Counter()
    for item in manifest['repositories']:
        record = json.loads(paths[item['repository_id']].read_text())
        if record['repository_id'] != item['repository_id']:
            raise ValueError('外部仓库身份不一致')
        if record.get('status') != 'complete':
            excluded[record.get('status', 'missing')] += 1
            continue
        features = build_maintenance_features(record['weeks'])
        if not equivalent(features, record['features']) or features['as_of_utc'] != protocol['time_window']['end_exclusive']:
            raise ValueError('线上/离线特征或冻结时间窗不一致')
        rows.append({'repository_id': item['repository_id'], 'name': item['full_name'], 'stratum': item['stratum'],
                     'activity_proxy': item['activity_proxy'], 'features': features, 'capture_sha256': digest(paths[item['repository_id']])})
    if not rows:
        raise ValueError('无覆盖完整的外部仓库')
    names = candidate['feature_names']
    x = np.asarray([[row['features']['feature_values'][name] for name in names] for row in rows])
    z = candidate['pipeline'].named_steps['scale'].transform(x)
    labels = candidate['pipeline'].predict(x)
    centers = np.asarray(numeric['centers'])
    distances = np.linalg.norm(z - centers[labels], axis=1)
    radii = np.asarray(numeric['distance_p99'])[labels]
    bounded = np.all((x >= np.asarray(numeric['feature_min'])) & (x <= np.asarray(numeric['feature_max'])), axis=1)
    in_domain = bounded & (distances <= radii)
    x_size = np.asarray([[row['features']['feature_values'][name] for name in SCALE_NAMES] for row in rows])
    baseline_labels = baseline['pipeline'].predict(x_size)
    sizes = np.asarray([row['features']['evidence']['commits_52w'] + row['features']['evidence']['prs_created_52w'] for row in rows])
    bins = np.digitize(sizes, numeric['training_size_tertiles'], right=True)
    shape_indices = [names.index(name) for name in SHAPE_NAMES]
    shape_z = z[:, shape_indices]
    valid = np.flatnonzero(in_domain)
    candidate_sil = silhouette(shape_z[valid], labels[valid]) if len(valid) else None
    baseline_sil = silhouette(shape_z[valid], baseline_labels[valid]) if len(valid) else None
    mixed = 0
    for group in range(3):
        counts = Counter(int(label) for label in labels[in_domain & (bins == group)])
        mixed += sum(value >= 3 for value in counts.values()) >= 2
    improvement = candidate_sil - baseline_sil if candidate_sil is not None and baseline_sil is not None else None
    numerical = bool(dev['selected']['development_gate_passed'] and len(valid) >= protocol['external']['min_complete_and_in_domain']
                     and (60-len(valid))/60 <= protocol['external']['max_rejection_fraction']
                     and mixed >= 2 and improvement is not None and improvement >= .05)
    cluster_counts = Counter(str(int(label)) for label in labels[in_domain])
    review_groups = defaultdict(list)
    detailed = []
    for index, row in enumerate(rows):
        if not in_domain[index]:
            excluded['out_of_distribution'] += 1
        row.update(cluster=int(labels[index]), in_domain=bool(in_domain[index]), distance=float(distances[index]),
                   distance_limit=float(radii[index]), activity_bin=int(bins[index]), size_baseline_cluster=int(baseline_labels[index]))
        detailed.append(row)
        if in_domain[index]:
            region = 'center' if distances[index] <= radii[index]*.5 else 'boundary'
            key = (int(labels[index]), region, int(bins[index]))
            review_groups[key].append(row)
    for group in review_groups.values():
        group.sort(key=lambda row: hashlib.sha256(f"review:20261109:{row['repository_id']}".encode()).hexdigest())
    sample = []
    while len(sample) < 40 and any(review_groups.values()):
        for key in sorted(review_groups):
            if review_groups[key] and len(sample) < 40:
                sample.append(review_groups[key].pop(0))
    summaries = {}
    for cluster in sorted(cluster_counts):
        members = [row for row in detailed if row['in_domain'] and str(row['cluster']) == cluster]
        evidence = ('commits_52w','prs_created_52w','commit_active_weeks','pr_active_weeks','longest_zero_commit_weeks')
        summaries[cluster] = {'count': len(members), 'median_evidence': {key:float(np.median([row['features']['evidence'][key] for row in members])) for key in evidence}}
    result = {'status':'research_only', 'numerical_gate_passed':numerical, 'production_approved':False,
              'protocol_sha256':digest(args.protocol), 'lock_sha256':digest(args.lock), 'evaluator_lock_sha256':digest(args.evaluator_lock), 'model_sha256':digest(args.development/'numeric_model.json'),
              'manifest_sha256':digest(args.manifest), 'frozen_repositories':60, 'complete_repositories':len(rows),
              'in_domain_repositories':len(valid), 'excluded':dict(excluded), 'cluster_counts':dict(cluster_counts),
              'rejection_fraction':(60-len(valid))/60, 'mixed_activity_tertiles':int(mixed),
              'candidate_shape_silhouette':candidate_sil, 'size_baseline_shape_silhouette':baseline_sil,
              'shape_silhouette_gain':improvement, 'cluster_summaries':summaries, 'review_sample_count':len(sample),
              'human_review_status':'not_started', 'project_owner_decision':'not_recorded',
              'limitations':['Commit 和 PR 为采集时可见快照；不可重建历史时点已删除数据或默认分支成员关系。',
                             '两名真实独立复核者及负责人批准缺失，任何数值结果都不构成生产批准。']}
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    (args.output/'details.json').write_text(json.dumps(detailed,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    with (args.output/'human_review.csv').open('w', encoding='utf-8', newline='') as stream:
        fields = ['repository_id','repository','window_start','window_end','cluster','activity_bin','distance','distance_limit',
                  'commits_52w','prs_created_52w','commit_active_weeks','pr_active_weeks','longest_zero_commit_weeks',
                  'reviewer_a','reviewer_a_assessment','reviewer_a_reason','reviewer_b','reviewer_b_assessment','reviewer_b_reason','disagreement','arbitration']
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for row in sample:
            ev = row['features']['evidence']
            writer.writerow({'repository_id':row['repository_id'],'repository':row['name'],'window_start':protocol['time_window']['start'],
                             'window_end':protocol['time_window']['end_exclusive'],'cluster':row['cluster'],'activity_bin':row['activity_bin'],
                             'distance':row['distance'],'distance_limit':row['distance_limit'], **{key:ev[key] for key in fields if key in ev}})
    print(json.dumps(result,ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
