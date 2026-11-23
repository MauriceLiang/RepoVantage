# RepoVantage 课程设计版机器学习收尾验收记录（v4.1）

日期：2026-11-10
任务书：`RepoVantage_机器学习课程设计收尾实施方案_v4.1.md`
基线提交：`311f3c40e9ec8fd34ea415107050d41e23fa2c00`（工作区原有未提交改动已保留）

> 历史验收记录，反映 2026-11-10 的课程版范围。M3 当时是 MAD 统计规则，后续已从当前产品和观测台移除；当前只展示 M1 与 M2。

## 验收结论

P0–P5 均已完成；P1 的 PR 搜索限流与分页上限已作为覆盖限制如实记录。P4 的真实详情、比较、Markdown 报告和窄屏布局已核验。课程版 ML 按既定边界交付：M1/M2 使用冻结 JSON；M3 明确为 MAD 统计规则；低活跃、短历史及不完整 Commit 数据不会生成正式模型预测。

本轮真实联网使用隔离的临时 SQLite 与归档目录；默认 `data/app.db` 和 `data/raw` 未触碰。工作区已有修改未清理、未提交。

## P0：基线与回退点

**状态：完成。** 本轮开始前记录了 HEAD、工作区状态和数据摘要。M1/M2 模型 JSON 已备份到 `ml/course/rollback/`，可用 `PYTHONPATH=. .venv/bin/python scripts/restore_course_ml_artifacts.py` 校验并回退。

| 模型 | 冻结版本 | 推理 JSON SHA-256 |
|---|---|---|
| M1 维护模式 | `ml03-12w-v1` | `5cddec2e2e4d935896357c376bcf5018576a226aa0a27d1b7c9c059af890e0ae` |
| M2 活跃趋势 | `ml01-trend-12w-v1` | `18a9fb8700de49b1ac27fea995f433ebcba53b71df5d9f915b402535667a918a` |

特征版本 `course-maintenance-12w-v1`。数据文件、SHA、210/45/45 仓库切分和旧指标见 `reports/ml/course-final-baseline.json`。旧 45 仓库已被查看；本轮切分仅用其仓库 ID 重现固定划分，评估样本加载只保留训练／验证仓库，旧测试特征、标签和预测不进入指标或候选选择。该实验记录见[模型评估 v4.1](model-evaluation-v41.md)。

## P1：真实 GitHub 端到端联调

**状态：完成，带覆盖限制。** 对 8 个公开仓库执行真实解析、维护采集、Worker、持久化、evaluation API 和页面流程。实际数据库位于 `/private/tmp/repovantage-course-final-v41/db/app.db`，归档目录位于 `/private/tmp/repovantage-course-final-v41/raw`。矩阵中的模型输出均来自真实 API 计算。

| 仓库与覆盖场景 | Commit 周覆盖／事实 | PR 覆盖 | 真实模型／降级结果 |
|---|---|---|---|
| `octocat/Hello-World`，零活动 | 12/12 完整，0 Commit、0 活跃周 | 12 周完整 | M1 低活动型；M2 `low_activity_scope` 抑制；MAD 基线 |
| `Theano/Theano`，老旧、长期静止 | 12/12 完整，0 Commit；另扩至 24/24 | 12/12、24/24 均为可核实真零 | M1 低活动型；M2 抑制；24 周只补充事实，M1/M2 仍按最近 12 周语义 |
| `pallets/flask`，一般活动、趋势类别稳定 | 12/12 完整，10 Commit、3 活跃周 | 部分周完整；有 1 周遇 GitHub rate limit | M1 集中活动型；M2 基本稳定；PR 不完整不伪装为零 |
| `django/django`，高活动、数据覆盖完整 | 12/12 完整，231 Commit、12 活跃周 | 12/12 完整 | M1 持续活动型；M2 下降；MAD 基线 |
| `python/cpython`，极高活动 | 12/12 完整，1,458 Commit、12 活跃周 | 1 周 rate limit，其余搜索覆盖不完整 | M1 持续活动型；M2 下降；仅 Commit 任务满足模型输入 |
| `react/react`，高活动 | 12/12 完整，122 Commit、12 活跃周 | 1 周 rate limit，其余搜索覆盖不完整 | M1 持续活动型；M2 下降 |
| `torvalds/linux`，超高活动分页上限 | 12 周可观察，但 Commit 分页达到 100 页上限、覆盖标为 partial | PR 12 周真零 | M1/M2/M3 均不输出模型判断 |
| `storytold/photocraft`，不足 12 周的新仓库 | 仅观察到 5 周；Commit 分页不完整 | 3 周完整、2 周 partial | M1/M2/M3 不输出模型判断，理由为短历史／不完整 Commit |

