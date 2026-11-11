# RepoVantage 课程设计版机器学习实验结果与选型解释

更新日期：2026-11-10
最新收尾需求基线：`RepoVantage_机器学习课程设计收尾实施方案_v4.1.md`（训练背景沿用 v4.0）

## 结论

课程版只实现三个任务。维护模式聚类和未来 4 周活跃趋势分类通过本轮基础评估并接入产品；活动异常任务在产品中使用可解释的 MAD 规则，仅给出“疑似”提示。IsolationForest 作为对照实验保留，不作为正式异常预测。

这里的“可用”表示模型在既有样本的留仓验证上达到了课程演示的基础条件，不代表商业生产准入、对所有仓库都可靠或对未来分布有保证。趋势模型不输出概率或精确 Commit 数量。

## 数据与特征口径

- 输入复用既有 `repo-evaluation-2026-v1`：300 个仓库、每仓库连续 52 个周记录，共 15,600 行；没有启动新的 300 仓库全历史抓取。
- 输入文件：`dataprepare/MachineLearn/run/repo-evaluation-2026-v1/repository_weekly_features.csv.gz`。
- 输入 SHA-256：`5a463e44da2260d943a7851c872277984552fba3034e12eb8d5bb14c7c2c148d`。
- 线上与离线共同使用 `course-maintenance-12w-v1`：UTC 周边界、只用完整周、Commit 覆盖为必需、PR 创建量为可选；缺失周不填零。特征定义位于 `backend/app/analytics/course_ml_features.py`。
- 默认采集最近 12 个完整 UTC 周；界面可在仓库较老且 12 周活动稀疏或观察期短时请求最多 24 周。24 周只增加事实背景，模型仍读取最近 12 周。
- Worker 优先复用满足新鲜度、覆盖区间和仓库更新时间检查的本地完整 Commit 聚合；否则只分页读取请求窗口，并按 UTC 周聚合。PR 使用按周搜索计数；超过搜索上限或结果不完整时标为覆盖不完整。没有读取 PR 正文，也没有扫描完整提交历史。
- 在线 Commit 口径是当前默认分支可见记录，时间优先使用 committer date，缺失时回退 author date；它不能复原所有历史分支在当时的成员关系。

训练、评估、候选选择由 `scripts/train_course_ml.py` 完成。固定随机种子为 `20261110`，按仓库分成训练 210、验证 45、留出测试 45。该 300 仓库样本曾用于早期研究；本轮是按新特征与新任务定义重新设计的历史回测，不是全新独立数据集。

## M1：维护模式聚类

**输入与算法**：每仓库最近 12 周的 Commit 活跃周比例、`log1p` 活动波动、最长无活动周比例、近期变化、前两周集中度。采用 `StandardScaler + KMeans`；不完整 PR 不会伪装成零并送入模型，因此当前上线的是已单独验证的 Commit-only 版本。

| K | 验证轮廓系数 | 仅按规模分组基线 | 与 Commit 规模三分位 NMI | 三次种子 ARI |
|---:|---:|---:|---:|---|
| 2 | 0.4025 | 0.2537 | 0.3540 | 1.000 / 1.000 / 1.000 |
| 3 | 0.4738 | 0.1407 | 0.4347 | 1.000 / 1.000 / 1.000 |
| 4 | **0.4780** | **0.0922** | 0.3483 | 0.972 / 1.000 / 1.000 |

选择 K=4：验证轮廓系数最高、超过规模基线，簇划分对随机种子稳定，且聚类并非单纯复制 Commit 总量分组。留出 45 个仓库的轮廓系数为 **0.4041**。按训练与验证数据得到的四类解释为：持续活动型（123 仓库）、集中活动型（47）、阶段波动型（40）、低活动型（45）。这些名称描述近期行为，不代表质量、健康度或采用价值。低活跃仓库仍展示完整周数、Commit 总量和活跃周等事实；不足 12 周时不输出模式模型。

