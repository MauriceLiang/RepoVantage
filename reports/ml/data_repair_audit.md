# Issue 评论数据修复审计

日期：2026-11-09。原研究中，62 个仓库的 59,651 条 Issue 快照与评论观察数矛盾，其中 13 个仓库在第 300 页结束时末页仍满。现有历史记录不能区分采集遗漏与后续删除。

本次实现逐 Issue 采集与核对工具 `scripts/repair_issue_comments.py`，调用 `backend/app/services/issue_comment_repair.py`。它跟随 GitHub 返回的分页链接，保留评论 ID、时间、作者身份类型、关联信息、请求页和采集前后 Issue 快照，不保存评论正文；以独立目录和原子检查点支持续跑。缺页、重复、身份不明、快照变化、限流或计数矛盾均标记 `coverage_uncertain`。对已成熟的 14 天窗口，仅在实际观察到人类非作者评论时允许给出正例；当前没有观察到评论即使快照计数相等，也不证明过去没有现已删除的回复，因此不产生历史负例。

按冻结清单，从 62 个受影响仓库各抽取一条存在矛盾的 Issue，另复核一条已确认的历史误判，合计 63 条，而不是重采了全部 59,651 条：

- 12 条达到 `complete_current_snapshot`，51 条为 `coverage_uncertain`；51 条存在当前快照评论数对账差异，其中 1 条还出现无效或重复评论。
- 共观察到 273 条当前可见评论；35 条形成已观察到的正例，28 条标签未知，未将任何一条未知样本标为负例。
- `microsoft/vscode#328547` 原摘要为 0 条，逐 Issue 检索观察到 10 条当前可见评论，其中有 14 天内的人类非作者回复，证实原摘要至少存在一条错误的无回复判定。

清单位于 `dataprepare/MachineLearn/run/p0-reproduction-v2/issue_repair_manifest.json`，本次结果位于 `dataprepare/MachineLearn/run/issue-repair-current-v2/`。这些样本不是随机代表性抽样，也没有完成 62 个仓库所有问题的覆盖对账。基于 35 个正例和没有可认证的负例无法重训并校准 ML-05；未来需可追溯的历史事件或新建前瞻性评论水位、等待 14 天成熟，并按仓库和时间重新划分。当前版不应把回溯快照筛选作为历史预测时可用特征。

具体分页和查询参数以 [GitHub Issue comments REST 文档](https://docs.github.com/en/rest/issues/comments)为准；`since` 按最后更新时间筛选，不能当成评论创建时间分片证明完整覆盖。
