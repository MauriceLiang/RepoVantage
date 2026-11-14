# v4.4 P0：工作区与数据基线

检查时间：2026-11-11<br>
目的：在创建新 150/150 实验产物前固定工作区、数据源和旧模型状态。

## Git 与工作区

- 分支：`feature/polish-existing-frontend`
- HEAD：`311f3c40e9ec8fd34ea415107050d41e23fa2c00`
- 开始检查时已有 **111 项**未提交或未跟踪变更。范围包括课程 ML 服务、训练脚本、前端、迁移、测试、ML 评估与报告；这些改动均视为用户已有工作，后续只做必要的增量修改，不重置、清理或覆盖。
- `scripts/train_course_ml.py` 在开始时为未跟踪文件，最后修改时间为 2026-11-10 10:44；文件是当前课程实验实现的一部分，修改前先按现有实现审查。
- 当前 `reports/course-150-150/p0-baseline.md` 路径在执行前不存在。

## 源数据与输入校验

- 数据集：`repo-evaluation-2026-v1`
- 输入：`dataprepare/MachineLearn/run/repo-evaluation-2026-v1/repository_weekly_features.csv.gz`
- 方案预期 SHA-256：`5a463e44da2260d943a7851c872277984552fba3034e12eb8d5bb14c7c2c148d`
- 执行前实测 SHA-256：`5a463e44da2260d943a7851c872277984552fba3034e12eb8d5bb14c7c2c148d`，一致。
- CSV 共 300 个唯一仓库，每仓库 52 周，共 15,600 行；未发现周数不足或重复仓库周序列。
- Commit 周覆盖状态：15,132 行 `complete`、468 行 `true_zero`；最近 12 周、最近 4 周以及 M2 `origin=48` 历史输入/标签窗口，300 个仓库均满足 Commit 覆盖要求。
- 原始采集目录约 536 MiB，其中 `collection.sqlite3` 约 489 MiB；本次只读核验，没有改写原始 CSV、SQLite 或压缩归档。

## 用户数据库与归档状态

- `data/app.db` 存在，约 46 MiB；已有 `app.db.before-0008-20261110T002054Z.bak` 和 `app.db.before-selection-feedback-20261109T135458Z.bak`。
- `data/raw/` 约 2.8 MiB；`data/collected/` 约 6.9 MiB。
- 本任务的数据包导入和端到端验证使用隔离数据库/目录，不对上述用户数据库或在线采集归档执行导入、删除或覆盖。

## 旧模型与回退基线

| 模型产物 | 当前文件 SHA-256 | `ml/course/rollback/` 回退副本 SHA-256 | 状态 |
|---|---|---|---|
| `ml03-maintenance-pattern-12w.json` | `5cddec2e2e4d935896357c376bcf5018576a226aa0a27d1b7c9c059af890e0ae` | `5cddec2e2e4d935896357c376bcf5018576a226aa0a27d1b7c9c059af890e0ae` | 一致，保留 |
| `ml01-activity-trend-12w.json` | `18a9fb8700de49b1ac27fea995f433ebcba53b71df5d9f915b402535667a918a` | `18a9fb8700de49b1ac27fea995f433ebcba53b71df5d9f915b402535667a918a` | 一致，保留 |

本轮候选模型与评估写入新实验目录，不覆盖以上产品产物或回退副本。M3 仍使用 MAD 规则，不训练新异常模型。

## 执行边界

- 使用已经采集的 300 仓库数据，不发起 GitHub 请求，不重新训练既有 300 数据之外的样本。
- 先生成并审核固定 150/150 仓库级分组，再运行 M1/M2；不按测试分数更换随机种子或重抽分组。
- 研究快照、应用数据转换和测试均保留来源、时间窗与覆盖状态；部分/缺失数据不补零。
- 本文件创建前未运行新划分训练，也未改动旧模型、源数据或用户数据库。
