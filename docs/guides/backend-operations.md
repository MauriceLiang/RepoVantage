# RepoVantage 后端

后端由 FastAPI、SQLite、Alembic 和独立 Worker 组成。它通过 GitHub REST API 读取公开仓库，保留原始响应归档、指标快照和分析任务历史。

## 环境

项目按 Python 3.12 运行。创建虚拟环境并安装依赖：

```bash
uv sync --locked --all-extras
source .venv/bin/activate
cp .env.example .env
```

完整项目可直接使用下方的一键启动命令；启动器会在缺少 `.env` 时创建文件并生成仅本机使用的 `INTERNAL_API_KEY`。手动启动时，可在 `.env` 中配置该密钥。`GITHUB_TOKEN` 可选；未配置时使用 GitHub 匿名额度。密钥只由 API 和 Worker 进程读取。

默认 SQLite 文件固定解析到仓库根目录的 `data/app.db`，不受启动时当前目录影响。兼容旧版的原始压缩 JSON 写入 `data/raw/`；新版逐页采集归档写入 Git 忽略的 `data/collected/`。仓库页只列出 15 个精选仓库和用户主动添加的仓库；机器学习的 300 个研究仓库、150 个留出组及历史事件仅供机器学习页和详细研究视图使用，不混入仓库列表。安装或升级时，程序会一次性将精选集加入仓库列表，并清理旧版本误加的 300 仓库成员。用户之后移除的精选仓库不会在重启时自动恢复。可用 `DATABASE_URL` 与 `RAW_DATA_DIR` 覆盖旧版归档路径。

## 数据库与启动

完整项目只需在仓库根目录运行这一条命令：

```bash
uv run --locked --all-extras python -m scripts.start
```

启动器会分别构建两套前端，自动升级数据库，并启动 FastAPI、Worker、普通用户页面和独立机器学习控制台。访问地址分别为 `http://127.0.0.1:8501` 和 `http://127.0.0.1:8502`；两套前端共享 FastAPI 的本机浏览器会话/API 层。首次运行会创建 `.env` 并生成本机随机 `INTERNAL_API_KEY`。按 `Ctrl+C` 会一并停止所有服务。新前端仅允许绑定本机回环地址；完整使用说明见[项目首页](../../README.md)。

若 API 已由其他方式启动，也可单独运行 `uv run --locked --all-extras python -m scripts.start_ml_console` 启动 8502 控制台；日常启动完整项目无需使用该命令。

需要单独调试后端时，可手动运行迁移并分别启动 API 与 Worker：

从空库执行迁移：

```bash
alembic upgrade head
```

分别启动 API 与 Worker：

```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8501
python -m backend.app.worker.main
```

健康检查为 `GET /healthz`。其余 `/api/v1/*` 请求须带 `X-Internal-Api-Key`。`/api/browser/*` 是给同源 Vue 前端使用的本机会话入口；密钥不会下发到浏览器。`/docs` 和 `/openapi.json` 用于本机联调，服务默认只绑定回环地址。

## 数据分类与课程样本

应用启动时会校验并导入 300 个历史仓库与 12 周特征；固定的 150 成员 `test` 分组仍用于模型留出评估。完整数据集保留 `train` / `test` 角色供机器学习页追溯。导入过程不请求 GitHub，也不会把这 300 个仓库放入仓库页或用户比较列表。

`data/datasets/course-research-events-300-v1/` 保存 300 个仓库的 Commit、Issue、PR 和 Release 历史事件，供机器学习页的详细数据视图读取。事件快照的统一分析截止时间为 2026-11-05；Issue 可能遗漏采集起点之前创建、之后关闭的记录，少数模块标为部分覆盖。快照未保存提交说明、Issue / PR 标题和正文。首次读取时会校验并解压到 `RAW_DATA_DIR`；可以用 `scripts/build_course_test_events.py` 从 `dataprepare/MachineLearn/run/repo-evaluation-2026-v1/collection.sqlite3` 重新生成。

