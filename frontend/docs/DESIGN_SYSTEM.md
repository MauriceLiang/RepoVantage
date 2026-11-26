# RepoVantage 设计系统

## 1. 设计原则

- **产品气质**：成熟的数据分析工具，不是后台模板，也不是营销页。
- **界面黑白、数据多彩**：导航、按钮、链接、图标、徽章一律黑白灰；颜色只用于数据编码（以及琥珀/玫红两种语义提示）。
- **证据优先**：每个图表都能回答「在问什么 / 数据从哪来 / 窗口与样本 / 是否完整」。
- **缺失不等于零**：未采集、采集为零、缺失值、部分采集使用不同表达。

## 2. 色彩令牌

所有颜色定义在 `src/styles/theme.css`，浅色为 `:root`，深色为 `.dark`。

| 令牌 | 浅色 | 用途 |
|---|---|---|
| `--gd-bg` | `#FAFAFA` | 页面底色 |
| `--gd-panel` | `#FFFFFF` | 卡片 / 抽屉 / 浮层 |
| `--gd-ink` | `#0A0A0A` | 主文字、主按钮背景 |
| `--gd-muted` | `#737373` | 次级文字、坐标轴标签 |
| `--gd-border` | `#E5E5E5` | 分割线、卡片描边 |
| `--gd-soft` | `#F2F2F3` | 选中态、浅底徽章 |
| `--gd-track` | `#F4F4F5` | 轨道、骨架、分段控件底 |
| `--gd-s1…s5` | `#E2683C / #E5A03A / #CE3F7C / #2E8FCB / #3B5BDB` | 图表序列色 |
| `--gd-heat-0…4` | GitHub 贡献图绿色阶 | 提交日历热力 |
| `--gd-warn-bg/fg` | `#FAF2E3 / #8A5A12` | 部分数据、演示数据、失败 |

深色模式的序列色使用高明度变体，保证深底上的对比；热力图使用 GitHub 深色色阶。

### 使用规则

- 同一图表内不允许两个序列同色；单序列统一 `--gd-s1`（或该页面的主色）。
- 颜色不是唯一编码：图例文字、数值标签、线型/点标记必须同时可辨。
- 不使用红绿表达「好/坏」；语义色只用于「部分采集 / 失败 / 演示数据」。

## 3. 字体与排版

- 正文/标题：`Noto Sans SC`（回退 PingFang SC / Microsoft YaHei）。
- 数字、日期、SHA、代码：`JetBrains Mono`，启用 `tabular-nums`。
- 页面标题 24–26px / 600；卡片标题 15.5px / 600；正文 13px；说明 11–12px，颜色 `--gd-muted`。
- 行高：正文 1.55–1.65；标题 1.3。

## 4. 间距与圆角

- 间距基准 4px：8 / 12 / 16 / 18 / 24。
- 卡片圆角 10px；按钮 7px；输入框 8px；徽章 4px。
- 页面内容左右留白 28px（窄屏 16px），模块间距 18px。

## 5. 组件规范

| 组件 | 文件 | 说明 |
|---|---|---|
| Button | `ui/GdButton.vue` | primary（黑底）/ outline / ghost，高度 34 / 28 |
| IconButton | `ui/GdIconButton.vue` | 30×30，hover 浅灰底 |
| Card | `ui/GdCard.vue` | 白底 + 1px 描边 + 10px 圆角 + 18px 内边距 |
| Badge | `ui/GdBadge.vue` | default / warn / plain / danger |
| Input | `ui/GdInput.vue` | 44 / 38 高，错误态红色描边 + 光环 |
| Segmented | `ui/GdSegmented.vue` | 时间窗口、粒度切换 |
| Drawer | `ui/GdDrawer.vue` | 右侧 460px，遮罩 + 滑入，Esc/遮罩关闭 |
| Toast | `ui/GdToastHost.vue` | 底部居中，2.6s 自动消失 |
| CoverageNote | `ui/GdCoverageNote.vue` | 覆盖状态点 + 文案（部分数据用琥珀色） |

## 6. 图表主题

正式图表统一使用 AntV G2 5，通过 `src/components/charts/G2Chart.vue` 管理实例生命周期和深浅主题。业务组件以 G2 mark/encode/scale 配置图表；没有旧 option 转换层。

- 坐标、网格与 Tooltip 采用当前主题色和简洁标签；卡片小图控制标签密度。
- 序列颜色在图例、名称或标记中同时说明，颜色不单独承载状态。
- 数据量、耗时等不同单位分图展示，不共用纵轴。
- 真实零、部分观察、缺失与失败按原始数据区分；不把 `null` 画成零。
- G2 图表销毁时释放实例；日期筛选、容器变化和主题切换均更新当前实例。
- `CalendarHeatmap.vue` 使用原生 Vue/CSS 网格，保留 UTC 日期格和 partial/missing 区分。
