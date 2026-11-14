#!/usr/bin/env python3
"""仅在历史训练/验证仓库上训练并冻结一个研究态维护行为聚类候选。"""
import argparse
import csv
import gzip
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import joblib
import numpy as np
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score, silhouette_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.analytics.maintenance_features import SCALE_NAMES, SHAPE_NAMES, build_maintenance_features  # noqa: E402

SEED = 20261109
FEATURES = {'A': SCALE_NAMES, 'B': SCALE_NAMES + SHAPE_NAMES, 'C': SHAPE_NAMES}


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load(path):
    grouped = defaultdict(list)
    with gzip.open(path, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            grouped[int(row['repository_id'])].append(row)
    result = {}
    for repository_id, rows in grouped.items():
        rows.sort(key=lambda row: row['period_start'])
        weeks = [{'week_start_utc': r['period_start'], 'week_end_exclusive_utc': r['period_end'],
                  'commits': int(r['commits_observed']), 'prs_created': int(r['pr_opened']),
                  'commit_coverage': r['commit_coverage'], 'pr_created_coverage': r['pr_opened_coverage']} for r in rows]
        result[repository_id] = {'name': rows[0]['repository'], 'features': build_maintenance_features(weeks)}
    return result


def pipeline(k, seed=SEED, n_init=20):
    return Pipeline([('scale', StandardScaler()), ('cluster', KMeans(n_clusters=k, random_state=seed, n_init=n_init))])


def silhouette(x, labels):
    return float(silhouette_score(x, labels)) if 1 < len(set(labels)) < len(labels) else None


def size_bins(sizes, bounds):
    return np.digitize(sizes, bounds, right=True)


def within_bins(labels, groups):
    qualified = 0
    for group in range(3):
        counts = Counter(int(value) for value in labels[groups == group])
        qualified += sum(count >= 3 for count in counts.values()) >= 2
    return int(qualified)


def analyze(name, k, x_train, x_valid, sizes_train, sizes_valid, repetitions):
    fitted = pipeline(k).fit(x_train)
    train_labels = fitted.predict(x_train)
    valid_labels = fitted.predict(x_valid)
    scaler = fitted.named_steps['scale']
    train_z, valid_z = scaler.transform(x_train), scaler.transform(x_valid)
    rng = np.random.default_rng(SEED + 100 * k)
    aris = []
    for index in range(repetitions):
        sampled = rng.integers(0, len(x_train), size=len(x_train))
        oob = np.setdiff1d(np.arange(len(x_train)), np.unique(sampled))
        resampled = pipeline(k, SEED + index + 1, 10).fit(x_train[sampled])
        aris.append(float(adjusted_rand_score(train_labels[oob], resampled.predict(x_train[oob]))))
    bounds = np.quantile(sizes_train, [1/3, 2/3])
    nmi = float(normalized_mutual_info_score(train_labels, size_bins(sizes_train, bounds)))
    train_counts = [int(np.sum(train_labels == label)) for label in range(k)]
    val_sil = silhouette(valid_z, valid_labels)
    ari_p05 = float(np.quantile(aris, .05))
    bins_qualified = within_bins(valid_labels, size_bins(sizes_valid, bounds))
    eligible = bool(name != 'A' and ari_p05 >= .70 and min(train_counts) / len(train_labels) >= .08 and nmi <= .55
                    and val_sil is not None and val_sil >= .20 and bins_qualified >= 2)
    ward = AgglomerativeClustering(n_clusters=k, linkage='ward').fit_predict(train_z)
    return {'feature_set': name, 'k': k, 'train_counts': train_counts,
            'validation_counts': [int(np.sum(valid_labels == label)) for label in range(k)],
            'train_silhouette': silhouette(train_z, train_labels), 'validation_silhouette': val_sil,
            'bootstrap_oob_ari_mean': float(np.mean(aris)), 'bootstrap_oob_ari_p05': ari_p05,
            'bootstrap_oob_ari': aris, 'size_tertile_nmi': nmi, 'validation_mixed_size_tertiles': bins_qualified,
            'ward_ari': float(adjusted_rand_score(train_labels, ward)), 'development_gate_passed': eligible}, fitted


def main():
    parser = argparse.ArgumentParser()
    for name in ('weekly', 'train-manifest', 'protocol', 'output'):
        parser.add_argument(f'--{name}', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    protocol = json.loads(args.protocol.read_text())
    if digest(args.train_manifest) != protocol['train_manifest_sha256']:
        raise ValueError('训练切分与冻结协议不一致')
    split = json.loads(args.train_manifest.read_text())
    data = load(args.weekly)
    train, valid = split['train_repository_ids'], split['validation_repository_ids']
    if set(train) & set(valid) or not (set(train) | set(valid)).issubset(data):
        raise ValueError('训练/验证仓库不一致或发生重叠')
    values = lambda ids, names: np.asarray([[data[repo]['features']['feature_values'][name] for name in names] for repo in ids], dtype=float)
    sizes = lambda ids: np.asarray([data[repo]['features']['evidence']['commits_52w'] + data[repo]['features']['evidence']['prs_created_52w'] for repo in ids])
    train_sizes, valid_sizes = sizes(train), sizes(valid)
    metrics, fitted = [], {}
    for name, names in FEATURES.items():
        x_train, x_valid = values(train, names), values(valid, names)
        for k in range(2, 7):
            item, model = analyze(name, k, x_train, x_valid, train_sizes, valid_sizes, protocol['training']['bootstrap_repetitions'])
            metrics.append(item); fitted[(name, k)] = model
    eligible = [row for row in metrics if row['development_gate_passed']]
    if eligible:
        for name in ('C', 'B'):
            choices = [row for row in eligible if row['feature_set'] == name]
            if choices:
                chosen = max(choices, key=lambda row: (row['validation_silhouette'], -row['k']))
                break
    else:
        choices = [row for row in metrics if row['feature_set'] != 'A']
        chosen = max(choices, key=lambda row: (row['bootstrap_oob_ari_p05'], row['validation_silhouette'] or -1, -row['k']))
    name, k = chosen['feature_set'], chosen['k']
    selected = fitted[(name, k)]
    baseline = fitted[('A', 2)]
    x_train = values(train, FEATURES[name])
    z_train = selected.named_steps['scale'].transform(x_train)
    labels = selected.predict(x_train)
    centers = selected.named_steps['cluster'].cluster_centers_
    distance = np.linalg.norm(z_train - centers[labels], axis=1)
    radii = [float(np.quantile(distance[labels == label], .99)) for label in range(k)]
    profiles = {}
    for label in range(k):
        indices = np.flatnonzero(labels == label)
        ordered = indices[np.argsort(distance[indices])]
        evidence_keys = ('commits_52w','prs_created_52w','commit_active_weeks','pr_active_weeks','longest_zero_commit_weeks')
        profiles[str(label)] = {'count': len(indices), 'description': '未经过人工审核的聚类编号，不是质量标签',
                                'median_evidence': {key: float(np.median([data[train[index]]['features']['evidence'][key] for index in indices])) for key in evidence_keys},
                                'center_repositories': [{'id': train[index], 'name': data[train[index]]['name']} for index in ordered[:3]],
                                'boundary_repositories': [{'id': train[index], 'name': data[train[index]]['name']} for index in ordered[-3:]]}
    args.output.mkdir(parents=True, exist_ok=False)
    joblib.dump({'pipeline': selected, 'feature_names': list(FEATURES[name]), 'status': 'research_only'}, args.output/'model.joblib')
    joblib.dump({'pipeline': baseline, 'feature_names': list(FEATURES['A']), 'status': 'research_only'}, args.output/'size_baseline.joblib')
    safe = {'format': 'trusted-numeric-kmeans-v1', 'status': 'research_only', 'feature_schema_version': 'maintenance-shape-v1',
            'feature_names': list(FEATURES[name]), 'scale_mean': selected.named_steps['scale'].mean_.tolist(),
            'scale_scale': selected.named_steps['scale'].scale_.tolist(), 'centers': centers.tolist(), 'distance_p99': radii,
            'feature_min': x_train.min(axis=0).tolist(), 'feature_max': x_train.max(axis=0).tolist(),
            'training_size_tertiles': np.quantile(train_sizes, [1/3, 2/3]).tolist()}
    (args.output/'numeric_model.json').write_text(json.dumps(safe, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    (args.output/'metrics_development.json').write_text(json.dumps({'status':'research_only','selected':chosen,'candidates':metrics,
        'train_repositories':len(train),'validation_repositories':len(valid),'profiles':profiles}, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    feature_path = ROOT/'backend/app/analytics/maintenance_features.py'
    manifest = {'status':'research_only','protocol_sha256':digest(args.protocol),'train_manifest_sha256':digest(args.train_manifest),
                'weekly_sha256':digest(args.weekly),'training_script_sha256':digest(Path(__file__)), 'feature_module_sha256':digest(feature_path),
                'requirements_sha256':digest(ROOT/'dataprepare/MachineLearn/research_s1/requirements.txt'),
                'model_sha256':digest(args.output/'model.joblib'),'numeric_model_sha256':digest(args.output/'numeric_model.json'),
                'size_baseline_sha256':digest(args.output/'size_baseline.joblib'), 'seed':SEED,
                'decision':'候选仅供研究；外部验证、两名真人复核及负责人批准均未完成。'}
    (args.output/'training_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    (args.output/'model_card.md').write_text(f"# ML-03 研究候选\n\n状态：research_only。训练 {len(train)} 仓库、验证 {len(valid)} 仓库；特征集 {name}，K={k}。开发门槛：{chosen['development_gate_passed']}。\n\n输入为 52 个完整 UTC 周的可见默认分支 Commit 与全部状态 PR 创建量；当前分支快照不能复原过去分支成员关系。簇编号不是质量等级，不提供概率。独立外部验证、两名真实复核者及负责人批准均未完成，不得生产加载。\n", encoding='utf-8')
    print(json.dumps({'selected': chosen, 'model_sha256': manifest['model_sha256']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