模型版本：`ml03-12w-v1`。纯 JSON 推理参数位于 `ml/course/artifacts/ml03-maintenance-pattern-12w.json`，后端不加载任意上传的序列化模型。

## M2：未来 4 周活跃趋势分类

**标签**：比较未来 4 周和此前 4 周 Commit 总数；上升/下降须达到 `max(3 次 Commit, 此前 4 周量的 25%)` 变化，避免 0→1 被当成显著增长。特征只取观测点之前 12 周。滑动窗口按仓库隔离，验证使用两个较早时间截面，训练标签的结束时间不越过对应验证截面。

候选为多数类 `DummyClassifier`、`LogisticRegression` 和 `HistGradientBoostingClassifier`；基线另含“延续近期历史变化类别”。验证集合合并两次时间截面后的结果：

| 候选 | Macro-F1 | Balanced Accuracy |
|---|---:|---:|
| Logistic Regression | **0.5185** | **0.5286** |
| HistGradientBoosting | 0.5147 | 0.5262 |
| 近期历史变化基线 | 0.3827 | 0.3824 |
| 多数类 Dummy | 0.2087 | 0.3333 |

选择 Logistic Regression：验证 Macro-F1 略高于 HGB，也明显高于两种简单基线；它能以小型系数 JSON 在后端无 sklearn 运行时依赖地推理。最终模型用训练与验证仓库拟合，在留出的 45 个仓库、单一较晚预测时点上测试：

| 留出方法 | Macro-F1 | Balanced Accuracy |
|---|---:|---:|
| Logistic Regression | **0.4753** | **0.4935** |
| 近期历史变化基线 | 0.3644 | 0.3838 |
| 多数类 Dummy | 0.1905 | 0.3333 |

混淆矩阵行列顺序均为“下降、基本稳定、上升”：`[[8, 0, 5], [2, 13, 3], [4, 8, 2]]`。产品只显示类别，不显示概率。最近 4 周 Commit 少于 3 次或 12 周活跃周少于 3 周时，只展示事实，不预测。按活跃度拆分的测试子组样本只有 7–17 个；其中高活动组（最近 4 周 ≥100 次，n=7）模型 Macro-F1 为 0.1667，低于近期变化基线的 0.3016。因此不能把总体提升解释成各活跃度都可靠；页面和本报告均保留这一限制。预测附带“既有仓库历史留仓回测”的说明。

模型版本：`ml01-trend-12w-v1`。预测时点、特征、真实标签、基线预测和混淆矩阵保存在训练结果及 `ml/course/evaluations/ml01-activity-trend.json`。

## M3：近期活动异常检测

使用前 11 个完整周的 `log1p` 中位数和 MAD 作为稳健基线，当前周绝对稳健 Z 分数达到 3 时标记方向；产品结果状态为 `baseline_only`，显示“疑似”并提示结合项目事件人工核查。该规则不是已验证准确率的 ML 模型。

训练集含 6,090 个周上下文，测试集含 540 个上下文（来自 210/45 个仓库）。IsolationForest 测试标记 27 条、MAD 规则标记 45 条、重合 21 条、Jaccard 重合率 0.4118。这些数值只是触发量与重合度，不是准确率。30 条真实留出样例的人工复核表已生成，但复核列尚为空；因此 IsolationForest 只保留研究，不接入产品。

## 产品接入与降级

- 仓库详情展示近 12 周维护画像、未来 4 周趋势类别和最近完整周异常提示；采集默认 12 周，必要时可请求最多 24 周。
- 仓库比较与 Markdown 选型报告并列展示维护模式、趋势、异常、覆盖与来源；ML 证据不进入规则排序得分。
- 低活跃仓库仍显示可核验事实。短历史、不完整 Commit、过期数据或归档校验失败时，相关模型停用并返回明确原因；PR 缺失只影响 PR 证据，不阻断 Commit-only 特征。
- 模型状态是任务独立的：M1/M2 可用时使用训练产物，M3 明确为统计基线。无概率、无精确数量、无“健康分/成功率”。

