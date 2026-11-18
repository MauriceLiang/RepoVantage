# RepoVantage 前端

RepoVantage 唯一正式前端使用 Vue 3、TypeScript、Vite 与 AntV G2 5。生产构建由 FastAPI 提供；默认通过本机浏览器网关读取和修改真实后端数据。Mock 数据仅在显式启用的演示模式使用。

## 本地开发

```bash
npm ci
npm run dev
```

开发服务器使用 `http://127.0.0.1:5173`，并把 `/api/browser` 代理到本机 FastAPI `http://127.0.0.1:8501`。请先启动后端。

```bash
VITE_DATA_MODE=http npm run dev   # 真实后端，默认模式
VITE_DATA_MODE=mock npm run dev   # 明确启用演示数据
npm run build                    # 类型检查 + 生产构建
```

项目入口、唯一路由和页面均位于 `src/`；Vite 只将 `@` 指向 `src/`。仓库根目录的 `python -m scripts.start` 会构建本目录并启动 FastAPI 与 Worker；FastAPI 在 `http://127.0.0.1:8501` 同时提供 API 和 Vue 页面。

## 页面

- `/` 总览：真实仓库、近期变化、任务动态、添加仓库与统计图
- `/repositories` 仓库管理：搜索、添加、筛选、移除、批量删除与比较入口
- `/repositories/:id/:tab?` 仓库详情：`overview`（含维护行为与模型信号）、`activity`、`issues`、`prs`、`releases`；旧 `analysis` 地址会跳转到 `overview`
- `/compare` 项目比较：2–5 个仓库、共同/独立时间窗、维度权重与 CSV
- `/research` 300 仓库研究图谱
- `/selection` 技术选型工作台
- `/tasks` 真实任务状态、筛选和失败重试
- `/settings` GitHub 深度采集页数设置

## 数据边界

前端通过 `RepositoryDataSource` 接口访问数据。默认实现使用带 CSRF 校验的本机浏览器 API 会话，不在浏览器中暴露内部 API Key。仓库分析使用已归档的 Commit、Issue、PR 和 Release 事件；本地逐条记录由详情接口提供，Issue 和 PR 正文可按需在线获取。数据缺失或覆盖不足时显示对应状态，不用估算值补齐。真实模式发生错误不会静默回退 Mock。
