#!/usr/bin/env python3
"""以当前 Python 解释器生成历史 52 周时序特征，用于跨环境一致性检查。"""
import argparse
import csv
import gzip
import json
from collections import defaultdict
from pathlib import Path

from backend.app.analytics.maintenance_features import InsufficientMaintenanceData
from backend.app.analytics.maintenance_features_v2 import build_temporal_features


def export(source, output):
    grouped=defaultdict(list)
    with gzip.open(source,'rt',encoding='utf-8',newline='') as stream:
        for row in csv.DictReader(stream): grouped[int(row['repository_id'])].append(row)
    result={}
    for repository_id,rows in grouped.items():
        rows.sort(key=lambda row:row['period_start'])
        weeks=[{'week_start_utc':r['period_start'],'week_end_exclusive_utc':r['period_end'],
                'commits':int(r['commits_observed']),'prs_created':int(r['pr_opened']),
                'commit_coverage':r['commit_coverage'],'pr_created_coverage':r['pr_opened_coverage']} for r in rows]
        try: result[str(repository_id)]={'status':'available','features':build_temporal_features(weeks)}
        except InsufficientMaintenanceData as exc: result[str(repository_id)]={'status':'excluded','reason':exc.reason}
    with output.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,sort_keys=True,allow_nan=False);stream.write('\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--weekly',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();export(args.weekly,args.output)


if __name__=='__main__':main()
