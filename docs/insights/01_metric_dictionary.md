# 指标字典 · insights-v1

基准 cff079a；Vue/FastAPI/SQLite/Worker 增量实现。统计不代表代码质量。

统一 UTC，API ISO8601 Z；窗口左闭右开。活动 90 天、正式 Release 365 天。窗口上界在开始采集活动时固定，采集完成日期各模块单独记录，防止分页时窗口漂移。周一 00:00 分桶；不完整边界周显示 null。

| 指标 | 计算 | 样本与限制 |
|---|---|---|
| commits_weekly | 按 committer.date / 同仓库 SHA 去重 | 默认分支含合并提交；完整覆盖的完整周允许真 0；partial 返回 null，同时保留 observed_events 下界 |
| recent/previous_4w | 最近8个已结束完整自然周，后4周与前4周总数差与百分比 | 不足8周拒算；前期0时百分比null；环比，不是同比 |
| issue_closed_duration_hours | 窗内 closed_at − created_at，小时 | 排除 PR、缺失和倒序；最近可观测关闭，不是首次响应/实际工时 |
| pr_merge_duration_hours | 窗内 merged_at − created_at，小时 | closed PR 集合，仅合并者进入耗时；不计算创建 cohort 合并率 |
| issues_closed_weekly / prs_merged_weekly | closed_at / merged_at UTC 周计数 | 与耗时样本不同：创建时间异常仍可能有有效关闭事件 |
| release_intervals_days | 窗内正式 Release 按 published_at 排序相邻差，天 | 排除草稿、预发布单独计数；少于2次中位间隔null；纯 tag 不算 |

分位采用 NumPy linear，p50 n≥1、p75 n≥5、p90 n≥10。耗时直方桶 [0,24),[24,72),[72,168),[168,720),[720,∞) 小时。排除计数与缺失率分别给出。部分覆盖保留已观测有效样本数，UI 不画完整总体图。

基础 Stars/Forks 仍是实际快照，不由活动总量倒推历史。贡献者身份识别尚不作为完整团队人数指标。
