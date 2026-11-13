#!/usr/bin/env python3
"""依据冻结的训练集规则选择低规模混杂的 ML-03 时间形态候选。"""
import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.analytics.maintenance_features import SCALE_NAMES  # noqa: E402
from backend.app.analytics.maintenance_features_v2 import SCHEMA_VERSION  # noqa: E402
from scripts.train_ml03 import SEED, digest, pipeline, silhouette, size_bins, within_bins  # noqa: E402
from scripts.train_ml03_v2 import load  # noqa: E402


def train_metrics(x, sizes, k, repetitions):
    fitted=pipeline(k).fit(x); labels=fitted.predict(x); scaled=fitted.named_steps['scale'].transform(x)
    rng=np.random.default_rng(SEED+100*k); aris=[]
    for index in range(repetitions):
        sampled=rng.integers(0,len(x),size=len(x)); oob=np.setdiff1d(np.arange(len(x)),np.unique(sampled))
        alternative=pipeline(k,SEED+index+1,10).fit(x[sampled])
        aris.append(float(adjusted_rand_score(labels[oob],alternative.predict(x[oob]))))
    bounds=np.quantile(sizes,[1/3,2/3]); groups=size_bins(sizes,bounds)
    nmi=float(normalized_mutual_info_score(labels,groups)); counts=[int(np.sum(labels==i)) for i in range(k)]
    sil=silhouette(scaled,labels); p05=float(np.quantile(aris,.05)); mixed=within_bins(labels,groups)
    passes=bool(p05>=.70 and nmi<=.55 and min(counts)/len(x)>=.08 and sil is not None and sil>=.20 and mixed>=2)
    return {'k':k,'counts':counts,'train_silhouette':sil,'bootstrap_oob_ari_p05':p05,
            'bootstrap_oob_ari_mean':float(np.mean(aris)),'bootstrap_oob_ari':aris,'size_tertile_nmi':nmi,
            'train_mixed_size_tertiles':mixed,'train_gate_passed':passes},fitted


