# 52 周维护活动特征与覆盖契约

时间窗为以 UTC 周一 00:00 为边界的连续 52 个完整周，结束时刻不包含在窗口内。产品默认要求采集时间不早于配置的 `base_refresh_hours`（默认 24 小时），且窗口终点仍是最新完整周；不满足时返回 `stale`。

| 数据 | 采集口径 | 有效覆盖 |
| --- | --- | --- |
| Commit | 固定采集时默认分支 SHA，按 committer 时间，缺失时使用 author 时间 | 所有分页完成、SHA 与时间有效且不重复；产品预算每模块 100 页，超限为不完整。历史并非该时间点的分支快照。 |
| 新建 PR | `state=all`，按 `created_at` 倒序读取到窗口前或末页 | 分页完成、顺序和 ID 可核对、首次页复查一致；不存在或已删除数据无法从当前快照恢复。 |

两者逐周分别记录 `complete`、`true_zero` 或 `partial`；没有覆盖的周不会当作零。周边界、周数、数值、覆盖、来源归档与周记录哈希均需通过校验，否则不输出模型标签。产品每次重新采集完整窗口，当前没有增量刷新或自动续采。

`maintenance-shape-v1` 由 `backend/app/analytics/maintenance_features.py` 同时供训练和产品调用，包含 Commit/PR 对数总量、活跃周占比、最长零活动周、波动、近期比例及 PR/Commit 比等；并返回可展示的事实证据。`maintenance-temporal-shape-v2` 在此基础上额外定义近 12 周占比、最高四周占比、周分布熵、活跃周波动和 Commit/PR 活跃周重合。v2 仅适用于至少 20 次 Commit 且至少 10 个新建 PR 的完整窗口；低于范围时仅保留历史统计。

v5 研究候选只使用 v2 的 `commit_entropy`、`pr_entropy`，预处理参数和训练来源在 `dataprepare/MachineLearn/run/ml03-v5-development/` 的模型与清单中。冻结协议和外部集不允许改用现有结果反复调参；在批准和完整生产验收前，产品只使用 v1 事实统计。
