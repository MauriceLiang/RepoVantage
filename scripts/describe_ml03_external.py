#!/usr/bin/env python3
"""只描述已冻结的外部评估结果；不再运行预测或改变准入决定。"""
import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import ks_2samp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.train_ml03_v2 import load  # noqa: E402


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('weekly', 'development', 'evaluation', 'result-lock', 'diagnostics-lock', 'output'):
        parser.add_argument(f'--{name}', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('描述性诊断已存在，禁止覆盖')
    diagnostic_lock = json.loads(args.diagnostics_lock.read_text())
    if digest(Path(__file__)) != diagnostic_lock['script_sha256']:
        raise ValueError('描述性诊断代码与预先冻结的版本不一致')
    result_lock = json.loads(args.result_lock.read_text())
    for name, expected in result_lock['hashes'].items():
        if digest(ROOT/name) != expected:
            raise ValueError(f'正式结果哈希不一致：{name}')
    manifest = json.loads((args.development/'training_manifest.json').read_text())
    if digest(args.weekly) != manifest['weekly_sha256'] or manifest['weekly_sha256'] != diagnostic_lock['training_data_sha256']:
        raise ValueError('训练数据哈希不一致')
    details = json.loads((args.evaluation/'details.json').read_text())
    metrics = json.loads((args.evaluation/'metrics.json').read_text())
    data, _ = load(args.weekly)
    train = [data[repo] for repo in manifest['train_repository_ids']]
    feature_names = json.loads((args.development/'numeric_model.json').read_text())['feature_names']
    drift = {}
    for name in feature_names:
        historical = [row['features']['feature_values'][name] for row in train]
        external = [row['features']['feature_values'][name] for row in details]
        valid = [row['features']['feature_values'][name] for row in details if row['in_domain']]
        quantiles = lambda values: [float(x) for x in np.quantile(values, [.1, .5, .9])] if values else None
        drift[name] = {'train_n':len(historical), 'train_p10_p50_p90':quantiles(historical),
                       'external_in_scope_n':len(external), 'external_p10_p50_p90':quantiles(external),
                       'in_domain_n':len(valid), 'in_domain_p10_p50_p90':quantiles(valid),
                       'ks_distance_all_in_scope':float(ks_2samp(historical, external).statistic) if external else None}
    grouped = defaultdict(list)
    for row in details:
        grouped[row['stratum'].split(':', 1)[0]].append(row)
    languages = {}
    for language, rows in sorted(grouped.items()):
        eligible = [row for row in rows if row['in_domain']]
        languages[language] = {'in_scope':len(rows), 'in_domain':len(eligible),
                               'out_of_distribution':len(rows)-len(eligible),
                               'clusters':dict(Counter(str(row['cluster']) for row in eligible))}
    development = json.loads((args.development/'metrics_development.json').read_text())
    profiles = {key:{'training':value['median_evidence'], 'external':metrics['cluster_summaries'].get(key)}
                for key, value in development['profiles'].items()}
    rule_counts = {name:defaultdict(Counter) for name in ('size', 'continuity', 'active_variation')}
    rule_examples = []
    for row in details:
        if not row['in_domain']:
            continue
        evidence = row['features']['evidence']
        values = row['features']['feature_values']
        lower_active_weeks = min(evidence['commit_active_weeks'], evidence['pr_active_weeks'])
        variability = (math.expm1(values['commit_active_cv']) + math.expm1(values['pr_active_cv'])) / 2
        rules = {'size':f"training_tertile_{row['activity_bin']+1}",
                 'continuity':'both_at_least_39_weeks' if lower_active_weeks >= 39 else
                              'both_at_least_13_weeks' if lower_active_weeks >= 13 else 'at_least_one_below_13_weeks',
                 'active_variation':'below_0.5' if variability < .5 else '0.5_to_1' if variability < 1 else 'at_least_1'}
        for name, value in rules.items():
            rule_counts[name][value][str(row['cluster'])] += 1
        rule_examples.append({'repository_id':row['repository_id'], 'repository':row['name'], 'cluster':row['cluster'],
                              'rules':rules, 'evidence':evidence})
    result = {'kind':'descriptive_only', 'does_not_change_numerical_gate':True, 'feature_distributions':drift,
              'languages':languages, 'train_and_external_profiles':profiles,
              'rule_baseline':{'definition':'规模使用训练集三分位；连续性使用 Commit 与 PR 各自活跃周的较小值，固定阈值 13/39 周；波动使用两种事件在活跃周的变异系数均值，固定阈值 0.5/1。规则不是质量等级或聚类真值。',
                               'cluster_counts':{name:{label:dict(counts) for label,counts in groups.items()} for name,groups in rule_counts.items()},
                               'examples':rule_examples},
              'limitations':['分层样本量较小，KS 距离是描述性分布差异，不是显著性或泛化保证。',
                             '语言来自冻结样本分层；未见语言或项目类型的适用性尚未验证。',
                             '仅对原结果作一次描述；不重新预测、不依据结果更改模型或阈值。']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status':'complete','features':feature_names,'languages':len(languages)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
