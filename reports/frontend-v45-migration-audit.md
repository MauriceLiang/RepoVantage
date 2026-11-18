# RepoVantage v4.5 前端迁移审计

本记录描述当前工作区的迁移结果与验证边界。它不是远端同步、PR 或生产验收通过的声明。

## 唯一前端结构

- 唯一 HTML 入口为 `frontend/index.html`，只加载 `/src/main.ts`；`frontend/src/main.ts` 是唯一正式 `createApp()` 调用。
- 唯一路由位于 `frontend/src/router/index.ts`，覆盖总览、仓库、详情、比较、研究图谱、技术选型、任务和设置八类业务路径。
- 页面、组件、主题样式和图表均已归入 `frontend/src/`；`frontend/optimized/` 已删除。
- TypeScript 只编译 `src/**` 与 Vite 配置；Vite `@` 别名只指向 `src/`。
- 正式源码不再导入 ECharts。`package.json` 与锁文件移除了 `echarts` 和仅被它依赖的 `zrender`；Vite 不再配置 ECharts 分包。

## 路由与真实业务能力

| 路由 | 页面 | 业务来源与保留能力 |
| --- | --- | --- |
| `/` | `OverviewPage.vue` | 仓库总览、添加并分析、近期 Commit 变化、任务动态和真实快照统计；HTTP 模式由 `getOverviewDashboard()`、`getActivityTrend()` 等读取。 |
| `/repositories` | `RepositoriesPage.vue` | `RepositoryDataSource` 提供仓库列表、GitHub 搜索、添加、移除、批量清理、筛选、分页和比较入口。 |
| `/repositories/:id/:tab?` | `RepositoryAnalysisPage.vue` | 解析路由仓库 ID 与 tab；保留概览、活动、Issue、PR、Release、analysis 六个 tab、30/90/180 天窗口、采集模式、维护分析、事件分页/详情、导出和带确认的清理。 |
| `/compare` | `ComparisonPage.vue` | 2–5 个仓库、同期/各自窗口、30/90/180 天、权重校验、真实比较/评分结果和 CSV 导出；综合分 G2 图只在评分接口返回 `available` 时显示。 |
| `/research` | `ResearchAtlasPage.vue` | 通过只读 `/research/atlas` 接入冻结 300 仓库、12 周轨迹、筛选、框选和选中仓库联动。 |
| `/selection` | `SelectionStudioPage.vue` | 通过场景、可视化和候选详情接口读取版本化候选、硬约束、能力证据、来源和覆盖状态。 |
| `/tasks` | `TasksPage.vue` | 使用 `listTasks()` 与 `retryTask()` 展示服务端状态、真实进度、筛选、失败/部分完成重试和仓库跳转。 |
| `/settings` | `SettingsPage.vue` | 使用 `getCollectionSettings()` / `saveCollectionSettings()`；限制每接口 1–100 页并显示保存反馈。 |

## 正式页面图表映射

| 页面 | 业务指标 | 实现 |
| --- | --- | --- |
| 总览 | 主语言仓库构成 | G2 treemap；真实语言分组数量 |
| 总览 | Stars 分布 | G2 横向 interval；缺失 Stars 被排除，不补零 |
| 总览 | Stars–Forks–活跃周 | G2 point；对数坐标与完整值筛选明确展示 |
| 总览 | 创建年份 | G2 离散 interval，不拟合平滑趋势 |
| 总览 | 各语言周均 Commit | G2 横向 interval；完整周样本的描述统计 |
| 总览 | 0–12 活跃周分布 | G2 离散 interval，不用连续折线 |
| 研究图谱 | 300 仓库研究坐标与 12 周轨迹 | `ResearchAtlasG2.vue` G2 scatter + `G2Chart.vue` 双序列 line；保留样本选择和框选 |
| 技术选型 | 候选活动 scatter、五维证据、选中候选周轨迹 | `DecisionScatterG2.vue`、G2 parallel coordinates、G2 line；缺失指标不补零并显示排除数 |
| 项目比较 | Commit 周序列、Issue/PR 耗时、综合评分 | G2 line、G2 grouped interval、`ComparisonScoreChart.vue` 横向 interval；综合评分直接使用服务端分数 |
| 仓库详情概览 | Commit、活跃作者、Release 时间点 | G2 line/point；周记录与正式版本来自分析接口 |
| 仓库详情活动 | 作者集中度、Commit/四周均值、日历分布 | G2 Lorenz、line/interval；日历热力采用原生 Vue/CSS 格子以保留日期单元交互，不保留 ECharts |
| 仓库详情 Issue | 新增/关闭、每周差值、处理耗时 | G2 interval/line、直方图；差值只对完整周计算，缺失保持空档 |
| 仓库详情 PR | 合并数量、样本耗时、月/周中位数 | G2 interval/point/line 与耗时区间；展示单位、样本量和覆盖状态 |
| 仓库详情 Release | 正式版本时间线、相邻发布间隔 | G2 interval/timeline；真实时间戳与观察窗 |