重复提交 `Hello-World` 的 12 周采集返回 `cached`、`reused=true`，新增 GitHub 请求为 0。GitHub HTTP 请求估算共 401 次：维护采集 364、90 天深度任务 29、仓库解析 8；不含 GitHubClient 传输自动重试。维护采集逐运行的估算与秒数见 `reports/ml/course-final-e2e-v41.json`。Linux 的分页上限和新仓库的短历史均有明确 partial 状态，没有无限翻页或假零值。

Flask 与 Django 的真实 90 天任务成功；同期比较 API 返回 `comparable`，共有 12 个完整 UTC 周。详情 API evaluation 与页面显示的 M1/M2/M3 版本、活动数字、窗口和来源一致。线上 Commit 口径是采集时默认分支可见历史，不代表完整历史分支集合。

## P2：M2 一轮受控比较

**状态：完成；保留现版。** 候选评估与错误案例在 `ml/course/evaluations/m2-tuning-round-v41.json`。脚本 `scripts/evaluate_course_m2_tuning.py` 固定用 210 个训练仓库、45 个验证仓库、时间折 40/44；预处理每折只在训练数据拟合。旧 45 测试仓库只用于重现固定的仓库切分；其周特征、标签和预测未进入本轮评估或候选选择。标签阈值及 12 周特征定义未变。

| 候选 | Macro-F1 | Balanced Accuracy | 上升类 Precision / Recall / F1 |
|---|---:|---:|---:|
| 原权重 LR（C=0.1/1/3；三者相同） | 0.4983 | 0.5147 | 0.500 / 0.214 / 0.300 |
| 当前平衡权重 LR（C=1） | 0.5185 | 0.5286 | 0.400 / 0.357 / 0.377 |
| 平衡权重 LR（C=0.1） | 0.5282 | 0.5368 | 0.400 / 0.357 / 0.377 |
| 既有 HistGradientBoosting | 0.5147 | 0.5262 | 0.467 / 0.250 / 0.326 |
| 延续近期趋势基线 | 0.3827 | 0.3824 | 0.300 / 0.321 / 0.310 |
| 多数类 Dummy | 0.2087 | 0.3333 | 0 / 0 / 0 |

`balanced C=0.1` 相对现版的两个验证折 Macro-F1 为 `0.4591 vs 0.4406`、`0.5575 vs 0.5575`：一折小幅提高，另一折持平；合并提升仅 `0.0097`。上升类三项指标完全相同，仍只有 28 个上升样本中的 10 个识别正确（Recall 35.7%）。零活动与 1–9 活动桶无变化；10–99、100+ 桶 Macro-F1 分别只增加约 `0.0010`、`0.0331`。混淆矩阵（下降、稳定、上升）为 `[[13,4,4],[5,25,11],[8,10,10]]`。JSON 另列出当前版与候选版的上升类误报／漏报案例及前后 4 周事实计数。

按 v4.1“明确、稳定、可解释”选择规则，本轮提升不足以解决上升类弱点，故保留 `ml01-trend-12w-v1`；冻结 JSON 未覆盖、SHA 未变化，未新增模型版本或回退文件。

## P3：M1 / M3 收尾

**状态：完成、冻结。** M1 保持 `ml03-12w-v1`、K=4。原训练记录中 K=2/3/4 验证轮廓系数分别为 0.4025/0.4738/0.4780；四个簇描述近期维护行为，不表示质量或健康度。低活动仓库保留 Commit 总量、活跃周、完整周等事实。

M3 保持 MAD 统计基线，仅标“疑似异常”并给出实际周与活动数；Isolation Forest 没有人工真值验证，不接入正式页面。真实仓库中没有观察到需要发出异常提示的周；这不等于异常检测能力已验证。

