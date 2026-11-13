#!/usr/bin/env python3
"""在外部特征或模型结果查看前，冻结 ML-03 候选池与验收协议。"""
import gzip
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'ml-production'
RUN = ROOT / 'dataprepare/MachineLearn/run/p0-reproduction-v2'
SOURCE = ROOT / 'dataprepare/MachineLearn/run/repo-evaluation-2026-v1'
RESERVES = ROOT / 'dataprepare/MachineLearn/ml-300-reserves.json'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    now = datetime.now(timezone.utc).isoformat()
    coverage = SOURCE / 'repository_module_coverage.jsonl.gz'
    historical = RUN / 'activity/manifest.json'
    old = RUN / 'unseen_holdout_manifest.json'
    shadow = RUN / 'prospective_shadow_manifest.json'
    predictions = RUN / 'prospective_shadow_predictions.json'
    protocol_path = OUT / 'protocols/ml03_release_protocol_v1.json'
    pool_path = OUT / 'manifests/ml03_external_pool.json'
    train_path = OUT / 'manifests/ml03_train_manifest.json'
    source_path = OUT / 'manifests/source_hashes.json'
    if any(path.exists() for path in (protocol_path, pool_path, train_path, source_path)):
        raise FileExistsError('冻结记录已存在；不得覆盖')
    split = json.loads(historical.read_text())['split_repository_ids']
    with gzip.open(coverage, 'rt', encoding='utf-8') as stream:
        excluded = {json.loads(line)['repository_id'] for line in stream}
    prior = set(excluded)
    for path in (old, shadow):
        ids = {item['repository_id'] for item in json.loads(path.read_text())['repositories']}
        if excluded & ids:
            raise ValueError('历史及前瞻仓库集合不独立')
        excluded.update(ids)
    groups = json.loads(RESERVES.read_text())['reserves']
    pool = []
    for group, items in sorted(groups.items()):
        candidates = [item for item in items if item['repository_id'] not in excluded]
        if len({item['repository_id'] for item in candidates}) < 4:
            raise ValueError(f'候选不足：{group}')
        for item in candidates:
            pool.append({'repository_id': item['repository_id'], 'full_name': item['full_name'],
                         'stratum': group, 'stars_at_original_snapshot': item.get('stars_at_snapshot')})
    if len({row['repository_id'] for row in pool}) != len(pool):
        raise ValueError('候选池跨层重复')
    write_new(pool_path, {'version': 'ml03-external-pool-v1', 'frozen_at': now, 'seed': 20261109,
                          'selection_population': '原保留候选，排除历史 300、ML-01 回溯 45 和前瞻 45；不按模型表现挑选。',
                          'exclusion_counts': {'historical': len(prior), 'total_previously_used': len(excluded)}, 'repositories': pool})
    write_new(train_path, {'version': 'ml03-train-split-v1', 'frozen_at': now,
                           'train_repository_ids': split['train'], 'validation_repository_ids': split['validation'],
                           'previously_viewed_test_repository_ids': split['test'],
                           'test_reuse_policy': '仅开发诊断，不能用于新外部验收；候选选择只使用 train 和 validation。',
                           'history_start': '2025-11-03T00:00:00Z', 'history_end_exclusive': '2026-11-02T00:00:00Z'})
    files = [coverage, historical, old, shadow, predictions, RESERVES, SOURCE/'repository_weekly_features.csv.gz',
             SOURCE/'capture_manifest.json', ROOT/'pyproject.toml', ROOT/'uv.lock', ROOT/'dataprepare/MachineLearn/research_s1/requirements.txt']
    write_new(source_path, {'frozen_at': now, 'git_commit': subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
                            'workspace_dirty': bool(subprocess.check_output(['git','status','--porcelain'], cwd=ROOT, text=True).strip()),
                            'source_sha256': {str(path.relative_to(ROOT)): sha(path) for path in files},
                            'pool_sha256': sha(pool_path), 'train_manifest_sha256': sha(train_path),
                            'note': '此提交上已有未提交变更；训练脚本和模型最终哈希将另外随模型保存。'})
    write_new(protocol_path, {
        'version': 'ml03-release-protocol-v1', 'frozen_at': now, 'seed': 20261109,
        'source_manifest_sha256': sha(source_path), 'pool_sha256': sha(pool_path), 'train_manifest_sha256': sha(train_path),
        'external_sampling': {'per_language_star_stratum': 4, 'target_repositories': 60,
                              'activity_proxy': 'profile pushed_at within 90 days of 2026-11-09T00:00:00Z; metadata only, not a model feature',
                              'selection_rule': '每层可用候选按固定哈希排序，尽量各取两名近期/非近期；某组不足时以同层剩余候选补足，不按模型表现替换。',
                              'metadata_failures': '保留失败记录；只在冻结前按上述固定规则从同层剩余候选补齐。'},
        'time_window': {'start': '2025-11-03T00:00:00Z', 'end_exclusive': '2026-11-02T00:00:00Z', 'weeks': 52, 'timezone': 'UTC'},
        'events': {'commits': 'committer timestamp, fallback author timestamp, on default branch SHA visible at collection',
                   'pull_requests': 'all states, created_at; creation-order pages until before window or terminal page'},
        'feature_sets': {'A': 'log1p commit total and log1p all-PR-created total',
                         'B': 'A plus shape features',
                         'C': 'shape features: commit and PR active-week fractions, commit longest zero-run fraction, log1p weekly CV with mean+1 smoothing, log1p clipped 12-week/previous-40-week smoothed mean ratio, log1p smoothed PR/commit ratio'},
        'training': {'fit': 'historical train IDs only; fit scaling and KMeans together',
                     'selection': 'historical validation IDs only; prefer C then B among qualifying candidates, select highest validation silhouette; if none qualify freeze the best stability candidate as research-only',
                     'candidate_k': [2,3,4,5,6], 'baseline': 'A size-only KMeans, and descriptive activity tertiles',
                     'comparison': 'Ward on train as diagnostic only; never used for online inference',
                     'bootstrap_repetitions': 50, 'bootstrap_unit': 'repository', 'oob_ari_p05_min': 0.70,
                     'min_train_cluster_fraction': 0.08, 'max_size_tertile_nmi': 0.55,
                     'validation_silhouette_min': 0.20, 'within_size_bins': 'at least two of three train-derived size tertiles have at least two clusters each with at least three members'},
        'external': {'min_frozen_repositories': 60, 'min_complete_and_in_domain': 40,
                     'max_rejection_fraction': 0.35, 'ood_rule': 'training-derived per-cluster 99th percentile standardized distance and feature ranges; reject rather than force assignment',
                     'nontrivial_gain': 'within at least two activity tertiles, at least two clusters have >=3 repositories, and shape-space silhouette exceeds size-only baseline by >=0.05',
                     'evaluation_reuse': 'only one formal evaluation per frozen model and holdout; failed results remain frozen',
                     'human_review': 'two actual independent humans review at least 40 eligible repositories, neutral descriptions and disagreements; project owner approval required',
                     'automatic_approval': False},
        'prohibitions': ['未通过人工审查、独立评估与负责人批准不得生产加载', '维护行为簇不是质量分数，不进入选型总分',
                         '不把当前分支快照伪称过去时点的默认分支成员关系', '不以无覆盖数据补零'],
    })
    print(json.dumps({'pool': len(pool), 'historical': len(prior), 'excluded': len(excluded), 'protocol_sha256': sha(protocol_path)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
