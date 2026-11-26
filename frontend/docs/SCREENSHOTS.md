# 页面截图与演示说明

截图由 `npm run capture`（Puppeteer + 本机 Chrome）生成，输出到：

```
docs/screenshots/light/   # 浅色主题
docs/screenshots/dark/    # 深色主题
```

| 文件 | 页面 | 演示要点 |
|---|---|---|
| `overview.png` | 总览 | 仓库输入与校验、最近分析、数据变化、进行中的任务 |
| `repositories.png` | 仓库管理 | 搜索/状态筛选、多选比较条、行内操作 |
| `repo-overview.png` | 仓库概览 | KPI、主图 hover/点击、Issue/PR/发布摘要、数据观察 |
| `repo-activity.png` | 开发活动 | 按日/按周切换、GitHub 贡献日历、作者贡献 |
| `repo-issues.png` | Issue 分析 | 双序列、耗时分布与分位数、未关闭年龄、明细表 |
| `repo-prs.png` | PR 分析 | 新建/合并、合并耗时、长期滞留 PR、未采集指标 |
| `repo-releases.png` | 版本发布 | 真实日期时间轴、相邻间隔、发布记录 |
| `compare.png` | 项目比较 | 多仓库趋势、效率对比（含缺失）、对照表 |
| `research.png` | 研究分析 | 样本说明、语言分组、四分位区间、散点与 ρ/n/p、数据质量 |
| `tasks.png` | 任务中心 | 六种状态、阶段进度、重试/取消 |
| `drawer.png` | 数据与口径抽屉 | 指标定义、窗口、样本、来源、限制 |

## 手动走查建议（5 分钟）

1. 总览输入 `demo-labs/steady-core` → 进入概览。
2. 主图 hover 查看 tooltip；点击柱子 → Commit 明细抽屉；Esc 关闭。
3. 切换 `按日`，再切换窗口 `30 天`，观察图表与 KPI 同步变化。
4. 打开 `数据与口径`；再进入 Issue 页点击表格行查看 Issue 抽屉。
5. 返回仓库列表勾选 2 个仓库 → 进入比较；移除一个仓库观察图表更新。
6. 顶栏切换深色主题，确认图表与列表配色同步。
7. 打开任务页，观察进度推进与「重试/取消」。
