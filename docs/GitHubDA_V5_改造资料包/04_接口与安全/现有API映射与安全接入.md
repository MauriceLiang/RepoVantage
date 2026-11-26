# GitHubDA V5：现有 API 映射与浏览器安全接入

> 基于仓库 `main@31530a4` 中已实现的 `frontend/api/client.py`、`backend/app/api/v1/`、`backend/app/main.py`、`backend/app/api/dependencies.py`，并结合现有 DTO 和接口说明整理。  
> **正式契约以实际运行的 FastAPI `/openapi.json` 和测试为准**。历史文档 `docs/03_API接口契约_v1.0.md` 中部分描述仍标记为“拟定”，不能在没校验实现时盲目当作生产事实。

## 1. V4 Mock 功能到真实接口对照

| 产品功能 | 已有 FastAPI 接口 | 关键限制 / UI 解释 |
|---|---|---|
| 系统健康 | `GET /healthz` | 无内部 Key；仅健康检查 |
| 系统状态/队列 | `GET /api/v1/system/status` | API/DB/Worker/限流信息，不要等同真实可分析状态 |
| GitHub 公开仓库搜索 | `GET /api/v1/github/search` | `q`, language, stars_min, sort, page, per_page；搜索窗口上限需遵循后端 |
| 解析 owner/repo / URL | `POST /api/v1/github/resolve` | 验证合法性，返回仓库预览 |
| 加入个人库并入队 | `POST /api/v1/library/repositories` | `auto_analyze=true`, `depth=basic`, 支持 `Idempotency-Key` |
| 我的仓库与筛选 | `GET /api/v1/library/repositories` | `q,status,sort,order,page,per_page`；服务端分页 |
| 从个人库移除 | `DELETE /api/v1/library/repositories/{repository_id}` | 204 无 body；只移除成员关系 |
| 仓库详情 | `GET /api/v1/repositories/{repository_id}` | 可通过 URL 深链直接进入 |
| 基础刷新/深度分析 | `POST /api/v1/repositories/{repository_id}/refresh` | `depth`, `force`, `Idempotency-Key` |
| 查看分析结果 | `GET /api/v1/repositories/{repository_id}/analysis` | `depth=basic/deep`；覆盖信息与采集状态分开 |
| 仓库真实观测点 | `GET /api/v1/repositories/{repository_id}/series` | `metric=stars/forks`；不可凭空填充没采集的历史 |
| 全部任务 | `GET /api/v1/tasks` | 状态/仓库 ID/分页；不是仓库名称，需要 UI 自行关联或后端补充字段 |
| 任务详情 | `GET /api/v1/tasks/{task_id}` | 支持阶段进度、模块与 ETA 可空 |
| 重试任务 | `POST /api/v1/tasks/{task_id}/retry` | 仅 failed/partial 允许；生成新任务；支持幂等 |
| 研究数据集 | `GET /api/v1/datasets` | 区分研究样本/个人库 |
| 总览统计 | `GET /api/v1/overview` | `scope=library/research`；不得混用统计口径 |
| 研究统计 | `GET /api/v1/research/statistics` | dataset_id, language, group_by |
| 研究数据质量 | `GET /api/v1/research/data-quality` | 质量报告与研究筛选范围需区分 |
| 仓库对比 | `POST /api/v1/comparisons` | 选定 2–5 仓库，数据覆盖和警告信息独立呈现 |
| 数据导出 | `GET /api/v1/exports/repositories.csv` | scope、dataset_id、language；按 CSV Blob 下载 |

详细字段以 `backend/app/schemas/` 与当前 `frontend/api/models.py` 为映射依据。推荐把 `/openapi.json` 生成的原始 TS DTO 留在 `web/src/services/http/generated/`，再定义稳定的 UI domain model；将蛇形字段转换放在 adapter，不散落到页面。

## 2. 当前内部认证机制（必须正视）

现有代码：

```py
# backend/app/api/v1/__init__.py（结构示意）
router = APIRouter(prefix='/api/v1', dependencies=[Depends(require_internal_api_key)])
```

`require_internal_api_key()` 接收 `X-Internal-Api-Key`，服务端与本地 `.env` 的 `INTERNAL_API_KEY` 比较。当前 Streamlit 服务端会通过 Python httpx 客户端设置此请求头，浏览器不知道密钥。

**禁止的 Vue 接法：**

```ts
// 绝对禁止：任何 VITE_* / 打包结果对访问页面的人可见
const key = import.meta.env.VITE_INTERNAL_API_KEY
fetch('/api/v1/tasks', {headers: {'X-Internal-Api-Key': key}})
```

也不能用“藏在 Pinia、localStorage、混淆构建后的 JS”来解决。密钥在浏览器里就是暴露的。

## 3. 推荐的正式接入形态

