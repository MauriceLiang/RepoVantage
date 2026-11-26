# GitHubDA V5：Vue 迁移与组件化重构实施手册

> 版本：V5.0｜编制日期：2026-10-16｜执行方式：**单开发者端到端负责**｜执行基线：`MauriceLiang/GitHubDA` 的 `main@31530a44edcf5c5775ce9fca21bae1860cfec40a`｜设计基线：**已确认的 V4 中文排版极简原型**。  
> 本文是**实施说明，不是已完成代码**。所有拟新增目录均为目标结构，不代表仓库现有结构。正式开工前再次执行 `git fetch` 确认主分支 SHA，发现新提交先复核差异。

## 0. 先读：不可误解的交付目标

本次改造不是继续修补 Streamlit 的 UI，也不是重新做一个无业务的 shadcn 模板。目标是：

1. **阶段 I / V5 Mock 可交互原型**：以现有 V4 HTML+CSS+JS 为视觉和业务行为基准，使用 **Vue 3 + TypeScript + Vite + shadcn-vue + Reka UI + Tailwind CSS + ECharts** 重建全部页面；**不连接 FastAPI**；所有按钮、表单、菜单、对比、图表、任务更新、导出、主题切换和移动端交互必须可用。
2. **阶段 II / 真实后端接入**：阶段 I 通过视觉、功能、Mock 测试后，保持相同 Vue 页面和组件，仅替换数据适配层，接入现有 FastAPI。所有敏感密钥必须保留在服务端；完成数据语义和端到端联调。
3. **最终产品**：不再运行 Streamlit 作为默认 Web UI；FastAPI、Worker、SQLite/迁移及统计分析尽量保留；单一开发者统一完成全链路修改、测试和交付。

### 本次必须遵守的设计共识

- 保留 V4 的**轻量、克制、中文优先、工具产品**方向；不新增英语装饰眉题、口号、巨大 Hero、乱七八糟的组件卡片墙。
- 导航只有四个主要入口：**总览 / 仓库 / 研究 / 任务**。仓库详情和比较属于仓库任务流，不占一级导航。
- 页面层级：页面标题 → 当前主操作 → 数据 / 内容主体 → 可选详细信息。一个屏幕一个明显的主操作。
- **不能因为引入 shadcn-vue 就复制官方 Dashboard 页面**。组件只提供交互基础和可访问性；具体排版和配色必须忠于 V4。
- 所有可见控件有实际作用；禁止只有 hover 效果但不可用的按钮和空的“待实现”入口。
- 有意义的数据语义不能被漂亮 UI 牺牲：未知≠0；`partial`≠失败；任务阶段进度≠数据覆盖率；历史趋势只能用真实时间观察点。
- 禁止直接复制 V4 的命令式 DOM 注入 / 全局事件路由；必须改用 Vue 模板、组件、响应式状态与路由。

## 1. 资料与权威次序

遇到不同材料冲突时，按以下优先级决策：

**产品视觉、文案及交互**：用户最新反馈 > 本文与 `02_设计规范/` > `07_V4原型资料/V4_可交互单文件.html`（交互可用性） > V4 原始 JS/CSS（仅作为行为参考） > 旧版 V1–V3。  
**真实业务语义和接口**：运行中 FastAPI `/openapi.json` + 已实现 `backend/app/api/v1` 和 `backend/app/schemas` > 真实契约测试 > 仓库历史 `docs/03_API接口契约_v1.0.md` > V4 Mock 数据。  
**新组件接口**：项目锁定依赖版本下的官方文档与实际运行 API > 本文代码片段。

V4 单文件和分离源码均已随包交付；`07_V4原型资料/预览/` 包含六张视觉基准图片。不要再让 Agent 根据主观想象重新设计页面。

## 2. 经过核对的现有架构

当前结构（仓库 `main@31530a4`）：

```text
GitHubDA/
├── frontend/                 # Streamlit 页面、组件、Python API Client、Mock
├── backend/app/api/v1/      # 已实现 FastAPI /api/v1 业务接口
├── backend/app/schemas/      # Pydantic API schema
├── backend/app/services/     # 仓库和分析服务
├── backend/app/worker/       # 数据采集 Worker
├── backend/app/persistence/  # SQLite / SQLAlchemy
├── migrations/              # Alembic
├── scripts/start.py         # 启动 API + Worker + Streamlit
├── tests/                   # 前后端现有 Python 测试
└── pyproject.toml
```