仓库页初始列表来自 `featured-v1` 的 15 个精选仓库。仓库比较只对用户在仓库页选择的项目计算；应用启动时不创建预设技术选型场景、候选清单或排名快照。

## API

完整接口定义以运行中的 `/docs` OpenAPI 文档为准。实现覆盖 API-01 至 API-20（API-01 为 `/healthz`）：搜索/解析、分析库、仓库快照与分析、任务/重试、数据集、总览/研究统计/质量、比较和 CSV 导出。JSON 成功响应采用 `data`/`meta`，错误采用 `error`/`request_id`；删除成员关系返回空的 204，CSV 为 UTF-8 文本。

Worker 对基础仓库档案采集真实快照。深度任务支持 `quick`、`window` 和人工排队的 `backfill`，所有范围都读取 `.env` 的 `GITHUB_MAX_PAGES` 配置。Commit/Issue 使用时间查询，PR 按更新时间倒序并在重叠边界停止，Release 端点逐次复核并按数字 ID 去重。系统不再定时排队仓库刷新或增量采集；新加入的仓库会自动排队完整 180 天窗口采集，后续仅在用户点击详情页的更新数据操作时排队同样的 180 天更新。页面仍可切换 30、90、180 天分析窗口。

深度采集默认通过分页拉取所选时间窗内的全部 Commit、Issue、PR 和 Release，直到 GitHub 没有下一页，确保后续分析不因固定页数截断。项目根目录 `.env` 中的 `GITHUB_MAX_PAGES=0` 表示不限页；`1`–`10000` 是每个接口的页数上限，达到后该模块可能为部分完成。设置上限可控制请求量，但无法保证非常活跃的仓库完整覆盖。每页最多请求 100 条，因此不限页数比任意有限默认值更适合作为分析默认值。修改页数上限后需重启 API；新建任务采用新值，已排队任务沿用创建时保存的上限。

设置页可保存个人 GitHub fine-grained token。令牌写入本机 `.env`（权限设为仅当前用户可读写），Worker 会在领取下一项任务前重新读取；API 不会回传令牌本身。公开仓库的只读请求通常不需额外权限；私有仓库应仅授权所需仓库和读取权限。GitHub 文档说明未认证 REST API 主额度为 60 次/小时，认证个人请求通常为 5,000 次/小时；账户共享额度和次级限流仍适用。创建令牌步骤见[官方个人访问令牌说明](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)，限流细节见[REST API 限流说明](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)。

历史回填只针对五个试点仓库提供 CLI 入口，默认仅预览本地数据库中已存在的仓库；加 `--queue` 才会写入任务队列。每次回填按用户页数预算让出 Worker，保留检查点并继续排队，普通任务优先。CLI 本身不访问 GitHub；实际请求只会在 Worker 执行时发生。有限页数预算下，任务进度按当前模块已获取页数推进，并在模块结束时推进阶段；总量未知的完整时间窗任务显示动态进度。预算耗尽、部分覆盖和配额延期不会被标为完整；进度只表示任务执行过程，不代表历史覆盖率。星标时间序列只包含真实采集日期，不插值。

仅在需要重新采集整个数据集时，可为成员排队任务（实际 GitHub 请求由 Worker 执行，会消耗额度）：

```bash
python -m scripts.collect_dataset course-research-300-v1 --scope window
```

预览五个历史回填试点（不会写入任务）：

```bash
python -m scripts.queue_history_pilot
```

审核预览后，使用 `--queue` 将可用仓库排入后台队列；GitHub 请求由 Worker 之后执行：

```bash
python -m scripts.queue_history_pilot --queue
```

15 仓库精选包是仓库页初始列表的数据来源。CLI 可生成、校验和导出精选包；导入会写入当前 `DATABASE_URL` 指向的数据库：

