# 机器学习历史实验复现与数据切分

日期：2026-11-09。工作区基于 Git commit `311f3c40e9ec8fd34ea415107050d41e23fa2c00`，其上包含未提交更改；训练和评估产物均写入新的目录，没有覆盖原有运行。

## 复现结果

历史的周活动及 PR 覆盖审计、ML-01/02 活动、ML-03 聚类、ML-04 PR 合并、ML-05 Issue 回复、ML-06 异常和 ML-07/08 风险实验均重新运行。结果位于 `dataprepare/MachineLearn/run/p0-reproduction-v2/`。`verification.json` 对 8 份样本或预测数据做内容哈希，对 6 组已选方法及测试指标和仓库切分做比较，结果为 `pass`。gzip 容器时间戳可以不同，比较的是解压后的内容。这证明所列项目的复现，不代表所有模型已通过生产验证。ML-09 没有真实偏好标签，未训练。

原始研究脚本的环境及完整命令见 `dataprepare/MachineLearn/research_s1/README.md` 和 `dataprepare/MachineLearn/research_followup/README.md`。本次环境为 Python 3.11.9、NumPy 2.4.3、scikit-learn 1.9.1；训练前设置 `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`。可用新输出文件重复核验：

```bash
.venv/bin/python scripts/verify_ml_reproduction.py \
  --runs dataprepare/MachineLearn/run \
  --replay dataprepare/MachineLearn/run/p0-reproduction-v2 \
  --output /tmp/repovantage-reproduction-verification.json
```

## 切分与覆盖

[split_manifest.json](split_manifest.json) 保存历史 180/60/60 仓库 ID、历史验证及测试时点、数据哈希，以及另外冻结的 45 个未参与上述实验的候选仓库。历史测试结果此前已被查看，状态固定为 `historical_evaluation`。

新 45 仓库来自原候选池，以语言与 Star 的 15 个分层各选 3 个，固定哈希排序，排除原有 300 仓库。ML-01 的模型哈希和候选清单在评分前冻结；部分采集在冻结模型哈希前已开始，但尚未计算新留出集性能。使用当前默认分支重建 2026-10-05 的历史特征，不能证明提交当时已经进入默认分支，因此这是**新仓库的回溯诊断**，不能代替严格时点独立验收。

另已从候选池冻结一批与上述 345 个仓库不重叠的 45 个仓库，记录实际采集时的默认分支 SHA，并在未来结果发生之前冻结 ML-01 与两个统计基线的影子预测：40 个快照覆盖完整，5 个覆盖不确定。预测及各快照哈希位于 `dataprepare/MachineLearn/run/p0-reproduction-v2/prospective_shadow_predictions.json`，名单和预设评估规则为同目录的 `prospective_shadow_manifest.json` 与 `prospective_shadow_protocol.json`。目标窗口为 **2026-11-09 14:08 UTC 至 2026-12-07 14:08 UTC**；未来标签尚未成熟。非周一预测起点须单独验证，且目标结束时仍须获取可证明时点的分支状态；本次没有设置自动采集任务，不能假定届时会自动产生有效标签或完成评估。

覆盖矩阵及 manifest 为 `dataprepare/MachineLearn/run/p0-reproduction-v2/coverage_matrix.parquet` 和 `coverage_matrix_manifest.json`，共 300 行；特征口径见 [feature_registry.yaml](feature_registry.yaml)。`source_usable` 只是字段覆盖筛选，不是模型发布批准。`sgl-project/sglang` 的可用 Commit、PR 创建模块不会因 PR 更新缺口被整体剔除；`renovatebot/renovate` 的 Release 失败不影响其他已证明完整的模块。所有 `dataprepare` 数据和研究产物受当前 `.gitignore` 忽略，分享或备份时需一并保全，不能只带 Git 代码。

## 限制

原始 Issue 评论和当前默认分支快照都无法充分还原历史时点。按现有数据重跑 ML-05 只能复现历史研究，不能视为修复后重新训练；新的可信负例需要可核对的历史事件或未来前瞻观察。见 [data_repair_audit.md](data_repair_audit.md) 与 [model_release_decisions.md](model_release_decisions.md)。