当前端点包括仓库搜索/解析、我的仓库、仓库详情/刷新/分析/趋势、任务列表/详情/重试、研究数据集/统计/数据质量、仓库比较、数据导出与系统状态。不要为了迁移而重写 Worker 或破坏已实现的算法。

**重要安全边界**：现有 `/api/v1/*` 的 `APIRouter` 通过 `require_internal_api_key` 全局依赖检查 `X-Internal-Api-Key`；Streamlit 服务端才有权读取这一密钥。Vue 浏览器不能直接持有、写入或打包该密钥。阶段 I 使用 Mock，不接触这个问题；阶段 II 必须经过安全的同源服务端入口（详见 `04_接口与安全/接口映射与安全接入.md`）。

## 3. 技术选型：定稿

| 能力 | 选型 | 原因 / 边界 |
|---|---|---|
| 框架 | Vue 3 + TypeScript，Composition API | 组件结构、精细交互、明确类型 |
| 工具 | Vite | 本地预览 / 构建，后续可静态部署 |
| 组件 | shadcn-vue（源码形式） | 统一 Button、Input、Dialog、Select、Tabs、Checkbox、Dropdown Menu 等 |
| 无样式交互基础 | Reka UI | 可访问性、键盘操作、焦点管理；优先复用 shadcn 的封装 |
| 样式 | Tailwind CSS（依照最新 Vite 插件方式）+ 设计 tokens | 避免各组件重复硬编码颜色 / 间距 |
| 图标 | lucide-vue-next | 统一线性图标 |
| 路由 | Vue Router | 直接访问 / 刷新业务深链 |
| 本地状态 | Pinia（出现跨视图共享需求后引入） | 管理选中仓库、布局主题及 Mock 状态 |
| 服务端状态 | @tanstack/vue-query | 只在连接真实 API 时使用查询缓存、失效与轮询；Mock 阶段可先保持统一 service 接口 |
| 图表 | Apache ECharts（按需引入） | 自适应、趋势、对比与研究数据图；小样本不强制绘图 |
| 测试 | Vitest + Vue Test Utils + Playwright | 业务单测、组件测试和实际浏览器场景 |
| 后端 | 原 FastAPI + Worker + SQLite | 保留，不重写 |

不引入第二套综合组件库（例如 Element Plus 与 shadcn-vue 混用）；对少量复杂需求可直接使用 Reka UI 基元做业务封装。ECharts 提供可视化，不负责业务指标计算。

官方文档参考：`https://www.shadcn-vue.com/docs/installation/vite`、`https://reka-ui.com/docs/overview/introduction`、`https://tailwindcss.com/docs/installation/using-vite`、`https://tanstack.com/query/latest/docs/framework/vue/overview`、`https://echarts.apache.org/handbook/en/concepts/dataset/`。依赖锁定后不要盲目运行持续升级脚本。

## 4. 目标工程结构（未来，非现状）

```text
GitHubDA/
├── web/                              # 新建 Vue 工程，先与 frontend/ 并存
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── components.json
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue
│   │   ├── app/router.ts
│   │   ├── app/providers.ts             # Query / Toast / 主题等统一入口
│   │   ├── styles/tokens.css
│   │   ├── styles/base.css
│   │   ├── components/ui/               # shadcn-vue 导入组件（不要全选）
│   │   ├── components/layout/           # AppShell/SideNav/TopBar/PageHeader
│   │   ├── components/domain/           # RepositoryRow/TaskStatus/Metric...
│   │   ├── pages/                       # Overview/Repositories/Detail/Compare/Research/Tasks
│   │   ├── features/repositories/
│   │   ├── features/research/
│   │   ├── features/tasks/
│   │   ├── services/contracts.ts        # 统一 RepoService 接口
│   │   ├── services/mock/               # 演示数据与可操作 Mock 实现
│   │   ├── services/http/               # 真正的 HTTP 实现（第二阶段）
│   │   ├── stores/                      # 主题/比较选择/演示状态
│   │   ├── types/                       # Repo/Task/Research/Api envelope
│   │   ├── utils/                       # 日期、单位、null、CSV、状态名称
│   │   └── charts/                      # ECharts option 生成器
│   └── tests/{unit,e2e}/
├── frontend/                         # 旧 Streamlit：迁移期间保留作回归对照
├── backend/
├── migrations/
├── scripts/
└── tests/
```

