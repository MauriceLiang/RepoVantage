# 300 仓库本地事件快照

规范数据集 ID 为 `course-research-events-300-v1`。早期清单曾误用 `course-test-events-v1`；该旧 ID 作为兼容别名保留在 `dataset.json`。本次只修正版本化元数据，事件归档与 SQLite 内容哈希保持不变。

此包由 `dataprepare/MachineLearn/run/repo-evaluation-2026-v1/collection.sqlite3` 生成，供单仓分析、同期比较和研究汇总使用。它保留 300 个仓库的创建时间、五项模块覆盖状态，以及源表中的全部 Commit、Issue、PR 和 Release 记录；提交账号已匿名化，不包含提交说明、Issue / PR 标题与正文。Issue 响应和 Tag 原表仍保留在 `dataprepare/`，当前评分不使用它们。

统一分析截止时间为 `2026-11-05T10:31:37Z`。包内较晚的 Release 记录保留，但不会混入该截止时间之前的比较。Issue 源数据只涵盖采集起点之后创建的记录；`sgl-project/sglang` 的 PR 更新与 `renovatebot/renovate` 的 Release 分别标记为部分和失败，不能当作完整覆盖。

可用 `python3 scripts/build_course_test_events.py --output <新目录>` 从原始采集库重新生成。脚本不会访问 GitHub，并拒绝覆盖已有目录。