def main():
    p=argparse.ArgumentParser()
    for name in ('weekly','train-manifest','protocol','output'): p.add_argument(f'--{name}',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists(): raise FileExistsError(a.output)
    protocol=json.loads(a.protocol.read_text()); split=json.loads(a.train_manifest.read_text())
    if digest(a.train_manifest)!=protocol['train_manifest_sha256']: raise ValueError('训练切分不匹配')
    data,excluded=load(a.weekly)
    train=[r for r in split['train_repository_ids'] if r in data]; valid=[r for r in split['validation_repository_ids'] if r in data]
    if len(train)<60 or len(valid)<30 or set(train)&set(valid): raise ValueError('训练或验证样本不足')
    matrix=lambda ids,names: np.asarray([[data[r]['features']['feature_values'][name] for name in names] for r in ids],dtype=float)
    size=lambda ids:np.asarray([data[r]['features']['evidence']['commits_52w']+data[r]['features']['evidence']['prs_created_52w'] for r in ids])
    train_sizes,valid_sizes=size(train),size(valid)
    candidates=[]; models={}
    for subset,names in protocol['feature_subsets'].items():
        x=matrix(train,names)
        for k in protocol['training']['candidate_k']:
            metric,model=train_metrics(x,train_sizes,k,protocol['training']['bootstrap_repetitions'])
            metric['feature_subset']=subset;metric['feature_names']=names
            candidates.append(metric);models[(subset,k)]=model
    passing=[r for r in candidates if r['train_gate_passed']]
    if passing:
        chosen=max(passing,key=lambda r:(r['train_silhouette'],-r['k'],r['feature_subset']))
    else:
        chosen=max(candidates,key=lambda r:(r['bootstrap_oob_ari_p05'],r['train_silhouette'] or -1,-r['k']))
    names=chosen['feature_names'];model=models[(chosen['feature_subset'],chosen['k'])]
    x=matrix(train,names);z=model.named_steps['scale'].transform(x);labels=model.predict(x)
    valid_x=matrix(valid,names);valid_labels=model.predict(valid_x);valid_z=model.named_steps['scale'].transform(valid_x)
    bounds=np.quantile(train_sizes,[1/3,2/3]); validation_sil=silhouette(valid_z,valid_labels)
    validation_mixed=within_bins(valid_labels,size_bins(valid_sizes,bounds))
    dev_gate=bool(chosen['train_gate_passed'] and validation_sil is not None and validation_sil>=.20 and validation_mixed>=2)
    centers=model.named_steps['cluster'].cluster_centers_;distances=np.linalg.norm(z-centers[labels],axis=1)
    radii=[float(np.quantile(distances[labels==i],.99)) for i in range(chosen['k'])]
    baseline=pipeline(2).fit(matrix(train,SCALE_NAMES))
    a.output.mkdir(parents=True,exist_ok=False)
    joblib.dump({'pipeline':model,'feature_names':names,'status':'research_only'},a.output/'model.joblib')
    joblib.dump({'pipeline':baseline,'feature_names':list(SCALE_NAMES),'status':'research_only'},a.output/'size_baseline.joblib')
    numeric={'format':'trusted-numeric-kmeans-v1','status':'research_only','feature_schema_version':SCHEMA_VERSION,'feature_names':names,
             'scale_mean':model.named_steps['scale'].mean_.tolist(),'scale_scale':model.named_steps['scale'].scale_.tolist(),
             'centers':centers.tolist(),'distance_p99':radii,'feature_min':x.min(axis=0).tolist(),'feature_max':x.max(axis=0).tolist(),
             'training_size_tertiles':bounds.tolist(),'applicability':{'commits_52w_min':20,'prs_created_52w_min':10}}
    (a.output/'numeric_model.json').write_text(json.dumps(numeric,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    profiles={}
    for label in range(chosen['k']):
        indices=np.flatnonzero(labels==label);ordered=indices[np.argsort(distances[indices])]
        evidence=('commits_52w','prs_created_52w','commit_active_weeks','pr_active_weeks','longest_zero_commit_weeks')
        profiles[str(label)]={'count':len(indices),'description':'未经过真人审核的中性聚类编号',
            'median_evidence':{key:float(np.median([data[train[i]]['features']['evidence'][key] for i in indices])) for key in evidence},
            'center_repositories':[{'id':train[i],'name':data[train[i]]['name']} for i in ordered[:3]],
            'boundary_repositories':[{'id':train[i],'name':data[train[i]]['name']} for i in ordered[-3:]]}
    selected={**chosen,'validation_silhouette':validation_sil,'validation_mixed_size_tertiles':validation_mixed,'development_gate_passed':dev_gate}
    (a.output/'metrics_development.json').write_text(json.dumps({'status':'research_only','selected':selected,'candidates':candidates,
        'train_repositories':len(train),'validation_repositories':len(valid),'excluded_historical_repositories':excluded,'profiles':profiles},ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    files={'protocol_sha256':a.protocol,'train_manifest_sha256':a.train_manifest,'weekly_sha256':a.weekly,
           'training_script_sha256':Path(__file__),'training_helpers_sha256':ROOT/'scripts/train_ml03.py',
           'training_loader_sha256':ROOT/'scripts/train_ml03_v2.py','feature_v1_sha256':ROOT/'backend/app/analytics/maintenance_features.py',
           'feature_v2_sha256':ROOT/'backend/app/analytics/maintenance_features_v2.py',
           'requirements_sha256':ROOT/'dataprepare/MachineLearn/research_s1/requirements.txt',
           'model_sha256':a.output/'model.joblib','numeric_model_sha256':a.output/'numeric_model.json',
           'size_baseline_sha256':a.output/'size_baseline.joblib'}
    manifest={key:digest(path) for key,path in files.items()}
    manifest.update(status='research_only',seed=SEED,train_repository_ids=train,validation_repository_ids=valid)
    (a.output/'training_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (a.output/'model_card.md').write_text(f"# ML-03 时间形态研究候选\n\n仅历史训练选择：{chosen['feature_subset']}，K={chosen['k']}；训练 {len(train)} 仓库、验证 {len(valid)} 仓库，开发门槛 {dev_gate}。\n\n适用范围：52 周完整覆盖且至少 20 次 Commit、10 个新建 PR。行为簇不是质量等级；历史分支成员关系不可回溯。未经过独立外部验收和真人复核，不能生产加载。\n",encoding='utf-8')
    print(json.dumps({'selected':selected,'train_repositories':len(train),'validation_repositories':len(valid),'numeric_model_sha256':manifest['numeric_model_sha256']},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
