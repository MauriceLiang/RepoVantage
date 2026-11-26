# RepoVantage v4.4 数据清单

盘点时间：2026-11-15（本机工作区）  
裁决依据：`data/manifests/selection-v44-candidates.json`（`repovantage-v4.4-curation-v1`）  
历史快照：`selection-v44-historical-1`，来源 `featured-v1`，截止 `2026-10-22T08:32:31Z`

## 数据用途与冻结资产

| 数据资产 | 实测/清单数量 | 观察范围与用途 | 结论 |
|---|---:|---|---|
| `course-research-300-v1` | 300 仓库、3,600 条周记录；train/test 各 150 | 12 周，`2026-08-10T00:00:00Z` 至 `2026-11-02T00:00:00Z`（右端不含）；仅供课程研究与描述性星图 | 解析压缩文件后核对 300/3,600；split 文件 SHA-256 与清单一致：`2bb8460365e8e6e69a7d67ef250b7c9aedb0507597f3fdf84ab0b37df5ccdba4`。本次未改 `ml/course`、课程研究数据包或 150/150 划分。 |
| `course-research-events-300-v1` | 300 仓库；元数据记录 Commit 445,175、Issue 167,248、PR 331,723、Release 42,458 | 截止 `2026-11-05T10:31:37Z`；历史事件证据，不代表完整 GitHub 历史，也不与精选快照直接混算 | 元数据修订到 revision 2；canonical ID 为 `course-research-events-300-v1`，旧 ID `course-test-events-v1` 保留为兼容别名。清单记录 archive SHA `94651c54b8ded3f928564ff4a665e0e2d4807c7cd934ae16fa694898a326a64c` 与 SQLite SHA `95b7a864c83a4bc09a534aa8232a90e13ad6e67ed7c40a66900cd65b1c8cb9c7`。本次只修版本化元数据，没有重建事件内容。 |
| `featured-v1` | 15 个既有仓库 | 活动指标统一为 12 个完整 UTC 周 `2026-07-27` 至 `2026-10-19`；Release 单独看 365 天；来源截止 `2026-10-22T08:32:31Z` | 复用已有冻结数据，没有 GitHub HTTP 请求。覆盖声明是冻结采集包内的窗口质量信息，不代表完整 GitHub 历史。 |
| `research-2026-v1` | 本机历史检查为 0 个成员 | proposed/pending | 没有回退到 300 课程样本来冒充正式选型集。 |

课程周特征和精选事件快照属于两个独立用途。300 点星图只读取 `course-research-300-v1`；选型工作台只读取 `featured-v1` 的裁决快照。两者没有合并排名。

## 候选用途、ID 与数据状态

15 个精选项目全部保留：11 个正式比较候选、4 个专题参考；新增 3 个补充仓库 profile。候选 ID 按 GitHub 数字 ID 去重，quality manifest 记录 0 个重复 ID。三个新候选没有本地历史事件指标，页面显示待采，未写入伪造活动数据。

| 场景 | 正式比较候选（GitHub ID） | 历史指标状态 | 补充状态 |
|---|---|---|---|
| G1 Go HTTP/API | Gin `20904437`；Echo `31504491`；Fiber `234231371` | 2 个 metrics-ready；Gin 的历史快照未达到全维可比条件 | Chi `44344606`：待采集 |
| G2 Python API | FastAPI `160919119`；Flask `596892` | FastAPI metrics-ready；Flask 历史快照未达到全维可比条件 | Litestar `435625572`：待采集。Django `4164482` 保留为全栈参考，不进 API 候选排名 |
| G3 JVM 服务 | Spring Boot `6296790`；Quarkus `139914932`；Micronaut `124230204` | 3 个 metrics-ready | 无新增候选 |
| G4 前端 UI | React `10270250`；Vue `137078487`；Svelte `74293321` | 3 个 metrics-ready | Solid `130884470`：待采集 |

专题参考还包括 `BurntSushi/ripgrep` `53631945`、`sharkdp/bat` `130464961`、`sharkdp/fd` `90793418`。Rust CLI 与 Django 均不进入四组正式比较。

总体状态：14 个正式候选中，9 个 metrics-ready、2 个历史快照未完全可比、3 个待采；另有 4 个 reference-only。`eligible` 表示业务纳入资格，`metrics_ready` 表示此历史快照是否达到比较条件，两者在 API 中分开返回。

## 指标口径与覆盖

| 指标 | 窗口与口径 | 记录状态 |
|---|---|---|
| `weekly_commit_mean` | 12 周 Commit 总数除以 12，单位 commits/week | 11 候选有值，n=12，覆盖 complete |
| `weekly_pr_open_mean` | 同一 12 周新开 PR 总数除以 12，单位 pull_requests/week | 11 候选有值，n=12，覆盖 complete |
| `issue_closed_median_days` | 窗口内已关闭 Issue 的 `closed_at-created_at` 中位数；n<5 不输出 | 11 候选有值，样本数 9–870，覆盖 complete |
| `pr_merged_median_days` | 窗口内已合并 PR 的 `merged_at-created_at` 中位数；n<5 不输出 | 10 个有值、1 个因 n<5 为 null；样本数 4–1,053，模块覆盖 complete |
| `release_interval_median_days` | `2025-10-22T08:32:31Z` 至 `2026-10-22T08:32:31Z` 内正式 Release 的相邻间隔中位数；不设方向 | 9 个有值，2 个真实零（窗口内不足两次 Release），覆盖状态分开记录；不进入综合权重 |

质量清单合计 55 条 metric 状态：53 `complete`、2 `true_zero`、0 `partial`、0 `failed`、0 `not_collected`。这里的 `true_zero` 是 Release 观测结果，不等价于缺失；PR 时长因样本不足产生的 null 也不被改写为 0。质量清单的样本阈值为时长 n<5 证据不足、5–9 探索性、n≥10 描述性比较；覆盖不完整时不参与完整窗口比较。

## 采集、数据库与去重结果

- 本次 GitHub HTTP 请求数：0；没有运行默认全量采集，也没有对三个补充仓库进行定向抓取。
- 本地既有精选 profile 复用 15 个；新增的 3 个 profile 只含公开仓库识别元数据，不含活动指标。
- 迁移后 SQLite 版本：`0009_selection_scenarios`。只读计数：`repositories=319`、`datasets=5`、`dataset_repositories=777`、`selection_scenarios=4`、`selection_scenario_candidates=18`、`selection_metric_snapshots=55`、`selection_capability_evidence=4`、`selection_snapshot_releases=4`。
- 300 课程库 membership 与 train/test 分割没有因候选组 seed 改写。v4.4 候选关系只写入选型场景表。
- `selection-v44-quality.json` 是本机质量清单；其 0 HTTP 请求和候选覆盖计数来自本次实测/计算，不代表未来补采结果。

