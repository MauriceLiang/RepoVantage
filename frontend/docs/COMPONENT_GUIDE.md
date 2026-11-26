# 组件指南

## 目录

```text
src/components/
├── charts/   G2 5 统一容器与业务图表；日历热力采用 Vue/CSS
├── common/   KPI 指标、观察列表、事件抽屉等共用组件
├── layout/   导航、顶栏相关布局、详情页签和仓库页头
├── optimized-ui/ 新版视觉系统的按钮、面板、输入和页面标题
└── ui/       既有业务控件、卡片、覆盖提示、抽屉与 toast
```

## 图表

正式图表通过 `charts/G2Chart.vue` 创建 G2 5 实例。它负责容器自适应、浅/深主题重绘、异步更新竞态处理、点击事件和卸载时销毁。业务图表按 G2 `mark`、`encode`、`scale` 和 `interaction` 组合，不使用 ECharts option 兼容层。

| 组件 | 数据与用途 |
|---|---|
| `TrendChart` / `GroupedChart` | UTC 时间序列；同时保留观测值与覆盖字段 |
| `HistogramChart` | 后端返回的耗时桶；只展示区间数据，不推测桶内值 |
| `CommitActivityComboChart` | 分开的 Commit、活跃账号和 Release 图；附可访问周数据列表 |
| `CommitAuthorStackChart` | 作者、其他/未关联账号的每周提交堆叠与四周均值 |
| `IssueTrendChart` | 新增/关闭周柱和完整周差值，附覆盖状态列表 |
| `PrMergeTrendChart` / `PrMonthlyDurationChart` | 合并数、逐条耗时、周期分布与中位数按单位拆图 |
| `ReleaseCadenceChart` / `ReleaseIntervalMiniChart` | 相邻正式 Release 的真实间隔天数 |
| `TimelineChart` | 实际 Commit 周趋势与正式/预发布日期泳道，支持日期筛选 |
| `ComparisonChart` / `ComparisonDurationChart` | 后端实际返回的候选时间趋势和耗时对比 |
| `ResearchAtlasG2` / `DecisionScatterG2` | 300 仓库研究图谱和候选散点/平行坐标 |
| `CalendarHeatmap` | Vue/CSS UTC 日期网格，保留 true zero、partial、missing 状态 |

新增图表前先确认 `RepositoryDataSource` 提供字段、单位、来源、窗口和覆盖含义。`null` 不补零。图表需有可访问名称与可见的指标解释；交互结果不得只用颜色表示。

## 布局与通用组件

| 组件 | 用途 |
|---|---|
| `NavigationSidebar` | 唯一正式侧栏和路由导航 |
| `ModuleTabs` / `RepoHeader` | 仓库详情模块导航和真实仓库操作 |
| `UiPageHeader` / `UiPanel` / `UiButton` | 新版页面标题、面板与基础控件 |
| `GdCard` / `GdCoverageNote` / `GdEmptyState` | 既有真实业务页面的卡片、覆盖提示和空态 |
| `EventDrawer` / `GdToastHost` | Commit、Issue、PR、Release 和指标口径抽屉；反馈消息 |

## 数据和状态

- 数据只通过 `useDataSource()` 选择的 `RepositoryDataSource` 获取。Mock 只在显式演示模式使用。
- 加载、空、失败和部分覆盖均显示明确状态；页面不得隐藏数据源错误或估算缺失值。
- 新增路由在 `src/router/index.ts` 注册，并同步 `frontend/docs/PAGE_STRUCTURE.md`。
