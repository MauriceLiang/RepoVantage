# 数据模型

所有类型定义在 `src/services/types.ts`，页面与图表只依赖这些类型，不直接依赖 Mock 文件。

## 核心类型

| 类型 | 关键字段 | 说明 |
|---|---|---|
| `RepositorySummary` | `id, fullName, language, stars, status, lastAnalyzedAt, activityDelta, scenario` | 列表与页头使用的仓库摘要 |
| `RepositoryAnalysis` | `metrics, commits, dailyCommits, issues, issueDuration, pullRequests, prDuration, releases, authors, observations, coverage` | 单仓库分析聚合结果 |
| `TimeSeriesResult` | `series[], unit, granularity, window, sampleSize, coverage, collectedAt, limitation` | 时间序列（单/多序列通用） |
| `MetricSet` | `metrics[], window, collectedAt, coverage` | KPI 指标集合 |
| `Metric` | `id, label, value(nullable), unit, note, sampleSize` | 单指标；`value: null` 表示不可用，UI 渲染为 — |
| `HistogramResult` | `buckets[], percentiles{p50,p75,p90}, sampleSize, coverage` | 耗时分布 |
| `Coverage` | `state: complete\\|partial\\|missing, label, detail` | 覆盖状态，禁止把 unknown 当 0 |
| `ReleaseRecord` | `tag, publishedAt, prerelease, intervalDays, note` | 发布事件 |
| `CommitEvent` | `sha, title, author, date, isBot, url` | 钻取明细 |
| `IssueRecord` / `PullRequestRecord` | 编号、标题、创建/关闭（合并）时间、耗时、状态 | 钻取明细 |
| `ComparisonBundle` | `entries[], window, notes` | 比较页数据 |
| `ResearchDataset` | `groups, scatter, quality, limitations` | 研究页数据 |
| `TaskItem` | `status, stage, processed, total, error` | 任务状态 |

## 演示场景

| scenario | 仓库 | 特征 |
|---|---|---|
| `active` | steady-core / grid-lite | 90 天完整数据，活动有起伏 |
| `partial` | sparse-kit | 仅采集到 03-24，Issue 分页截断 |
| `small` | tiny-lab | 仅 5 周、7 条提交，n 很小 |
| `quiet` | docs-site | 活动低但完整 |
| `empty` | empty-lite | 尚未分析 |
| `failed` | queue-demo | 采集失败 |

## Mock 数据一致性

- 周序列合计 = 指标卡「提交数」；日序列按周拆分后合计等于周值。
- Issue / PR 双序列、耗时分布、样本数来自同一份 seed。
- 覆盖状态与采集时间随仓库不同，比较页会展示差异，不默认「同口径可比」。
