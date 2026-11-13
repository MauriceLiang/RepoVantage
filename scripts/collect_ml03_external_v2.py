#!/usr/bin/env python3
"""只读采集第二批冻结外部仓库；不读取候选模型或计算模型预测。"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from backend.app.core.exceptions import AppError
from backend.app.integrations.github.client import GitHubClient
from backend.app.services.maintenance_collection import collect_maintenance
from scripts.collect_ml_holdout import digest
from scripts.repair_issue_comments import atomic_json


def main():
    parser=argparse.ArgumentParser()
    for name in ('manifest','lock','output'): parser.add_argument(f'--{name}',type=Path,required=True)
    parser.add_argument('--max-pages',type=int,default=30);parser.add_argument('--delay',type=float,default=.5)
    args=parser.parse_args()
    if args.max_pages<1 or args.delay<0: parser.error('分页预算必须为正且延迟不能为负')
    lock=json.loads(args.lock.read_text())
    for filename,expected in lock['hashes'].items():
        if digest(Path(filename))!=expected: raise ValueError(f'冻结文件哈希不一致：{filename}')
    if digest(args.manifest)!=lock['hashes']['ml-production/manifests/ml03_external_holdout_v2.json']:
        raise ValueError('名单不属于冻结版本')
    manifest=json.loads(args.manifest.read_text());args.output.mkdir(parents=True,exist_ok=True)
    meta=args.output/'manifest.json'
    if meta.exists() and json.loads(meta.read_text())['lock_sha256']!=digest(args.lock): raise ValueError('输出目录属于其他冻结协议')
    if not meta.exists(): atomic_json(meta,{'lock_sha256':digest(args.lock),'repository_count':len(manifest['repositories']),'max_pages':args.max_pages})
    with GitHubClient(on_response=lambda _response:time.sleep(args.delay) if args.delay else None) as github:
        for item in manifest['repositories']:
            path=args.output/'repositories'/f"{item['repository_id']}.json"
            if path.exists(): continue
            try:
                result=collect_maintenance(github,item['repository_id'],end=datetime(2026,11,2),max_pages=args.max_pages)
                atomic_json(path,result);print(f"{item['repository_id']}: {result['status']}",flush=True)
                if any(v.get('error_code')=='GITHUB_RATE_LIMITED' for v in result.get('source_audits',{}).values()):
                    raise SystemExit('GitHub 限流；已保存断点。')
            except AppError as exc:
                if exc.code=='GITHUB_RATE_LIMITED': raise SystemExit('GitHub 限流；已保存断点。') from exc
                atomic_json(path,{'repository_id':item['repository_id'],'status':'partial','error_code':exc.code})
                print(f"{item['repository_id']}: {exc.code}",flush=True)


if __name__=='__main__':main()