图表底层统一使用 `G2Chart.vue` 或专项 G2 组件；实例卸载时销毁，页面提供可访问名称。正式数据缺失、部分覆盖和失败仍按接口状态呈现。没有样本时显示空态。

## 数据与目录清理核对

- `useDataSource()` 默认选择 HTTP 数据源，只有显式 `VITE_DATA_MODE=mock` 才启用演示源；HTTP 失败不回退到 Mock。
- 研究图谱与技术选型直接读取本机浏览器 API；服务不可用时显示错误与重试，不显示演示指标。
- 正式页面源码中没有 `ChartPanel`、`EChartsOption` 或 ECharts import；没有 `optimized/src` 路由或 TypeScript include。
- 原始 300 仓库课程数据、150/150 划分、后端、数据库、ML 代码均未修改。

## 验证记录

- **VERIFIED — 静态工程**：本轮改动后 `npm run typecheck` 与 `npm run build` 均通过；`npm ls --depth=0` 通过；`npm ls echarts --depth=0` 显示 `(empty)`。
- **VERIFIED — 现有数据逻辑脚本**：作者集中度、Commit 活动、耗时分布、Issue 趋势、分页记录五个脚本均通过。
- **VERIFIED — Codex 内置浏览器，真实 HTTP 模式**：用临时 Python 3.12 和隔离 SQLite 启动后端；只导入仓库内冻结快照，未启动 Worker、未请求 GitHub，也未触碰 `data/app.db`。总览显示 300 仓库、4,985,248 Stars、150 个仓库至少 9 个活跃周；六类 G2 图表均渲染。仓库列表显示 300 条并完成分页；仓库详情 overview、activity、issues、prs、releases、analysis 六个 tab 均读到历史数据、样本量和覆盖状态，详情深链接刷新后可重载。研究图谱显示 300 个节点、3,600 条周记录；选型页加载四种场景、版本快照与候选证据。项目比较用两仓库的 90 天同期数据返回可用评分，G2 评分图显示后端实际计算结果。任务页如实显示空队列；设置读取 10 页，输入 101 被拒绝、无效估算显示为未计算且错误与输入关联，随后恢复 10，未保存。
- **FIXED — 总览语言树图**：真实数据加载后复现 `children` 未定义错误；改为 G2 5 的层级 `data.value` 输入并用树路径映射分类颜色。之后内置浏览器确认矩形树图和同页其余图表正常渲染。数据格式依据 [AntV G2 树图文档](https://g2.antv.antgroup.com/en/manual/extra-topics/graph/treemap)。
- **VERIFIED — 演示模式边界**：在演示模式下比较接口返回 `insufficient_data`，评分图保持隐藏，没有伪造排名。
- **NOT TESTED**：未启动 Worker，未测试实时 GitHub 采集；其余 Puppeteer E2E、全 8 路由的浅/深主题及窄屏截图、20 次路由往返、完整 Tooltip/API 数值逐项对照未完成。页面截图通过 Codex 内置浏览器检查，但没有保存为仓库中的截图文件。一次 `test:e2e:analysis-window` 尝试无法启动独立 Chrome；按用户要求后续浏览器验收均使用 Codex 内置浏览器。
- **构建观察**：生产入口 chunk 为约 215 KB，G2 图表 chunk 为约 1.33 MB（gzip 约 394 KB），Vite 保留了超过 700 KB 的图表 chunk 警告。路由已改为按需加载；后续仍应在真实浏览器网络/渲染条件下评估图表 chunk。

## 尚未完成的交付步骤

- 已抓取 `origin/feature/polish-existing-frontend` 并核对：远端目标与本地起始 `HEAD` 均为 `96bb37e`，无分叉；当前工作分支为 `codex/v4.5-g2-unified-frontend`。
- Worker、全套 Puppeteer E2E、深浅主题八页面截图和真实 API/Tooltip 逐项数值对照仍未完成；当前浏览器验证使用隔离临时数据库中的固定历史快照，并非用户本机数据库或实时 GitHub 数据。
- 未提交、推送或创建 PR。