```text
浏览器 Vue 3 SPA  -- HTTPS / 同源 Cookie --> 浏览器网关 / FastAPI BFF
                (不含内部 API Key)       | 认证/会话/CSRF/限流
                                         |
                                    服务端调用
                                         v
                                 既有 /api/v1/*
                                         |
                         FastAPI Services + SQLite + Worker
```

可选方案 A：FastAPI 增加 `/api/browser/*` 的同源、受登录会话保护的浏览器 API；在服务器内依照既有服务层执行业务，不一定非要以 HTTP 方式自调用。

可选方案 B：单独受保护 BFF（Node/Python 皆可），使用服务端密钥调用既有 `/api/v1/*`。本项目更建议 **A**，减少进程和部署复杂度；要求路由职责明确且不绕过授权。

**重要**：现有项目属于单一共享工作区，尚无账户与仓库所有权隔离。若仅本机自己使用，可限制 localhost 访问并说明风险边界；若公网部署/多人使用，必须先做认证/授权与数据隔离，不能只凭隐藏导航项当权限校验。

### 登录 / 会话实现验收要求

- HttpOnly、Secure（HTTPS）且合适 SameSite 策略的会话 Cookie；服务端控制过期和撤销。
- 任何有副作用的浏览器 Cookie 请求配套 CSRF 防护和 Origin 校验；限制允许来源。
- 用户会话过期给出可恢复引导，不无限重试。
- 服务端错误可安全地传回 `error.code/request_id`，不得暴露凭据、堆栈或敏感系统位置。
- 多人环境必须验证仓库/任务资源访问的所有权或工作区权限。
- 若本机单用户模式未启用完整账户系统，严格限 `127.0.0.1` 并明确标注不能直接公网部署。

## 4. Mock Provider 与 Http Provider 切换规则

建议入口只做一次环境分流，页面全部无感：

```ts
export const services = import.meta.env.VITE_DATA_MODE === 'mock'
  ? createMockServices()
  : createHttpServices() // HTTP 仅连接已安全适配的浏览器路由
```

`VITE_DATA_MODE=mock` **不是安全控制**，只是 Mock/真实切换。实时模式必须通过安全的服务端入口，生产环境不能把内部密钥或 GitHub Token 暴露给客户端。

- mock 服务可使用可控延迟 100–400ms，任务有明示的模拟阶段。
- http 服务应处理连接超时、request_id、校验错误、429、503 和取消中的 fetch AbortSignal。
- TanStack Vue Query 只缓存服务端查询，不要用它存浏览器 UI 选择框状态；mutation 失效具体 queryKey。
- CSRF Token（若实现）遵循服务端规范，不从不可信 URL 中取得任意 secret。

## 5. 重要数据语义映射

| 后端字段 | UI 示例 | 禁止行为 |
|---|---|---|
| `null` 数值 | `—` / `未采集` | 误显示为 0 |
| `status=queued` | `排队中` | 直接显示“正在采集” |
| `status=running` | `运行中` | 伪称成功 |
| `status=partial` | `部分完成` | 视同全部数据失败/全部完成 |
| `data_status=stale` | `展示上次成功快照` | 把过期数据丢弃或当实时 |
| `progress_kind=stages` | `阶段进度` | 当“覆盖了 GitHub 百分之 xx” |
| `eta_seconds=null` | 无可靠完成时间 | 编造 ETA |
| `source_metadata.coverage` | `完整/部分覆盖/未采集` | 仅凭任务结束设置为完整 |
| 样本 `n=1` | `样本不足，暂不绘图` | 伪造分布趋势 |

## 6. 一键启动改造注意事项

现有 `scripts/start.py` 同时启动 API、Worker、Streamlit（8501）。正式迁移需使其运行 API/Worker + Vue 开发预览或生产静态页面；首次迁移不要提前删除旧进程配置。

- Mock 阶段：只启动 `web` Vite，**不要求 Python 后端启动**。
- 真实阶段：启动后端和 Worker，运行迁移，再加载 Vue；确认新旧两套运行方式不使用相同端口互相冲突。
- 配置隔离：`INTERNAL_API_KEY` / `GITHUB_TOKEN` 继续保留在服务端；前端仅使用公开非敏感配置。
- 移除 Streamlit 前先运行现有 Python tests 和新 Vue tests，完成生产启动、停止及跨平台验证。

## 7. 需要额外修改后端的功能清单（按需）

1. 任务列表若要求直接显示仓库名：前端可通过已有 `repository_id`+库列表映射；不在当前库中的历史任务应允许后端返回 `full_name` 可选字段，或增加批量查询，避免 N+1。
2. 浏览器认证/BFF：必做且优先级最高。
3. 研究图表需要新数据维度时：先检查已有 `research/statistics` 与 DTO，确认现有能力不足再新增兼容字段。
4. 较大数据集的筛选/分页，应在后端实现，不能为了好看在前端一次性加载全量记录。
5. 实时任务更新：初期使用适度轮询，只有真实性能瓶颈时再评估 SSE/WebSocket，不预先增加复杂度。