> 可以调整具体目录名，但必须保留 **页面 / 复用组件 / Mock 服务 / HTTP 服务 / 领域类型** 这五种清晰边界。不要把页面、业务数据、定时器和路由全塞进单个 App.vue。

## 5. 全站路由和页面权限

| 路由 | 页面 | 导航显示 | 核心任务 |
|---|---|---|---|
| `/` | 总览 | 是 | 输入仓库→开始分析；最近仓库/任务 |
| `/repositories?tab=saved` | 仓库 · 我的仓库 | 是 | 搜索、筛选、查看、对比、导出、移除 |
| `/repositories?tab=discover` | 仓库 · 发现仓库 | 否（内页 Tab） | 搜索公开仓库，开始分析 |
| `/repositories/:repositoryId` | 仓库详情 | 否 | 概览、活跃度、协作、数据来源、刷新 / 深度分析 |
| `/compare` | 仓库比较 | 否 | 2–5 仓库对比、切换指标、导出 |
| `/research` | 研究 | 是 | 数据集、分布、分组、相关性、质量与导出 |
| `/tasks` | 任务 | 是 | 排队/运行/异常/历史，详情和重试 |
| `/tasks/:taskId`（可选） | 任务详情 | 否 | 支持分享深链；也可先用 Drawer 实现并同步 URL |

设置优先使用全局 Dialog/Sheet，不必新增“设置”一级导航。路由失效、有缺失 ID 时应提供明确返回路径。

## 6. 共用组件：先建好，再铺页面

**每一项均必须经过实际页面复用验证。**

| 推荐封装 | 底层组件 | 使用位置 | 验收点 |
|---|---|---|---|
| `AppShell`、`SideNav` | Sidebar / 自定义 Vue Nav | 全站 | 只有四个导航；导航项高度固定；移动端 Drawer 自动关闭 |
| `PageHeader` | 字体+布局 | 各页面 | 中文短标题；非口号；描述至多一句 |
| `ActionButton` / `IconAction` | shadcn Button / Tooltip | 各页面 | 主次三级；36–40px；不允许列表纵向堆按钮 |
| `RepositorySearch` | Input + Button / Command（可选） | 总览 / 仓库 | Enter 搜索；合法输入提示；加载禁用重复提交 |
| `RepositoryListRow` | Checkbox + DropdownMenu | 仓库 | 文案截断、状态展示、操作列基线对齐 |
| `RepositoryPicker` | Command / Combobox | 对比 | 选择 2–5 个；跨页保留；区分未分析 |
| `StatusText` | Icon + 小号状态字 | 仓库/任务 | queued/running/partial/failed 正确；少用彩色大标签 |
| `Metric` | 自定义语义组件 | 总览/详情/研究 | 数值格式、未知显示、单位、时间窗口 |
| `EmptyState` | 文本 + 单个入口 | 全站 | 只提供下一步，不铺大面积空白提示框 |
| `ConfirmAction` | AlertDialog | 移除 / 重置 | Escape / Focus / 明确后果 / 取消生效 |
| `FormField` | Input / Select / Checkbox | 筛选 | label、help、error、disabled 与键盘操作 |
| `TaskProgress` | Progress + 文字 | 任务/详情 | 排队和运行更新；阶段与覆盖严格区分 |
| `ChartPanel` | ECharts | 详情/对比/研究 | ResizeObserver；隐藏/不足数据状态；可访问性替代文本 |
| `Feedback` | Sonner / Alert（控制频率） | 全站 | 成功/失败/重试有明确反馈；不铺满 Toast |
| `LoadingPlaceholder` | Skeleton | 列表/详情 | 布局稳定，不产生跳动 |

**组件使用规则**：优先使用 shadcn-vue 标准交互实现；对颜色、尺寸、边框、字重通过全局 token 和少量业务变体调整。禁止把整套 UI 复制到每个页面内，也禁止全局 CSS 粗暴覆写所有 `button` / `input`。

## 7. 页面改造规格（按实际业务闭环）

### 7.1 总览 `/`

设计基准：`07_V4原型资料/预览/总览.png`；V4 行为由 `app.js` 的 `overview()`、`analyze()` 和 `createTask()` 提供参考。

视觉结构：标题“分析 GitHub 仓库”→一句说明→ **URL/owner-repo 输入框 + 一个开始分析主按钮** → 横向 4 指标 → 近期仓库和近期任务两列（小屏改为单列）。减少或不绘制无意义的“只有一条仓库”的分布图。

