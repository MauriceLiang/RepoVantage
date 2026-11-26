# RepoVantage

基于 GitHub 公开数据的仓库分析与技术选型工作台。支持仓库采集、活动趋势、Issue / PR / Release 分析、多仓库比较，以及固定课程数据上的机器学习评估。

**技术栈：** Vue 3 + TypeScript + Vite + AntV G2 · FastAPI + Python 3.12 · SQLite + Alembic · 独立采集 Worker。

## 快速启动

前置依赖：**Python 3.12、[uv](https://docs.astral.sh/uv/)、Node.js / npm**。在仓库根目录运行：

```bash
uv run --locked --all-extras python -m scripts.start
```

首次启动会准备依赖、构建两套前端、创建本机 `.env` / `INTERNAL_API_KEY`、升级数据库，并启动 API、Worker 和页面。按 `Ctrl+C` 停止整套服务。

| 地址 | 用途 |
| --- | --- |
| http://127.0.0.1:8501 | 普通用户工作台 |
| http://127.0.0.1:8502 | 机器学习观测台 |
| http://127.0.0.1:8501/docs | FastAPI 接口文档 |
| http://127.0.0.1:8501/healthz | 健康检查 |

GitHub Token 是可选配置；未设置时受匿名请求额度限制。可通过工作台设置页添加 Token。内部 API Key 保留在本机，不进入浏览器资源；本机数据库和动态采集文件均被 Git 忽略。

## 功能

- **仓库管理：** 搜索、添加、分组、更新和移除 GitHub 仓库。
- **比较仓库清单：** 仓库页可一键导入 60 个公开项目，按相近用途建立 12 个分组，并按清单顺序排队采集。新安装默认保持“我的仓库”为空；只有用户主动导入后才加入清单项目。
- **仓库分析：** 观察 Commit、Issue、PR、Release 和维护活动，按 30 / 90 / 180 天窗口查看数据。
- **项目比较：** 比较 2–5 个仓库，支持同期 / 独立窗口、权重调整、排名与导出。
- **任务管理：** 查看采集进度、重试和数据覆盖状态。
- **机器学习观测：** 对固定研究样本展示训练、评估和模型诊断，不等同于生产预测服务。

**数据约束：** 不把未知、未采集、部分覆盖或失败状态当成真实零值。同期比较应遵守共同观察窗口规则。模型研究结论不得直接代替仓库质量判断。

## 代码结构

```text
backend/app/       FastAPI、业务服务、GitHub 集成、数据处理和 Worker
frontend/src/      普通用户前端、组件、图表、API 数据源
frontend/ml-console/ 独立的机器学习观测前端
data/datasets/     冻结的课程数据包及来源说明
data/manifests/    数据和选型快照元信息
ml/course/         课程模型、固定分组和评估结果
ml-production/     模型准入协议、注册表与验证证据
migrations/        Alembic 数据库迁移
scripts/           启动、采集、训练、评估、导入和校验命令
tests/             后端行为、API 契约及固定测试样例
reports/           机器可读的评估与验收结果
```

项目保持单仓库、单后端、两套前端，不引入额外的 workspace 或微服务分层。前端开发和路由见 [frontend/README.md](frontend/README.md)，模型准入见 [ml-production/README.md](ml-production/README.md)。

## 本地开发与验证

```bash
# 后端测试
uv run --locked --all-extras pytest

# 普通用户前端
cd frontend
npm ci
VITE_DATA_MODE=mock npm run dev  # 显式 Mock 演示
# VITE_DATA_MODE=http npm run dev  # 连接运行中的后端
npm run typecheck
npm run build
npm run build:ml
npm run test:selection-weight-math
npm run test:overview-charts
```

浏览器端到端测试使用 `frontend/scripts/` 下的脚本，通常需要先启动页面和无头浏览器；CI 配置见 `.github/workflows/`。修改 API、数据源或页面功能时，需同时更新相应测试；不要仅以能成功构建作为验收标准。

## 数据与机器学习边界

- `data/manifests/comparison-repositories-v1.json` 是仓库页的演示导入清单，分组说明见 [docs/仓库采集清单.md](docs/仓库采集清单.md)。新克隆后“我的仓库”默认为空；需要演示时，点击仓库页上方的“导入比较仓库”才会将清单加入。
- M1、M2 使用的 300 仓库、52 周聚合训练输入保存在 `ml/course/datasets/repo-evaluation-2026-v1/`，按固定 **150 训练 / 150 留出** 切分；模型、切分与评估结果保存在 `ml/course/`。该训练数据不导入个人仓库列表。
- M1 使用 K-Means 描述维护活动模式；M2 使用逻辑回归评估活动趋势。评估属于既定历史样本上的课程研究，不能外推到所有 GitHub 仓库。
- `ml-production/approved/` 当前没有批准的生产模型。模型注册和研究材料不构成生产准入。
- `data/app.db`、`data/collected/`、`data/raw/`、`.env` 属于本机运行状态，不应提交到仓库；冻结数据包与模型可复现材料应保留版本记录。

修改模型、数据切分或指标口径前，应先核对固定清单和评估结果，不要将研究产物当作可随意清理的构建缓存。
