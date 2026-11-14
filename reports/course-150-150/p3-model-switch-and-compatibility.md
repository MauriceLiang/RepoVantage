# v4.4 P3：课程模型切换与兼容检查

日期：2026-11-11。通过训练评估的 M1/M2 候选接入课程设计推理路径；旧模型文件和回退副本保留。部署范围是课程演示和历史样本分析，不宣称生产级或外部验证。

## 当前推理模型

| 任务 | 运行产物 | 模型版本 | SHA-256 |
|---|---|---|---|
| M1 维护模式 | `ml/course/artifacts/ml03-maintenance-pattern-12w-150train-v1.json` | `ml03-12w-150train-v1` | `02fa46887dd340e78db4f1263711d69902c7ad98387209840ca45ef9eac8a651` |
| M2 未来 4 周趋势 | `ml/course/artifacts/ml01-activity-trend-12w-150train-v1.json` | `ml01-trend-12w-150train-v1` | `4289ce1896385d5c24d5423b849eddaf03f8677b27db4dae13044307c311957a` |

两者使用 `course-maintenance-12w-v1`。`backend/app/services/course_ml.py` 校验状态、特征 schema 和系数/聚类中心；不完整周不补成零。M1 只用最近 12 个完整 UTC 周；M2 只返回类别，不显示未经校准概率或精确 Commit 数。

M2 对最近 4 周提交少于 3 次或 12 周活跃周少于 3 周的仓库返回 `low_activity_scope`，只保留历史事实。观察不足 12 个完整周时，相关模型返回数据不足/短窗口状态。

## 回退与旧产物

| 旧模型 | 当前旧文件 SHA-256 | 回退副本 SHA-256 | 状态 |
|---|---|---|---|
| `ml03-maintenance-pattern-12w.json` | `5cddec2e2e4d935896357c376bcf5018576a226aa0a27d1b7c9c059af890e0ae` | `5cddec2e2e4d935896357c376bcf5018576a226aa0a27d1b7c9c059af890e0ae` | 保留，未覆盖 |
| `ml01-activity-trend-12w.json` | `18a9fb8700de49b1ac27fea995f433ebcba53b71df5d9f915b402535667a918a` | `18a9fb8700de49b1ac27fea995f433ebcba53b71df5d9f915b402535667a918a` | 保留，未覆盖 |

当前模型通过独立版本名加载；出问题时可在 `course_ml.py` 将 M1/M2 文件名恢复为旧文件，无需改写数据库历史周数据。M3 始终使用 MAD 规则，本轮未替换。

## 页面和报告口径

- 仓库详情显示 `train` / `test` 角色、样本版本、快照截至时间和活动窗口；角色仅用于标明历史回测分组。
- 项目比较使用最近的完整周级维护汇总；比在线事件分析时间较新的维护汇总优先，较新的在线事件分析仍优先于课程快照。
- 比较表和规则报告携带样本角色与来源。ML 结果仅作为维护行为证据，不计入规则得分。
- Issue、PR 合并耗时和 Release 在课程包中缺失时保持缺失，不补零、不从 PR 周计数推导耗时。

## 兼容证据

全量后端测试、课程导入/报告相关测试、前端生产构建通过。实际本机数据库导入后，TestClient 验证了课程成员、课程分析、仓库分析、同期比较、Markdown 规则报告和 CSV 导出；详细数据见 P4/P5。旧 API 调用方式及非课程仓库路径仍由现有测试覆盖。