## P4：详情、比较和 Markdown 报告

**状态：真实 API 与页面完成。** Chrome 桌面视口 1440×1050 的真实数据截图：

- Theano 低活跃 24 周背景：[real-api-low-activity-theano-24w-v41.png](screenshots/real-api-low-activity-theano-24w-v41.png)
- Flask 模型详情：[real-api-model-detail-flask-v41.png](screenshots/real-api-model-detail-flask-v41.png)
- Flask/Django 对比与报告：[real-api-comparison-report-flask-django-v41.png](screenshots/real-api-comparison-report-flask-django-v41.png)

比较 API 和页面在同一 90 天交集上显示 12 个完整周；UI 预览和下载都使用当前响应的 `selectionResult.reportMarkdown`，落盘 Markdown 与 API 响应字段完全一致（1605 字符），因此两者来自同一次计算。选型结果明确为规则排名，使用用户指定的每周 Commit 单一事实指标（Django 1.0、Flask 0.0）；该分数不代表采用成功概率，ML 不影响排序。报告文件：`reports/ml/real-api-comparison-report-v41.md`。

Codex 内置浏览器以窄屏测试详情与比较页面，实际 CSS 视口 433×938：文档宽度与视口同为 433 px，没有页面级横向溢出。比较表使用宽 860 px 的 `overflow-x:auto` 容器，容器可横向滚动；尺寸证据见 `reports/ml/real-api-mobile-layout-validation-v41.json`。桌面浏览器采集的页面错误数为 0，见 `reports/ml/real-api-ui-validation-v41.json`。

## P5：自动检查与交付证据

**状态：完成。** 本轮 M2 调参脚本在隔离的 Python 3.11 环境执行成功，没有更改项目依赖。检查结果：

- 后端：`.venv/bin/python -m pytest -o addopts= -q` → **257 passed**, 7 条既有依赖／夹具告警。
- 前端：`npm run typecheck` → 通过；`npm run build` → 通过。
- Python：调参与回退脚本 `py_compile` → 通过；调参实际运行生成上述 JSON。
- Git：`git diff --check` → 通过。
- 相关行为用例位于 `tests/backend/test_course_ml_features.py`、`test_maintenance_collection.py`、`test_maintenance_product.py`、`test_model_registry.py`、`test_selection_report.py` 和 `test_ml_evaluation.py`。
- 真实联网链路：8 个公开仓库，真实采集／Worker／数据库／API／详情／对比／报告均留有 JSON 或截图证据，与 Mock 检查分开。

M2 评估运行时 joblib 未能读取 macOS 物理核心数，自动回退到逻辑核心并正常完成。当前 headless Chrome 本轮重试启动失败（进程异常退出），因此窄屏核验改由 Codex 内置浏览器完成；此前桌面截图和 `page_errors=[]` 记录来自 Chrome headless。内置浏览器的窄屏实测通过，没有用 Mock 代替真实 API 数据。

## 答辩限制与复现材料

- 300 仓库、15,600 行历史数据及 210/45/45 留仓划分来自既有研究池；这不是新仓库前瞻验证。旧 45 仓库留出指标仅作为已查看的历史回测。
- 默认分支 Commit 可见性、GitHub Search 限流、100 页分页上限和不足 12 周的新仓库都会影响覆盖；partial 数据不进入不适用的模型推理。
- 趋势类别不输出未校准概率或精确 Commit 数；M1 模式不代表仓库质量；M3 是规则提示而非已验证 ML 异常预测。
- 源码和模型 JSON 不等于训练数据移交。完整训练输入位于仓库忽略目录；数据路径、SHA、训练命令和评估证据见[模型评估 v4.1](model-evaluation-v41.md)与 `reports/ml/course-final-baseline.json`。

真实 API 结构化证据：`reports/ml/course-final-e2e-v41.json`、`reports/ml/real-api-e2e-v41.json`、`reports/ml/real-api-ui-validation-v41.json`、`reports/ml/real-api-mobile-layout-validation-v41.json`。基础状态快照：`reports/ml/course-final-baseline-status.txt`。本轮没有提交 Git commit。
