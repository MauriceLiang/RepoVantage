#!/usr/bin/env python3
"""按第二份冻结协议只使用历史训练/验证仓库，研究规模无关的时序形态。"""
import argparse
import csv
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

import joblib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.analytics.maintenance_features import InsufficientMaintenanceData, SCALE_NAMES  # noqa: E402
from backend.app.analytics.maintenance_features_v2 import SCHEMA_VERSION, TEMPORAL_NAMES, build_temporal_features  # noqa: E402
from scripts.train_ml03 import SEED, analyze, digest  # noqa: E402

FEATURES = {'A':SCALE_NAMES, 'B2':SCALE_NAMES + TEMPORAL_NAMES, 'D':TEMPORAL_NAMES}


def load(path):
    grouped = defaultdict(list)
    with gzip.open(path, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream): grouped[int(row['repository_id'])].append(row)
    result, excluded = {}, {}
    for repository_id, rows in grouped.items():
        rows.sort(key=lambda row: row['period_start'])
        weeks = [{'week_start_utc':r['period_start'], 'week_end_exclusive_utc':r['period_end'], 'commits':int(r['commits_observed']),
                  'prs_created':int(r['pr_opened']), 'commit_coverage':r['commit_coverage'], 'pr_created_coverage':r['pr_opened_coverage']} for r in rows]
        try:
            result[repository_id] = {'name':rows[0]['repository'], 'features':build_temporal_features(weeks)}
        except InsufficientMaintenanceData as exc:
            excluded[repository_id] = exc.reason
    return result, excluded


