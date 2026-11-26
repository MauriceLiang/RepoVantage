# RepoVantage v4.5 P0 迁移基线审计

日期：2026-11-15  
分支：`codex/v4.5-g2-unified-frontend`  
基线：`96bb37e feat: add v4.4 research and selection workspaces`  
目标分支：`feature/polish-existing-frontend`（当时与基线同 SHA）

## 工作区边界

开始时工作区已有用户本地内容：`ml-production/scheduling/logs/ml01-shadow.stdout.log` 修改，`.agents/` 与 `.openidea/` 未跟踪。本次迁移不包含这些路径。

## 入口、路由与功能映射

| URL | 当前生产路由页面 | 真实能力来源/目标验收 |
|---|---|---|
| `/` | `optimized/src/pages/OverviewPage.vue` | 总览真实仓库、趋势、任务、添加仓库；盘点旧 `src/pages/Overview/` 的数据逻辑和全部六张总览图 |
| `/repositories` | `optimized/src/pages/RepositoriesPage.vue` | 真实仓库搜索/新增/删除/比较；盘点旧页面筛选、批量删除流程 |
| `/repositories/:id/:tab?` | `optimized/src/pages/RepositoryAnalysisPage.vue` | 当前路由指向 `src/pages/RepositoryAnalysis/RepositoryAnalysisPage.vue`；须保留 overview/activity/issues/prs/releases/analysis、采集、事件详情、导出和 ML |
| `/compare` | `optimized/src/pages/ComparisonPage.vue` | 当前路由指向旧真实比较页；迁移窗口、权重、质量说明和 CSV，排除原型 Mock 分数 |
| `/research` | `optimized/src/pages/ResearchAtlasPage.vue` | 新 G2 图谱与真实研究数据；迁移剩余 ECharts 趋势 |
| `/selection` | `optimized/src/pages/SelectionStudioPage.vue` | 新真实场景筛选和 G2 散点；迁移平行坐标与 12 周图 |
| `/tasks` | `optimized/src/pages/TasksPage.vue` | 当前路由指向旧真实任务页；使用 `listTasks()` / `retryTask()`，不保留 MockTask |
| `/settings` | 路由指向旧 `src/pages/Settings/SettingsPage.vue` | 新视觉中重建；保留 `getCollectionSettings()` / `saveCollectionSettings()` 及 1–100 校验 |

`frontend/index.html` 当前加载 `/optimized/src/main.ts`。`optimized/src/router.ts` 是活跃业务路由；其 8 条路由与上述矩阵一致，部分页面通过 `@/pages` 实际引用旧页面。最终应只有 `frontend/src/main.ts`、一套 App/Router，且 `frontend/optimized/` 完全删除。

## 图表迁移清单（P0 静态源码盘点）

| 页面/区域 | 当前业务图/组件 | 目标与数据真实性要求 |
|---|---|---|
| 总览 | 六个 `ChartPanel` 图：语言构成、Stars、Stars/Forks、创建年份、语言周均 Commit、活跃周数 | G2 treemap/interval/point；从真实总览响应取值，保留 null 与筛选说明 |
| 仓库详情 Overview | 提交活动、作者分布/集中度、日历热力等旧图表组件 | G2；以真实 UTC 周/贡献数据为准，日历若 G2 不合适可采用 Vue/CSS 并记录理由 |
| 仓库详情 Activity | Commit activity、作者贡献/集中度、日历 | G2；沿用原查询窗口与样本口径 |
| 仓库详情 Issues | issue 新增/关闭趋势、处理耗时 | G2；真实快照和耗时样本，显示样本量、覆盖/空态 |
| 仓库详情 PRs | PR 合并趋势、处理耗时 | G2；真实快照和耗时样本 |
| 仓库详情 Releases | release 时间线、发布间隔/节奏 | G2；真实 release 时间戳和观察窗口 |
| 仓库详情 Analysis | 研究/质量/维护比较图（依所选分析数据） | G2；沿用 ML 结果、来源与数据覆盖说明 |
| 项目比较 | 比较分数及耗时图 | G2；只展示真实比较服务评分和真实样本 |
| 研究图谱 | G2 300 仓库散点 + ECharts 周趋势 | 保留现有 G2，周趋势迁 G2 并与选中样本联动 |
| 技术选型 | G2 候选散点 + ECharts 多维比较/12 周趋势 | 保留散点；迁移平行坐标及真实周趋势，严格保留 null/覆盖状态 |

源码中旧 `src/components/charts/` 有 18 个 ECharts 图表/辅助文件：`CalendarHeatmap`、`ComparisonChart`、`CommitActivityComboChart`、`CommitAuthorStackChart`、`AuthorConcentrationChart`、`GroupedChart`、`HistogramChart`、`ScatterChart`、`TrendChart`、`IssueTrendChart`、`PrMergeTrendChart`、`PrMonthlyDurationChart`、`ComparisonDurationChart`、`TimelineChart`、`ReleaseCadenceChart`、`ReleaseIntervalMiniChart`、`ResearchGroupComboChart`、`ResearchQualityChart`，另有 `EChart.vue`、`options.ts`、`theme.ts`、`comboHelpers.ts`。逐个组件的实际调用及其数据输入还需在迁移时用 `rg` 完成引用核对。

原型中的 `optimized/src/components/ChartPanel.vue` 为 ECharts 容器；`optimized/src/pages/ResearchPage.vue`、`ComponentGalleryPage.vue` 和 `optimized/src/data/mockData.ts` 需在依赖清理时确认仅供原型使用并删除。正式 HTTP 模式不能继承原型中的固定倍数 Issue/PR 或 Release 月度序列。

## 构建配置与基线

- `frontend/index.html`：`/optimized/src/main.ts`。
- `frontend/package.json`：同时包含 `@antv/g2` 与顶层 `echarts`。
- `frontend/vite.config.ts`：包含 ECharts 手动分包。
- `frontend/tsconfig.json`：同时包含 `src/**` 与 `optimized/src/**`。
- v4.5 改动前 `npm run build --prefix frontend` 通过；当时 ECharts chunk 约 714 KB、应用 chunk 约 1.325 MB，存在大 chunk 提示。
- v4.5 改动前 `./.venv/bin/python -B -m pytest -p no:cacheprovider --basetemp=/tmp/repovantage-v45-baseline tests/backend`：283 passed，7 warnings。
- 本地 API 服务 `127.0.0.1:8000`（PID 20273）已存在，服务读取根 `frontend/dist`，不应停止。
- v4.4 基线截图位于忽略目录 `docs/research-v45/baseline/light/`；覆盖总览、仓库列表、详情六 tab、比较、研究、选型、任务、设置。无仓库预选的比较截图是空态，后续须补充有真实候选的比较验证。

## 数据/Mock 边界

保留 `frontend/src/services/repositoryDataSource.ts`、HTTP 和显式 Mock 数据源、数据类型、stores、composables、真实 tabs 的业务调用。`optimized/src/data/mockData.ts` 是原型数据，不能接入正式页面。既不重写仓库样本或 ML 150/150 划分，也不清理本机数据库和原始采集文件。

## P0 未完成项

- 核对并记录迁移分支相对目标远端的最新 fetch 时间/HEAD；当前只读环境下网络受限，先前会话已核实两者为 `96bb37e`。
- 对旧图表逐组件记录真实调用处、原始字段/单位、时间窗、缺失状态及新的 G2 表达；上表是路由/组件级盘点，尚不能作为图表迁移完成证据。
- 重新跑 v4.4 相关前端 E2E 作为本次分支执行时的 P0 基线。