- 输入合法公开仓库地址：先校验格式，再模拟解析→添加到个人仓库→生成采集任务→进入对应详情。
- 已添加仓库：打开现有详情，不重复添加，不额外制造重复任务。若需要刷新，用户在详情显式触发。
- 提交中：禁用按钮、展示加载反馈；快速双击不得制造两条任务。
- 错误：不合法输入、仓库不存在、Mock 限流场景给出明确提示，保留原输入。
- 已添加为空：显示简短下一步操作；任务为空：不显示宽大警告条。

验收：无需通过“仓库 → 发现”中转；不出现宣传式英文眉题；任务创建后状态与详情同步。

### 7.2 仓库中心 `/repositories`

设计基准：`预览/仓库.png`。两个明确的内页 Tab：“我的仓库”“发现仓库”。状态筛选与排序保持一行，屏幕变窄才折行。

- **我的仓库**：紧凑列表（名称/简介/语言/Stars/更新状态/操作）；列表项不可被每行大卡片替代。
- 所有仓库有可操作详情入口，更多菜单显示“基础刷新、深度分析、移除”；删除须确认，且只移除库成员关系，不伪称删除数据。
- 直接显示行选择 Checkbox（无需额外“多选模式”开关）；2–5 个已采集仓库才能比较；跨筛选/分页保留所选，手动清空可撤销选择。
- 未采集与部分采集项目的比较资格由**真实 API 的数据语义**决定，不以 UI 猜测；Mock 要明确禁止无快照比较、给出原因。
- 发现页：关键词/语言搜索，命中后 `开始分析`；已加入显示 `查看分析`；失败场景支持重试。
- 导出按钮调用统一 CSV 生成器，下载文件名与来源清楚说明。真实模式使用后端 CSV，不要前端重新统计替代。

验收：列表所有按钮水平对齐；键盘可操作；空列表与过滤无结果是两个不同状态；切换 Tab 保留合适的搜索状态，不污染另一个 Tab。

### 7.3 仓库详情 `/repositories/:id`

- 页首：返回仓库、`owner/repo`、真实仓库描述、状态、最近采集；右侧“基础刷新/深度分析/访问 GitHub”按主次分组。
- 内容顺序：基本指标 → 概览 / 活跃度 / 社区协作 / 数据范围 → 任务状态与采集覆盖。不要把一串指标写成营销结论。
- 趋势仅当 `observed_days >= 2` 才画线；数据缺失使用“尚未采集”或“—”，不能补伪时间点。
- 部分完成保留既有成功快照，明确展示缺失模块、覆盖时间窗口与局限；故障不覆盖旧结果。
- 刷新和深度分析调用同一任务服务；任务变化同步到任务中心。多个页面同时查看也应看到一致状态。

验收：直接刷新详情深链不丢仓库；换 Tab 不重置数据；各种 coverage 值已中文转换。

### 7.4 仓库对比 `/compare`

- 上方列出已选仓库（2–5）并可移除/新增；不足 2 个显示简短说明与返回选择入口。
- 对比表格按列显示 Stars、Forks、近90天提交/关闭 Issues/合并 PR、近一年 Release 等明确时间窗口。
- 优先展示各仓库数值，不搞无数据依据的“综合质量评分”；无数据项使用“—”，附注覆盖差异。
- 提供指标切换、根据有效值绘制小型对比图、CSV 导出（Mock 原型导出文件显式标记演示数据）。
- 改变对比仓库或分析深度时应刷新结果，防止旧对比内容滞留。

验收：不同项目类型/时间口径给出真实警告，不画虚构优势结论。

### 7.5 研究 `/research`

- 研究数据集与个人仓库库严格分离；不能把个人库“凑成”研究样本。
- 交互分区：顶部数据集 + 主要过滤 → 子视图：概览、分布、分组、相关性、数据质量。
- 未冻结数据集显著标记“当前结果不代表固定样本结论”；样本为 0 时不伪造均值、图表和相关性。
- 把语言/分组等控件控制在适中宽度，避免满屏表单；统计结果优先于复杂设置。
- 导出研究 CSV，注明数据集版本/范围；切换数据集后旧结果和旧导出失效。

验收：无研究样本/少量样本/完整样本/样本未冻结场景可验证。

### 7.6 任务 `/tasks`

