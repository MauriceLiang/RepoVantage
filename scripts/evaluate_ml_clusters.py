#!/usr/bin/env python3
"""对历史仓库聚类做 bootstrap 和规模消融；不作为独立发布验收。"""
import argparse
import csv
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score, silhouette_score
from sklearn.preprocessing import StandardScaler


SEED = 20261109


def load_features(path):
    repositories = defaultdict(list)
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            repositories[int(row["repository_id"])].append(row)
    full, shape, sizes = [], [], []
    for repository_id, rows in sorted(repositories.items()):
        rows.sort(key=lambda item: item["period_start"])
        if len(rows) != 52 or not all(row["commit_coverage"] in {"complete", "true_zero"} and row["pr_opened_coverage"] in {"complete", "true_zero"} for row in rows):
            continue
        vectors, pattern = [], []
        for field in ("commits_observed", "pr_opened"):
            series = np.asarray([int(row[field]) for row in rows], dtype=float)
            vectors.extend([np.log1p(series.mean()), np.mean(series == 0), np.log1p(series.std())])
            pattern.extend([np.mean(series == 0), np.log1p(series.std() / (series.mean() + 1))])
        full.append(vectors)
        shape.append(pattern)
        sizes.append(sum(int(row["commits_observed"]) + int(row["pr_opened"]) for row in rows))
    if len(full) < 20:
        raise ValueError("可用仓库不足以评估聚类稳定性")
    return np.asarray(full), np.asarray(shape), np.asarray(sizes)


def analyze(x, sizes, repetitions):
    normalized = StandardScaler().fit_transform(x)
    candidates = {}
    fitted = {}
    for k in range(2, 7):
        model = KMeans(n_clusters=k, n_init=20, random_state=SEED).fit(normalized)
        fitted[k] = model
        candidates[str(k)] = {"silhouette": float(silhouette_score(normalized, model.labels_)),
                              "sizes": [int(np.sum(model.labels_ == index)) for index in range(k)]}
    k = max(fitted, key=lambda value: candidates[str(value)]["silhouette"])
    labels = fitted[k].labels_
    rng = np.random.default_rng(SEED)
    scores = []
    for index in range(repetitions):
        selected = rng.integers(0, len(x), size=len(x))
        oob = np.setdiff1d(np.arange(len(x)), np.unique(selected))
        scaler = StandardScaler().fit(x[selected])
        model = KMeans(n_clusters=k, n_init=10, random_state=SEED + index).fit(scaler.transform(x[selected]))
        scores.append(float(adjusted_rand_score(labels[oob], model.predict(scaler.transform(x[oob])))))
    size_bins = np.digitize(sizes, np.quantile(sizes, [1 / 3, 2 / 3]), right=True)
    keep = sizes <= np.quantile(sizes, 0.95)
    scaler = StandardScaler().fit(x[keep])
    without_largest = KMeans(n_clusters=k, n_init=20, random_state=SEED).fit(scaler.transform(x[keep]))
    return {"selected_k": k, "candidates": candidates, "bootstrap_oob_ari_mean": float(np.mean(scores)),
            "bootstrap_oob_ari_p05": float(np.quantile(scores, 0.05)),
            "activity_size_tercile_nmi": float(normalized_mutual_info_score(labels, size_bins)),
            "drop_top_5pct_activity_ari": float(adjusted_rand_score(labels[keep], without_largest.labels_)),
            "bootstrap_repetitions": repetitions}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weekly", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=50)
    args = parser.parse_args()
    if args.output.exists() or args.bootstrap < 1:
        parser.error("输出必须是新文件，bootstrap 次数必须为正")
    full, shape, sizes = load_features(args.weekly)
    result = {"status": "research_only", "evaluation_type": "historical_diagnostic_not_independent_test", "repositories": len(full),
              "seed": SEED, "source_sha256": hashlib.sha256(args.weekly.read_bytes()).hexdigest(),
              "scale_and_shape": analyze(full, sizes, args.bootstrap), "shape_only": analyze(shape, sizes, args.bootstrap),
              "limitations": ["同一批历史仓库已用于模型开发；bootstrap 不是新的独立验收。", "聚类缺少人工业务画像复核，不能用于质量分级。"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"repositories": len(full), "scale_and_shape": result["scale_and_shape"], "shape_only": result["shape_only"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
