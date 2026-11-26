# GitHubDA V5：Vue + shadcn-vue 改造资料包

本资料包是**开发交接资料**，不是已经完成的 Vue 工程；不能直接 `npm run dev` 运行此资料包。它包含已确认的 V4 可交互 HTML 原型、分离源码、页面截图、设计和文案规范，以及单开发者实施手册、Mock 交互规格、现有 FastAPI 接入边界、验收矩阵和可直接使用的 Agent 执行指令。

## 本次决策

- **已确认的 UI/UX 基准：V4 中文极简原型**。没有英文装饰标题和营销式文案。保持四个主导航：总览 / 仓库 / 研究 / 任务。
- **新技术栈**：Vue 3 + TypeScript + Vite + shadcn-vue / Reka UI + Tailwind CSS + Apache ECharts。
- **第一阶段 Mock-first**：先做全页面、全交互、可恢复/可重置的 Vue 原型，不连接真实 API。
- **第二阶段接入**：保留 FastAPI / Worker / SQLite，建立安全的浏览器接入层后改为真实数据。
- **开发组织**：单人统一负责全栈改造，不划分“前端负责人/后端负责人”，按照 S0–S6 阶段验收，最终统一 PR。

## 阅读顺序

| 文件/文件夹 | 用途 |
|---|---|
| `01_实施方案/GitHubDA_V5_Vue迁移与组件化重构实施手册.md` | **主文档**：所有实现阶段与页面规格 |
| `02_设计规范/V5_设计系统与组件替换规则.md` | 组件库应用原则、色板、字号、布局和反 AI 模板规则 |
| `02_设计规范/V4_既有文案排版规范.md` | 用户已确认的中文文案和视觉表达原则 |
| `03_交互与Mock/Mock数据与交互状态机.md` | Mock 领域模型、完整交互与数据真实性规则 |
| `03_交互与Mock/Mock场景索引.json` | Mock 场景目录（非可执行数据服务） |
| `04_接口与安全/现有API映射与安全接入.md` | 现有 API 对应关系与浏览器认证底线 |
| `05_测试验收/测试矩阵与交付门槛.md` | T01–T30 检验清单，截图与安全检查 |
| `06_Agent执行/直接交给Agent的执行指令.md` | 复制发给开发 Agent 的完整任务提示 |
| `07_V4原型资料/V4_可交互单文件.html` | **视觉与行为参考**，无需依赖即可浏览器打开 |
| `07_V4原型资料/源码/GitHubDA_V4/` | V4 HTML/CSS/JS 可编辑原文件；只能作参考，不能作为 Vue 产出交付 |
| `07_V4原型资料/预览/` | 总览、仓库、研究、任务、深色、移动端截图 |

## 已核对的源码基线

- GitHub：`https://github.com/MauriceLiang/GitHubDA`
- 已审查 commit：`31530a44edcf5c5775ce9fca21bae1860cfec40a`
- 检查日期：2026-10-16
- 新开工必须再次确认最新 main；如果 HEAD 前进，不可直接用旧文档覆盖新功能。

## 阶段状态（截至交付包创建时）

| 阶段 | 状态 |
|---|---|
| V4 HTML 原型与 Mock 演示 | 已有，可作为基准 |
| V5 Vue 新工程 | 尚未实现 |
| V5 Vue Mock 全站交互 | 尚未实现 |
| V5 实际 FastAPI 连接与认证改造 | 尚未实现 |
| V5 正式上线与替换 Streamlit | 尚未实现 |

> 重要安全说明：现有 `/api/v1/*` 要求内部 API Key。不能直接在 Vue 代码中放置内部密钥。Mock 阶段完全不需要内部密钥；真实阶段必须有受保护的服务端浏览器入口。

## 第一次给 Agent 怎么发

请将**整个 ZIP 资料包**提供给 Agent，在仓库根目录解压到例如 `docs/handoff/githubda-v5/`（不要覆盖应用代码）。先发送 `06_Agent执行/直接交给Agent的执行指令.md`，要求 Agent 按目录阅读引用材料，并从 S0 开始。

只将 `V4_可交互单文件.html` 发给 Agent，可能导致 Agent 忽略后端契约与安全问题；只发 PDF/截图又会丢失可交互业务流程，所以这次同时交付了源文件、规范与实施文档。

## 官方文档导航（在线，不包含第三方源码）

- Vue: https://vuejs.org/guide/introduction.html
- Vite: https://vite.dev/guide/
- shadcn-vue（Vite 安装）：https://www.shadcn-vue.com/docs/installation/vite
- Reka UI: https://reka-ui.com/docs/overview/introduction
- Tailwind CSS + Vite: https://tailwindcss.com/docs/installation/using-vite
- Apache ECharts: https://echarts.apache.org/handbook/en/get-started/
- TanStack Vue Query: https://tanstack.com/query/latest/docs/framework/vue/overview
- Playwright: https://playwright.dev/docs/intro
- Vue Test Utils: https://test-utils.vuejs.org/

引用的库文档可能随发布发生变化；执行时按项目锁文件与版本的官方文档核查，不靠猜测 CLI 名称或组件路径。