- 顶部为精简状态筛选：全部 / 进行中 / 已完成 / 异常；列表按时间排序。
- 任务名称优先用对应仓库 `full_name` 而不是 `repository_id`；`task_id` 放详细信息区域。
- 排队/运行时显示任务阶段；已知阶段进度才显示百分比，不能当成 GitHub 数据覆盖率；ETA 缺失不预测。
- `queued` 和 `running` 都能自动更新；退出页面或终态立即停止对应轮询；失败后保留查询重试入口。
- 失败/部分完成可在受允许状态中手动重试，创建新任务，保留先前任务记录，防止双击导致重复执行。
- 当前无任务时保持简洁，不用高饱和色整宽警告条占据页面。

验收：模拟排队→运行→完成、失败→重试、部分完成→查看旧快照、限流等可重复运行；未完成状态改变时不会把用户输入/筛选清空。

### 7.7 设置与全局行为

- 设置通过 Dialog/Sheet 调整主题、信息密度及演示模式重置；不要求独立导航。
- 亮/深主题：CSS token 同时切换，ECharts 图表 theme 随之切换；优先持久化到本地。
- `⌘K / Ctrl+K` 打开全局搜索；支持 Escape 关闭、焦点还原与键盘上下移动。
- 桌面固定导航；小屏抽屉导航；打开后支持遮罩点击和 Escape 关闭，关闭后焦点回到触发按钮。

## 8. 阶段 I：Mock 原型落地（不要提前接真实 API）

### S0. 建基线与项目脚手架

- 检查 `git status`、读取最新 `main`，新建 `feature/vue-v5`；旧 `frontend/` 保留可运行。
- 在 `web/` 初始化 Vue 3 + TypeScript + Vite，启用 ESLint、格式化、类型检查；用 Vite 的 Tailwind 插件安装 CSS。
- 初始化 shadcn-vue（建议 `Neutral` base color），只导入当前页面用到的组件；建立 `tokens.css`。
- 创建路由与 AppShell；提交最小、可运行版本。运行 `npm run build`、`npm run typecheck` （需自行在 package.json 配置对应脚本）。

### S1. 还原 V4 的视觉系统（先静态版）

- 对照原型截图逐页搭框架；先实现 SideNav/TopBar/PageHeader/Buttons/Inputs/Tabs/Table/Dialogs。
- 使用 V4 源码理解布局，但改为 Vue SFC + 组件状态；禁止将 `app.js` 塞入 `onMounted()` 执行。
- 建立单一全局色板、字号/间距/圆角/边界 tokens；调整 shadcn 组件变量保持 V4 视觉。
- 必须截取 1440×900、1280×800、768×900、390×844 的真实浏览器页面图，对照基准。

### S2. Mock 领域层、页面和交互

- 建 `RepositoryService` / `TaskService` / `ResearchService` 等领域服务接口，Mock 与未来 HTTP 采用**相同 Promise 语义**。
- Mock 资料用明确可重置的固定种子；演示定时任务使用可控状态机；禁止实际调用 GitHub、FastAPI 或本地数据库。
- 完成四个一级页面和仓库详情/对比子流程；每页按 7 节验收；全部导出行为可验证。
- 使用本地持久化记录设置、已添加仓库和已选择集合，数据结构要有 `schemaVersion`；版本不兼容则清晰重置，不默默损坏数据。

### S3. Mock 联动与回归

- 单仓库输入→解析→添加→排队→运行→完成→查看数据；中途跨页查看同一任务；2–5 项比较；研究数据集切换；失败重试；主题切换与重置。
- Playwright 通过全部交互，按 4 种视口对照截图；确认无运行错误、页面级横向溢出、按钮错位与难以操作的 hover-only 菜单。
- 单独提交 S0、S1、S2、S3 工作进度即可，不要求多角色多个 PR；一个功能分支连续迭代、最终统一 PR。

### 阶段 I 交付门槛

**没有以下四项，不允许开始真实 API 接入**：①全部路由有可用 Mock 数据；②所有核心交互端到端通过；③四种视口基本匹配 V4 且组件精修通过；④Mock Service 完全独立于 UI 组件。

## 9. 阶段 II：真实 API / Worker 接入

阶段 II 使用同一套 Vue 页和 service interface 将 Mock Provider 切换为 HTTP Provider，**不是再做一套页面**。

### S4. 同源访问与安全适配（优先于任何真实数据请求）