核心代码：`backend/app/analytics/course_ml_features.py`、`backend/app/services/course_ml.py`、`backend/app/services/maintenance_collection.py`、`backend/app/services/maintenance.py`、`backend/app/worker/maintenance.py`、`backend/app/services/selection.py`。请求接口为 `POST /api/v1/repositories/{id}/maintenance-collection?lookback_weeks=12|24`，读取接口为 `GET /api/v1/repositories/{id}/evaluation`。

## v4.1 收尾补充：受控调参与真实链路

M2 按 v4.1 仅增加一轮固定候选比较，采用既有 210/45/45 切分的训练与验证分区、时间折 40/44；旧 45 个测试仓库的特征和标签没有用于本轮选择。Logistic Regression 的 `class_weight` 与 C∈{0.1,1,3}、既有 HistGradientBoosting 和两种基线的候选结果、混淆矩阵、活动量分桶及上升类错误案例见 `ml/course/evaluations/m2-tuning-round-v41.json`。

平衡权重 C=0.1 的 Macro-F1 为 0.5282，高于当前 C=1 的 0.5185；第一折从 0.4406 到 0.4591，第二折持平于 0.5575。上升类 Precision/Recall/F1 均维持 0.400/0.357/0.377；低活动分桶无变化。考虑改善幅度有限，且没有改善原先关注的上升类，本轮保留冻结的 `ml01-trend-12w-v1`，不覆盖模型 JSON。指标为历史验证结果，不代表新仓库前瞻表现。

真实 GitHub 流程对 8 个公开仓库执行采集、Worker、入库、evaluation、详情、比较和 Markdown 报告。真实 API 证据和覆盖限制见 `reports/ml/course-final-acceptance.md`；包含 12 周完整数据、低活跃抑制、24 周事实扩展、短历史和分页上限 partial 场景。比较报告里的 Django/Flask 排名是用户选择 Commit 指标权重后的规则结果，ML 结果只作行为证据。

## 验证记录

- 完整后端测试：**257 passed**；另有 7 条既有依赖/夹具弃用或告警，不影响结果。
- 前端 `npm run typecheck`：通过；`npm run build`：通过。
- 后端 TestClient 测试覆盖实际 JSON 模型推理、低活跃与部分覆盖降级、12/24 周任务、缓存复用、比较结果和 Markdown 报告。
- Mock 浏览器检查作为独立 UI 测试记录，不计作真实数据证据。v4.1 收尾另以 8 个公开 GitHub 仓库完成真实 API → Worker → 临时数据库 → evaluation → 详情／对比／Markdown 报告核验；真实截图与请求估算见 `reports/ml/`。
- Codex 内置浏览器以 433×938 CSS 像素检查窄屏详情与对比页；页面无整体横向溢出，比较表保留内部横向滚动。旧研究样本仍无新仓库前瞻验证。

## 复现与证据文件

关键训练评估 JSON 已写入 `ml/course/evaluations/`；训练模型 JSON 位于 `ml/course/artifacts/`。完整 CSV 特征集、逐样本预测、模型 Joblib 和人工复核空表位于本机忽略目录 `dataprepare/MachineLearn/run/course-ml-12w-v2-verified-20261110/`，不会被误当作源码提交。

复现命令（使用新目录，避免覆盖之前的训练记录）：

```bash
PYTHONPATH=. LOKY_MAX_CPU_COUNT=4 dataprepare/MachineLearn/.venv-ml/bin/python scripts/train_course_ml.py \
  --output dataprepare/MachineLearn/run/course-ml-12w-v2-rerun
```

训练脚本会校验输入周数、按固定随机种子切分仓库、重新训练和评估三个任务，并更新 `ml/course/evaluations/` 与 M1/M2 推理 JSON。M3 不生成可供产品调用的模型产物。