def main():
    parser = argparse.ArgumentParser()
    for name in ('weekly','train-manifest','protocol','output'):
        parser.add_argument(f'--{name}',type=Path,required=True)
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError(args.output)
    protocol = json.loads(args.protocol.read_text())
    if digest(args.train_manifest) != protocol['train_manifest_sha256']:
        raise ValueError('历史训练切分不匹配')
    split = json.loads(args.train_manifest.read_text())
    data, excluded = load(args.weekly)
    train = [repo for repo in split['train_repository_ids'] if repo in data]
    valid = [repo for repo in split['validation_repository_ids'] if repo in data]
    if len(train) < 60 or len(valid) < 30 or set(train) & set(valid):
        raise ValueError('适用范围内的训练或验证仓库不足')
    matrix = lambda ids,names: np.asarray([[data[repo]['features']['feature_values'][name] for name in names] for repo in ids],dtype=float)
    size = lambda ids: np.asarray([data[repo]['features']['evidence']['commits_52w'] + data[repo]['features']['evidence']['prs_created_52w'] for repo in ids])
    train_sizes, valid_sizes = size(train), size(valid)
    candidates, models = [], {}
    for group,names in FEATURES.items():
        x,y = matrix(train,names),matrix(valid,names)
        for k in range(2,7):
            row,model = analyze(group,k,x,y,train_sizes,valid_sizes,protocol['training']['bootstrap_repetitions'])
            candidates.append(row); models[(group,k)] = model
    eligible = [row for row in candidates if row['feature_set'] != 'A' and row['development_gate_passed']]
    if eligible:
        for group in ('D','B2'):
            choices = [row for row in eligible if row['feature_set']==group]
            if choices:
                chosen=max(choices,key=lambda row:(row['validation_silhouette'],-row['k']));break
    else:
        chosen=max((row for row in candidates if row['feature_set']!='A'),
                   key=lambda row:(row['bootstrap_oob_ari_p05'],row['validation_silhouette'] or -1,-row['k']))
    group,k=chosen['feature_set'],chosen['k']
    selected=models[(group,k)]; baseline=models[('A',2)]
    x=matrix(train,FEATURES[group]); z=selected.named_steps['scale'].transform(x); labels=selected.predict(x)
    centers=selected.named_steps['cluster'].cluster_centers_; distances=np.linalg.norm(z-centers[labels],axis=1)
    radii=[float(np.quantile(distances[labels==index],.99)) for index in range(k)]
    args.output.mkdir(parents=True,exist_ok=False)
    joblib.dump({'pipeline':selected,'feature_names':list(FEATURES[group]),'status':'research_only'},args.output/'model.joblib')
    joblib.dump({'pipeline':baseline,'feature_names':list(FEATURES['A']),'status':'research_only'},args.output/'size_baseline.joblib')
    numeric={'format':'trusted-numeric-kmeans-v1','status':'research_only','feature_schema_version':SCHEMA_VERSION,
             'feature_names':list(FEATURES[group]),'scale_mean':selected.named_steps['scale'].mean_.tolist(),
             'scale_scale':selected.named_steps['scale'].scale_.tolist(),'centers':centers.tolist(),'distance_p99':radii,
             'feature_min':x.min(axis=0).tolist(),'feature_max':x.max(axis=0).tolist(),
             'training_size_tertiles':np.quantile(train_sizes,[1/3,2/3]).tolist(),
             'applicability':{'commits_52w_min':20,'prs_created_52w_min':10}}
    (args.output/'numeric_model.json').write_text(json.dumps(numeric,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    profiles={}
    for label in range(k):
        indices=np.flatnonzero(labels==label); ordered=indices[np.argsort(distances[indices])]
        keys=('commits_52w','prs_created_52w','commit_active_weeks','pr_active_weeks','longest_zero_commit_weeks')
        profiles[str(label)]={'count':len(indices),'description':'未经过人工审核的聚类编号，不是质量标签',
                              'median_evidence':{key:float(np.median([data[train[index]]['features']['evidence'][key] for index in indices])) for key in keys},
                              'center_repositories':[{'id':train[index],'name':data[train[index]]['name']} for index in ordered[:3]],
                              'boundary_repositories':[{'id':train[index],'name':data[train[index]]['name']} for index in ordered[-3:]]}
    (args.output/'metrics_development.json').write_text(json.dumps({'status':'research_only','selected':chosen,'candidates':candidates,
        'train_repositories':len(train),'validation_repositories':len(valid),'excluded_historical_repositories':excluded,'profiles':profiles},ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    files={'protocol_sha256':args.protocol,'train_manifest_sha256':args.train_manifest,'weekly_sha256':args.weekly,
           'training_script_sha256':Path(__file__),'training_helpers_sha256':ROOT/'scripts/train_ml03.py',
           'feature_v1_sha256':ROOT/'backend/app/analytics/maintenance_features.py',
           'feature_v2_sha256':ROOT/'backend/app/analytics/maintenance_features_v2.py',
           'requirements_sha256':ROOT/'dataprepare/MachineLearn/research_s1/requirements.txt',
           'model_sha256':args.output/'model.joblib','numeric_model_sha256':args.output/'numeric_model.json',
           'size_baseline_sha256':args.output/'size_baseline.joblib'}
    manifest={key:digest(path) for key,path in files.items()}
    manifest.update(status='research_only',seed=SEED,train_repository_ids=train,validation_repository_ids=valid,
                    decision='无人工复核和负责人批准；不能生产加载。')
    (args.output/'training_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (args.output/'model_card.md').write_text(f"# ML-03 时序形态研究候选\n\n状态 research_only；历史训练 {len(train)} 仓库，验证 {len(valid)} 仓库；特征 {group}，K={k}。开发门槛：{chosen['development_gate_passed']}。\n\n仅适用于 52 周完整覆盖、至少 20 次 Commit 和 10 个新建 PR 的仓库。归一化时序特征不等于质量，快照不能复原过去分支成员关系；需新的外部测试、真实双人复核和负责人批准。\n",encoding='utf-8')
    print(json.dumps({'selected':chosen,'train_repositories':len(train),'validation_repositories':len(valid),'numeric_model_sha256':manifest['numeric_model_sha256']},ensure_ascii=False),flush=True)


if __name__ == '__main__': main()