- 保留 `INTERNAL_API_KEY` 仅作为服务端内部配置；不得放入 Vite env、浏览器 Cookie 可读项、前端源码或网络响应。
- 选一条明确的浏览器安全模型：建议 FastAPI 增加受会话 / Cookie / CSRF 保护的浏览器入口，服务端内部再调用现有受保护接口；或使用服务端 BFF 转发。要保证浏览器访问的是**同源**路径，例如 `/api/browser/...`，而不是直接从 JS 读内部 Key。
- 现有单一共享工作区没有用户隔离；公开部署必须增加身份鉴别和权限边界，不允许默认把个人仓库数据暴露给所有访问者。
- 开发环境可通过 Vite proxy 向本地服务转发；**proxy 不是鉴权**，不能因为代理通了就省略安全设计。
- 明确登录/会话过期、认证失败、CSRF、凭据存储、错误映射、CORS/同源、防重复请求与导出下载处理。

### S5. 实际 API 数据接入

- 从运行中 FastAPI `/openapi.json` 生成或校验 TypeScript 类型；保留 `data/meta` 响应包装及 `error/request_id` 错误体系。
- 实现 `HttpRepositoryService` 等，支持列表筛选/分页、深链、导出、任务进度、重试、研究结果。
- mutation 成功后失效相应 Vue Query 缓存；正在进行的轮询只针对 active task，终态停止；缓存寿命和频率依据真实数据变化合理配置。
- `Idempotency-Key` 保持合理复用，避免重复提交；中断重试不得凭空变更请求 ID。
- 统一中文数据状态枚举映射，时间时区、缺失值与有效样本范围都按后端返回的数据呈现。

### S6. 真实端到端验证和旧 UI 下线

- 本地跑 FastAPI + Worker + DB + Vue，至少用公开仓库完成一次真实分析；再覆盖重试、限流、空数据与深度分析。
- 更新 `scripts/start.py` 和 README：Vue 正式构建或开发服务器取代 Streamlit 默认入口，保持 Python Worker/API 启动、迁移、退出控制；避免 macOS/Windows 平台硬编码路径。
- 等新 UI 通过视觉和真实场景回归，再移除 Streamlit 依赖与旧前端目录；在此之前保留可回滚机制。
- 更新 README、部署说明、API 契约文档、测试脚本和版本历史。仓库只保留一个正式前端入口。

## 10. 执行、质量与 PR 策略

**单人开发，不区分前后端分工**。一次迭代可以同时修改 UI、API、DTO 和测试，但每个可交付步骤须有可复现验收。建议分支：`feature/vue-v5`；每完成一个 S 阶段提交 commit；最终发一个主 PR。对 API 兼容改动优先新增可选字段/非破坏性端点，避免破坏旧测试。

开工指令参考（根据工具与本机现有配置适配，不要覆盖用户未提交改动）：

```bash
git fetch origin
git status --short
git switch -c feature/vue-v5 origin/main
# 先核实 package manager 可用版本与 node 版本，再初始化 Vite
npm create vite@latest web -- --template vue-ts
cd web
npm install
npm install tailwindcss @tailwindcss/vite
# 配置 tsconfig aliases、Vite Tailwind 插件、样式入口后：
npx shadcn-vue@latest init
# 按需添加组件；版本/CLI 以官方文档为准
```

建议完整检查命令（在 `web/`，Agent 需先建立 scripts）：

```bash
npm run lint
npm run typecheck
npm run test
npm run build
npm run test:e2e
```

**拒绝条件**：出现未经允许的真实 API Key 暴露、不能双击/连续点击后可靠恢复的异常、截图和 V4 显著失配、仅有静态无交互页面、Mock 情况下偷打公网 API、数据统计造假、任一一级页面不可操作时，一律不通过验收。

## 11. 最终交付物清单

- `web/` 完整 Vue 源码与依赖锁定文件；不依赖原生 HTML 原型运行。
- `web/README.md` 说明启动/构建/Mock 与真实模式切换、环境变量及限制。
- 可直接打开的 Mock 运行地址或本地运行方式；固定测试数据与重置入口。
- Vue 组件/设计 tokens、复用服务接口与 TypeScript 类型。
- 真实 API 浏览器安全入口设计与测试（仅阶段 II）。
- 最少四个桌面/平板/移动视口的每页截图/录屏及交互自动化结果。
- API 与数据语义验收记录、失败和局限说明、构建日志、最终 PR 描述。

> 将本目录 `02–06` 作为配套文档一起给 Agent。不要只把实施手册单独发给它而不提供 V4 原型和截屏。
