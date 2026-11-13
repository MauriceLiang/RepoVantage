# 机器学习落地实施记录 v3

截至 2026-11-10，项目交付状态为 **partial**，`production_ml_delivered=false`。以下统计和规则功能已经接入，任何研究模型都没有被批准上线。

## 实施与证据

| 阶段 | 实际结果和剩余工作 |
| --- | --- |
| G0 | 原始历史来源、训练切分、外部名单、模型和评估器均有哈希及冻结记录，见 `ml-production/manifests/` 和 `ml-production/protocols/`。保留首批外部失败结果。 |
| G1 | 产品采集后台保存 52 个完整 UTC 周、覆盖状态、可追溯来源和归档哈希；产品与研究使用同一特征代码。根据独立采集的分页诊断，后续手动产品采集预算由每模块 50 页提高至 100 页，超过上限仍标记不完整。当前每次采集会重新扫描 52 周，**增量刷新和自动续采尚未实现**，超过默认 24 小时或完整周边界后需再次采集。Commit 为采集时默认分支 SHA 可见历史，不能恢复历史时点的分支成员或已删除 PR。 |
| G2 | 初始规模、规模加形态及形态候选已比较。后来冻结的 v5 候选仅用历史训练仓库选择，K=2、特征为 Commit/PR 时间熵，140 个训练、48 个验证仓库；训练 OOB ARI 5% 分位 0.9171、验证轮廓系数 0.6417。数值模型、研究模型、规模基线和开发指标已字节级复现，见 `ml03-reproducibility.json`。这不是发布批准。 |
| G3 | 首个独立外部集冻结 60 个仓库，其中 53 个完整且在模型范围；形态轮廓相对规模基线增益为 -0.0706，低于冻结门槛 +0.05，判定失败。第二批互不重叠的 75 个仓库中，45 个完整且可归类，形态增益 +0.2671，但拒判率 40% 超过冻结上限 35%，再次未通过。真实双人复核和负责人决定均缺失。详见 `external-validation-v5.md`。 |
| G4 | 受信任目录、注册状态、哈希与审批记录完整性校验、有限数值推理、超时、适用范围、拒判、缓存及回退已实现；测试数据下的推理与禁用回退见 `ml03-runtime-exercise.json`。记录中签署人身份的真实性仍须靠人工及部署环境权限核实，哈希本身不证明身份。生产中仍无获批模型。macOS 当前检查子进程峰值 RSS，但没有硬性地址空间内存上限；进程内监控会在重启后清空，生产监控与目标环境容量验证未完成。 |
| G5 | 单仓库画像、后台采集任务、同窗对比和 Markdown 报告均已接入。未获批准时仅展示历史事实，维护画像不参与选型分数；无覆盖数据不会补零。`browser-v3-evidence.json` 和 `browser-v3-empty-evidence.json` 记录了隔离数据库、真实 GitHub 数据、桌面、移动端、慢加载、任务提交、报告下载及反馈删除测试。截图在 `dataprepare/MachineLearn/run/ml03-v3-browser-evidence/`。 |
| G6 | 隔离环境使用合成测试批准记录验证禁用后 API 回退；并非真实模型灰度或生产回滚演练。尚无真实双人复核、负责人审批、获批模型、生产灰度和生产监控验收，不能宣布 ML 生产化。 |

首批独立结果见 `dataprepare/MachineLearn/run/ml03-v3-external-evaluation/metrics.json` 及 `ml-production/manifests/ml03_external_result_lock.json`。v5 的 300 仓库在线/离线特征比对见 `dataprepare/MachineLearn/run/ml03-v5-development/feature_parity.json`；其中 225 个适用且非 OOD 的预测与受控数值实现一致，容差 1e-12。

数据库已通过 SQLite 在线备份并升级至 `0008_maintenance`。备份位置、完整性和原表行数核对见 `migration-0008.json`；隔离浏览器测试所采集的数据未写入用户数据库。真实数据库在迁移时新增的维护活动表为空，须从仓库页面发起采集并运行 Worker。

验证：`.venv/bin/python -m pytest tests/backend -o addopts='' -q` 为 **254 passed**；7 条警告来自现有 TestClient、重复 ZIP 文件名测试和 Alembic 配置。`npm run typecheck`、`npm run build` 与 `git diff --check` 通过。真实 GitHub 采集在隔离数据库中对 `BurntSushi/ripgrep` 和 `sharkdp/fd` 成功完成，并在浏览器比对页面与下载报告的来源和事实统计。隔离合成批准记录下的 50 次本机未缓存推理 P95 约 27 ms；这一结果不代表生产 SLO。

## 本机运行和验证

下面的命令基于当前仓库已有的 `.venv`、`frontend/node_modules` 和研究环境；本次后端使用 Python 3.12.14 和 `uv.lock`，研究使用 Python 3.11.9 与 `dataprepare/MachineLearn/research_s1/requirements.txt` 的固定版本。服务需要本地 `.env` 中已有的配置与 GitHub 凭据，勿将凭据写入报告。

```bash
# 首次或新增迁移后，先核对并备份实际数据库
.venv/bin/python -m alembic upgrade head

# 构建并启动产品；Worker 在另一个终端运行
cd frontend && npm run typecheck && npm run build && cd ..
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8501
.venv/bin/python -m backend.app.worker.main

# 后端测试
.venv/bin/python -m pytest tests/backend -q
```

研究候选可在新的空目录重复训练（不得覆盖现有冻结产物）：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  dataprepare/MachineLearn/.venv-ml/bin/python scripts/train_ml03_v3.py \
  --weekly dataprepare/MachineLearn/run/repo-evaluation-2026-v1/repository_weekly_features.csv.gz \
  --train-manifest ml-production/manifests/ml03_train_manifest.json \
  --protocol ml-production/protocols/ml03_release_protocol_v3.json \
  --output /private/tmp/repovantage-ml03-reproduction-new
```

研究数据、模型和截图位于被 Git 忽略的 `dataprepare/`，数据库和备份位于被忽略的 `data/`；代码提交本身不会包含这些本地文件。迁移或复制环境时须另行保全对应数据和哈希。

## 受控停用

维护者可执行以下命令将 ML-03 切换到 `disabled`，后续请求回退到历史统计；操作记录写入 `ml-production/logs/registry_events.jsonl`。此命令不会批准或启用模型。应确认日志写入成功，并在部署环境复核 `/api/v1/models/status` 与用户页面。若写日志失败，注册表可能已经停用，不能将命令失败误判为模型仍在服务。

```bash
.venv/bin/python scripts/disable_ml03.py --reason '填写实际停用原因'
```

`ML-01` 的未来观测、系统时区和机器在线条件及补救流程见 `ml01-shadow-schedule.md`。到期结果尚未发生，不得视为已完成评估。