```bash
python -m scripts.build_featured_bundle --version featured-v1.0.0
python -m scripts.verify_dataset_bundle data/datasets/featured-v1
python -m scripts.export_dataset_bundle data/datasets/featured-v1 --output data/datasets/featured-v1.zip --force
python -m scripts.import_dataset_bundle data/datasets/featured-v1.zip
```

打包器要求 `featured-default` 恰有 15 个已审核成员，且本地具备快照和分析数据；不会生成虚构的演示记录。精选成员也加入 `library-default`，供仓库页筛选、分组和用户自选比较；再次导入不会覆盖用户移除动作，也不会触碰机器学习的 300 仓库样本。`/api/v1/datasets/featured/*` 与相关 CLI 用于维护精选数据包。

## 验证与诊断

```bash
python -m compileall -q backend migrations scripts tests
python -m pytest -p no:cacheprovider tests/backend -q
python -m scripts.check_data_integrity
```

做本地集成验收前，将 `DATABASE_URL`、`RAW_DATA_DIR` 和随机 `INTERNAL_API_KEY` 配置到本地环境；API 与 Worker 必须使用相同配置。临时数据库先运行 `alembic upgrade head`，再分别启动 API 和 Worker。确认 `/healthz` 返回 200 后，带 `X-Internal-Api-Key` 请求 `/api/v1/datasets` 与 `/api/v1/system/status`。真实 GitHub 冒烟可通过 `/api/v1/github/resolve` 查询一个公开仓库，再添加到分析库并轮询任务；记录 `X-Request-ID`、任务终态和 coverage，勿将 Token、内部 Key、测试数据库或原始归档提交到仓库。

`GET /api/v1/system/status` 读取数据库、Worker 心跳、队列和 GitHub 最近一次限额缓存；它不会为了状态查询消耗 GitHub 配额。`GET /repositories/{id}` 只读取本地数据库，因此 GitHub 暂时不可用时仍能展示最近一次成功结果。

## 事件分析 API（insights-v1）

新增接口均沿用内部认证和 `{data,meta}` 响应；浏览器沿用同源会话/CSRF，不传内部 Key：

- `GET /api/v1/repositories/{id}/insights`：最新版本化运行、按指标独立质量、来源、限制。
- `GET /api/v1/repositories/{id}/insights/series?metric=commits_weekly|issues_closed_weekly|prs_merged_weekly`。
- `GET /api/v1/repositories/{id}/insights/quality`：模块分页、错误、观察与查询范围。
- `GET /api/v1/repositories/{id}/insights/export.csv`：精确统计与分桶，包含单位、版本、窗口、任务，防 CSV 公式注入。
- `POST /api/v1/comparisons/insights`：`{"repository_ids":[1,2],"depth":"deep"}`；提交仅使用共同完整周，耗时窗口不一致则不给可比值。
- `GET /api/v1/research/insights?dataset_id=...`：研究成员活动分组、分布与相关，排除非 ready 输入。

无事件返回 missing，不返回伪造零值；单模块 partial 不影响其他 ready 模块。旧 `/analysis`、`/series`、比较和导出合同不变。完整合同见运行中的 `/docs`；数据采集和窗口覆盖边界见[采集合同](../insights/02_collection_contract.md)与[窗口验收规则](../insights/06_window_acceptance.md)。

## 机器学习观测 API

独立 ML 前端从既有评估产物读取数据，避免重复训练或在请求时引入 scikit-learn：

- `GET /api/v1/models/evaluation`：返回研究数据集来源、固定切分、M1 聚类轮廓系数与簇分布、M2 Macro-F1 / 平衡准确率 / 基线对比 / 混淆矩阵。
- `GET /api/v1/models/status`：返回 M1 / M2 研究模型可用状态和生产候选模型的审批/运行状态。
- `GET /api/v1/models/monitoring`：返回当前进程的推理计数、P50 / P95 延迟和峰值内存；进程重启后会清空。

三个接口都经过内部 API Key 保护。8502 前端通过 `/api/browser` 本机会话代理调用，不把内部凭据放入浏览器；页面和 API 仍仅接受本机回环访问。
