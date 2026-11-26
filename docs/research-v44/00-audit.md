# RepoVantage v4.4 实施前审计

审计时间：2026-11-15（本机工作区）

## 工作区边界

- `HEAD=2a59bf5`，分支 `feature/polish-existing-frontend`。
- 保留审计开始前的工作区状态：`ml-production/scheduling/logs/ml01-shadow.stdout.log` 有未提交修改；`.agents/` 与 `.openidea/` 是未跟踪目录。
- 本机数据库位于 Git 忽略的 `data/app.db`。迁移前在线备份已创建为 `data/app.db.before-research-v44-20261115.bak`，大小 48,295,936 字节；备份和数据库都不进入 Git。

## 课程研究资产

仓库版本化清单 `course-research-300-v1/dataset.json` 声明 300 个仓库、3,600 条周记录、12 周窗口（2026-08-10 至 2026-11-02 UTC，右端不含）及 150/150 的 train/test 划分。其 `split_manifest_sha256` 为 `2bb8460365e8e6e69a7d67ef250b7c9aedb0507597f3fdf84ab0b37df5ccdba4`。Commit 3,600 周均为完整或真实零；PR merged 有 3,588 周完整/真实零，另有 12 周标记为并发变更部分覆盖。现有 M1、M2 产物哈希分别为 `4289ce1896385d5c24d5423b849eddaf03f8677b27db4dae13044307c311957a` 与 `02fa46887dd340e78db4f1263711d69902c7ad98387209840ca45ef9eac8a651`。

本机 `data/app.db` 在本次迁移前版本为 `0008_maintenance`：仓库 316、数据集 5、数据集关系 764、维护运行 300、维护周记录 3,600、活动事件 26,309、仓库快照 322。课程样本 membership 仍为 300，train/test 各 150。以上库内记录与课程静态包分开管理。

## 精选候选与来源

- `featured-v1` 数据包声明 15 个仓库，截止 `2026-10-22T08:32:31Z`；Commit、Issue、Pull Request、Release 的覆盖报告均为 15/15 complete。质量报告记录本次历史数据来自既有冻结包；本次实施没有向 GitHub 发起 HTTP 请求。
- 候选裁决清单为 11 个正式比较、4 个参考、3 个新增待采。15 个既有仓库均能以 GitHub 数字 ID 在本机仓库主表找到；`sharkdp/fd` 在主表及事件表中，但当前不在 `featured-default` 数据集 membership。
- 三个新增仓库（Chi、Litestar、Solid）的 ID 在本机仓库主表和事件表均未找到；保留为待采候选，不写入伪造的活动数据。

## 现有前端和接口路径

- 生产入口 `frontend/index.html` 使用 `frontend/optimized` 的 Vue 入口。当前优化版研究页直接读取 `mockData.ts`，不满足正式研究页面的数据来源边界。
- 后端已提供 FastAPI `/api/v1/research/dashboard` 与 `/api/v1/research/insights`；课程研究仪表盘已批量载入维护周记录。`course_research_insights` 中仍存在逐 membership 查询 repository/run/week 的 N+1 路径，实施阶段需减少查询并实测。
- 当前 SQLAlchemy 使用 `repositories.repository_id`（GitHub 数字 ID）作为仓库主键；Alembic 版本为 `0008_maintenance`，下个迁移号应为 `0009`。

## 数据标识冲突

`data/datasets/course-research-events-300-v1/dataset.json` 的路径名与清单 `dataset_id=course-test-events-v1` 不一致。运行时代码及既有 API 也使用旧 ID。本次修订需把 canonical ID 改为 `course-research-events-300-v1`，保留旧 ID 作为显式兼容别名，更新校验与测试；SQLite 事件内容、压缩包哈希和 SQLite 内容哈希不得改变。

## 可复用窗口与风险

`featured-v1` 每个仓库均报告 `2026-07-24T08:26:02Z` 至 `2026-10-22T08:26:02Z` 的活动覆盖，可容纳 12 个完整 UTC 周窗口 `2026-07-27T00:00:00Z` 至 `2026-10-19T00:00:00Z`。正式发布指标前，生成脚本会按固定窗口过滤原始事件并逐仓验证覆盖；低于样本门槛、Release 数量不足或覆盖异常的数值保持不可比较。

性能基线的准确查询数、p50/p95 需要在变更前用 SQLAlchemy 事件监听进行复测；静态审计未把旧服务行为虚报为性能数字。
