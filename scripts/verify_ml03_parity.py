#!/usr/bin/env python3
"""复核同一特征模块跨 Python 环境与已训练数值模型的输出一致性。"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import joblib
import numpy as np

from backend.app.ml.maintenance_numeric_worker import predict
from scripts.export_ml03_features import export
from scripts.ml03_feature_parity import equivalent

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser()
    for name in ('weekly','development','output'):p.add_argument(f'--{name}',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    with tempfile.TemporaryDirectory(prefix='repovantage-ml03-parity-') as directory:
        direct=Path(directory)/'research.json'; app=Path(directory)/'app.json'
        export(a.weekly,direct)
        subprocess.run([str(ROOT/'.venv/bin/python'),'-m','scripts.export_ml03_features','--weekly',str(a.weekly),'--output',str(app)],cwd=ROOT,check=True,timeout=60)
        left,right=json.loads(direct.read_text()),json.loads(app.read_text())
        if not equivalent(left,right):raise ValueError('训练与产品 Python 环境输出不同')
        numeric=json.loads((a.development/'numeric_model.json').read_text())
        candidate=joblib.load(a.development/'model.joblib')
        checked=outside=0
        for row in left.values():
            if row['status']!='available':continue
            features=row['features']['feature_values']; result=predict(numeric,features)
            if result['status']=='out_of_distribution':outside+=1;continue
            vector=np.asarray([[features[name] for name in candidate['feature_names']]])
            expected=int(candidate['pipeline'].predict(vector)[0])
            if result.get('cluster')!=expected:raise ValueError('数值推理与已训练 Pipeline 的聚类结果不一致')
            checked+=1
        if checked<1:raise ValueError('没有适用样本')
    result={'status':'pass','repositories_checked':len(left),'in_scope_numeric_predictions_compared':checked,
            'in_scope_but_out_of_distribution':outside,'tolerance':{'relative':1e-12,'absolute':1e-12},
            'note':'离线研究一致性检查，不构成人工批准或生产发布。'}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
