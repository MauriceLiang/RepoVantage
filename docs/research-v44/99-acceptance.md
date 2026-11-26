# RepoVantage v4.4 验收记录

验收时间：2026-11-15（本机工作区）  
目标：继续实施数据裁决与可视化文档中的 P0–P7；保留已有未提交工作。

## 已完成并验证

### 数据和迁移

- 新增 Alembic `0009_selection_scenarios`，按随附裁决清单建立 4 个场景、18 条关系（11 个精选比较、4 个参考、3 个待采补充）、55 条历史指标、4 条 G1 `net/http` 能力证据和 4 个快照发布记录。
- seed 可幂等执行；后端测试检查 4 组候选、参考隔离、待采状态与原课程 300/150/150 分割。
- SQLite 当前版本为 `0009_selection_scenarios`。只读数据库计数见 [02-dataset-inventory.md](02-dataset-inventory.md)。迁移前备份为 `data/app.db.before-research-v44-20261115.bak`；数据库与备份均未进入 Git。
- 课程研究数据实际解析为 300 仓库、3,600 周记录、150/150 划分；split manifest SHA-256 与冻结清单一致。`ml/course` 与 `data/datasets/course-research-300-v1` 没有本次变更；此前工作区已有的 `ml-production/scheduling/logs/ml01-shadow.stdout.log` 改动原样保留。
- 修复课程事件数据包 canonical ID：`course-research-events-300-v1`；保留旧 `course-test-events-v1` 别名与原始来源哈希记录。没有重建事件内容。
- 精选 15 个项目全部保留；11 个归入四组正式比较，4 个作为专题参考；3 个补充仓库 ID 去重后新增 profile。本轮没有 GitHub HTTP 请求，Chi、Litestar、Solid 仍是 pending，不能参加匹配窗口比较。

### 接口与页面

- 新增只读 API：300 仓库星图、四场景目录/详情/图表数据/候选详情/敏感性状态。API 将资格 `eligibility` 与指标 `metrics_ready` 分开返回；待采候选没有 metric 记录。跨组排名未实现。
- 本机实际 API 样例：`GET /api/browser/v1/selection/scenarios/go-http-api/viz` 返回 `selection-v44-historical-1`、截止 `2026-10-22T08:32:31Z`、4 个关系；Gin/Echo/Fiber 为 compare，Chi 为 supplement 且 `metrics_ready=false`。
- 上述实际 API `data` 载荷的字段摘录：

  ```json
  {
    "scenario": "go-http-api",
    "snapshot_version": "selection-v44-historical-1",
    "as_of": "2026-10-22T08:32:31Z",
    "candidates": [
      { "full_name": "gin-gonic/gin", "role": "compare", "eligibility": "eligible", "metrics_ready": false },
      { "full_name": "labstack/echo", "role": "compare", "eligibility": "eligible", "metrics_ready": true },
      { "full_name": "gofiber/fiber", "role": "compare", "eligibility": "conditional", "metrics_ready": true },
      { "full_name": "go-chi/chi", "role": "supplement", "eligibility": "unknown", "metrics_ready": false }
    ]
  }
  ```
- 星图 API 实际返回 300 点、0 排除、3,600 条周记录，窗口为 `2026-08-10` 至 `2026-11-02` UTC。图表支持均值/波动/PR 趋势视图、语言与 train/test 样本角色筛选、Commit/PR 阈值、真实值 tooltip、框选过滤、双击重置、候选选择和 12 周轨迹详情。x/y 的 `log1p` 变换与轴标签可见；Stars 仅用于点大小。
- 选型页默认 G1，按场景分组；G1 候选标记、列表、证据详情、平行坐标与 12 周趋势同步。G2/G3/G4 有各自的历史比较组和待采缺失状态。没有生成跨组总分或“冠军”。平行坐标保留现有 ECharts，G2 用于新的散点图。
- G1 目前只有 `net/http middleware` 这一项能力证据经过来源核验（4 个候选）；其他硬约束和 G2–G4 功能能力仍未完成来源审查。UI 将未核验状态显示为 unknown，因此当前页面不输出条件化技术推荐。

## 候选组覆盖

| 场景 | compare 数 | metrics-ready | 历史快照未完全可比 | pending | 数据源/窗口 |
|---|---:|---:|---:|---:|---|
| G1 Go HTTP/API | 3 | 2 | 1（Gin） | 1（Chi） | `featured-v1`；12 UTC 周至 2026-10-19，Release 单独 365 天 |
| G2 Python API | 2 | 1 | 1（Flask） | 1（Litestar） | 同上；Django 仅参考 |
| G3 JVM 服务 | 3 | 3 | 0 | 0 | 同上 |
| G4 前端 UI | 3 | 3 | 0 | 1（Solid） | 同上 |

指标质量合计 53 `complete`、2 `true_zero`；没有 `partial/failed/not_collected` 状态。完整指标和采样门槛不自动等价于技术优劣。完整口径见 [02-dataset-inventory.md](02-dataset-inventory.md) 与 `selection-v44-quality.json`。

## 自动化与运行验证

| 检查 | 命令/结果 |
|---|---|
| 前端类型检查与生产构建 | `npm run build --prefix frontend`：通过；内部 `vue-tsc --noEmit` 通过，Vite 构建通过 |
| 后端完整测试 | `./.venv/bin/python -B -m pytest -p no:cacheprovider --basetemp=/tmp/repovantage-v44-full tests/backend`：283 passed，7 warnings（本轮后端文件未再变更） |
| 查询预算 | `./.venv/bin/python -B -m pytest -p no:cacheprovider -s --basetemp=/tmp/repovantage-v44-budget tests/backend/test_course_research_query_budget.py`：1 passed；6 次执行均为 6 条 SQL，p50 46.73ms、p95 71.50ms。该数字是本机 pytest/SQLite 测量，不是相对旧版本的提升百分比；变更前基线未实测。 |
| 浏览器验收 | `npm run test:e2e:research-v44 --prefix frontend`：通过；1440×900 与 1920×1080 各验证星图和 G1；验证四组切换、20 次场景切换、10 次 Resize、筛选、框选/重置、候选联动、待采状态；246 次浏览器 API 请求均为 GET，无页面异常、无写入、无 GitHub/采集请求。 |
| 补充检查 | `git diff --check` 未报告空白错误。 |

最新浏览器运行的 route-to-visible-chart 时间：1440 星图 2,033ms、G1 847ms；1920 星图 1,018ms、G1 819ms。时间受本机运行状态影响，不作为性能 SLA。

验收脚本迭代时曾遇到一次框选时序超时；加 350ms 图表稳定等待后最终复跑通过。Puppeteer 当前版本没有 `page.waitForTimeout`，脚本等待改用 Node 定时器后通过。

Vite 仍报告大 chunk：ECharts 约 714KB、另一个入口 chunk 约 1.325MB（gzip 约 394KB）。构建通过，但拆包优化未纳入本次数据裁决范围。完整前端 lint 未执行，仓库没有为该页面配置独立 lint 命令。

## 截图

截图由本地浏览器实际渲染生成，保存在 `docs/research-v44/screenshots/`：

- `atlas-1440x900.png`、`atlas-1920x1080.png`：300 点星图。
- `selection-go-1440x900.png`、`selection-go-1920x1080.png`：G1 对比与候选证据详情。
- `selection-go-detail-1440x900.png`：G1 详情面板首屏。
- `selection-python-pending-1440x900.png`：Litestar 待采状态。
- `selection-python-1440x900.png`：G2 场景切换；另有早期 `selection-python-1920x1080.png`。

## 未完成与限制

1. P5 的 S2 定向采集未运行。三个补充候选仍待采；旧候选也没有刷新到共同新截止点，因此当前仅发布带历史截止时间的 S1 快照。
2. P4/P6 的硬约束证据仍是部分实现：只有 G1 的 `net/http` 条件有 4 条官方来源记录；G1 的其他约束与 G2–G4 能力证据未核验/未落库，不能作出实际推荐。敏感性接口明确返回 unavailable，不生成综合排名。
3. 变更前 N+1 性能基线没有实测，当前只记录优化后的 SQL 次数与延迟；不能声称相对旧实现提速。
4. 代码实现 reduced-motion 监听并在卸载时清理 G2 实例，但浏览器自动化没有模拟 `prefers-reduced-motion`；旧研究页、仓库详情和 ML 流程没有额外做人工浏览器验收。
5. 当前验收是本机工作区结果。`docs/` 被仓库 `.gitignore` 忽略，因此本报告和截图是本地交付文件，不会出现在普通 `git diff` 中；没有暂存、提交或推送改动。

## 本次核心代码范围

新增/更新的 v4.4 核心包括：

- 后端：`backend/app/api/v1/analytics.py`、`backend/app/services/selection_v44.py`、`backend/app/services/course_research_dataset.py`、`backend/app/persistence/models.py`、`migrations/versions/0009_selection_scenarios.py`。
- 前端：`frontend/optimized/src/pages/ResearchAtlasPage.vue`、`SelectionStudioPage.vue`、`ResearchAtlasG2.vue`、`DecisionScatterG2.vue`、`researchTypes.ts`、路由与 E2E 验收脚本。
- 数据/验证：两个 v4.4 manifest、课程事件数据包版本化元数据、`tests/backend/test_selection_v44.py`、`test_course_research_query_budget.py`。

工作区在本次继续前已有大量未提交改动（包括 `.agents/`、`.openidea/` 与 ML shadow 日志）；未清理、未覆盖。完整 `git status` 应作为当前工作区状态读取，不应把既有未提交文件全部误认为本次新增。

