# GitHubDA V5：Mock 数据与交互状态机

> 阶段 I 必须不调用真实 API。Mock 是为了让所有页面**真的能操作**，不是插入几条硬编码列表假装页面完成。

## 1. 设计目标

Mock Provider 和未来的 HTTP Provider 对 Vue 页面暴露相同接口。推荐接口函数返回 `Promise<Result>`，模拟延迟可配置，但不长期冻结 UI。Mock 数据与前端本地交互状态分层管理。

### 建议服务接口（TypeScript 形状示意）

```ts
export type TaskStatus = 'queued'|'running'|'succeeded'|'partial'|'failed'|'cancelled'
export type Coverage = 'complete'|'partial'|'not_collected'|'unknown'
export type Depth = 'basic'|'deep'

export interface Repository {
  repositoryId: number
  fullName: string
  description: string | null
  language: string | null
  stars: number | null
  forks: number | null
  analysisStatus: 'not_started'|'queued'|'processing'|'completed'|'partial'|'failed'
  dataStatus: 'missing'|'fresh'|'stale'
  lastCollectedAt: string | null
}
export interface Task {
  taskId: string
  repositoryId: number
  depth: Depth
  status: TaskStatus
  progressPercent: number | null
  progressKind: 'stages' | 'unknown'
  phase: string | null
  etaSeconds: number | null
  modules: Array<{name:string;status:string;coverage:Coverage}>
}
export interface RepositoryService {
  resolve(input: string): Promise<Repository>
  search(params: {q:string;language?:string;page?:number}): Promise<Repository[]>
  listLibrary(params: {q?:string;status?:string;sort?:string;page?:number}): Promise<Repository[]>
  addAndStart(input: string, depth?: Depth): Promise<{repositoryId:number;taskId:string|null}>
  getDetail(repositoryId: number): Promise<Repository>
  refresh(repositoryId: number, depth: Depth): Promise<Task>
  remove(repositoryId: number): Promise<void>
  compare(ids: number[], depth: Depth): Promise<unknown>
  exportLibrary(): Promise<Blob>
}
export interface TaskService {
  list(status?: TaskStatus): Promise<Task[]>
  get(taskId: string): Promise<Task>
  retry(taskId: string): Promise<Task>
}
export interface ResearchService {
  datasets(): Promise<unknown[]>
  statistics(input: {datasetId:string;groupBy:string;language?:string}): Promise<unknown>
  quality(datasetId: string): Promise<unknown>
  exportDataset(datasetId: string): Promise<Blob>
}
```

上述是**Vue 的建议 domain model**；正式对接时将 FastAPI `repository_id/full_name` snake_case DTO 映射为 camelCase；允许保持 snake_case，但必须统一，不能在页面混用。

## 2. 固定种子数据与场景

基础 Mock 至少含：

- 6–10 个语言、Star 数和仓库年龄不同的公开仓库样例；仓库显示名称可以是常见开源项目，但 Mock 数值必须明确标记演示，不冒充实时 GitHub 数据。
- 个人库：至少 4 个仓库，覆盖 `completed`、`partial`、`queued/running`、`not_started`/`missing`；允许一键清空。
- 任务：基础采集、深度采集、历史成功、历史失败、部分完成、排队中的任务。
- 研究：固定且有有效样本的数据集、未冻结数据集、空数据集；提供分布/相关性/质量所需字段。
- 历史趋势：两个以上观察点的仓库、零个点的仓库、仅一个点的仓库；不能给后两类画增长趋势。
- 错误：仓库不存在/非法 URL、GitHub 限流、Worker 不可用、API 错误、重试冲突。

**种子可重复**：最好使用静态 JSON 和统一时钟基准（比如以固定 ISO 日期为生成输入），避免每次测试随机变动导致截图不稳定。真实演示动效可以模拟时间推进，但每次重置必须得到相同初始状态。

## 3. 模拟任务状态机

```text
用户发起开始分析
    |
    v
   queued ----(下一时刻)----> running ----(完成)----> succeeded
      |                          |                      |
      |                          +---> partial         +--> 可查看结果
      |                          +---> failed
      |                          +---> cancelled（若 Mock 支持显式取消）
      +----> failed（模拟环境错误）

failed/partial --[用户主动重试]--> 新 taskId，重新 queued
```

- `queued` 时 `attempt=0`，进度可以未知，不能显示假百分比。
- `running` 时如果给出 `progress_kind=stages`，UI 明确标注“阶段进度”；`progress_percent` 不可推算 coverage。
- `partial` 时某些模块可能成功、一些失败；展示可用结果并说明局限。
- `failed` 时仍保留上次成功结果；不自动重复发送用户操作。
- 同一个仓库已存在 `queued/running` 时，再点击开始/刷新应复用或阻止重复任务，附反馈。
- Mock 时间推进使用单一 store/service 定时管理或模拟时钟；组件卸载不得保留孤儿 interval。
- taskId 全局唯一（Mock 可用可靠序列/UUID）；旧任务在列表中可追溯。

## 4. 持久化与重置

- `localStorage` 只存 Mock 交互状态：个人库、任务、已选仓库、主题、密度、schemaVersion。不要在里面存任何真实密钥。
- `Mock.reset()` 原子恢复默认种子、清理无效选中和过滤、返回默认总览或当前有效页，通知用户“演示数据已重置”。
- Vue 页面统一调用服务接口，不可直接访问种子 JSON 或 `localStorage`。
- Mock 演示模式顶部使用一个轻量“演示数据”提示即可，禁止每张图、每个模块重复告警。

## 5. 必做的交互矩阵

| 场景 | 操作 | 期望 |
|---|---|---|
| 新仓库 | 输入 `owner/repo` 或 GitHub URL | 加入个人库，入队并打开详情 |
| 已存在仓库 | 重复输入同一地址 | 打开原详情，不重复建成员/任务 |
| URL 错误 | 输入非法地址 | 保留输入，显示字段错误 |
| 搜索 | 输入关键词、切换语言、排序 | 结果与控件一致；不互相覆盖 |
| 选择 | 列表勾选 2–5 个，跨筛选返回 | 保留选择且不超过上限 |
| 对比 | 删掉一个已选仓库 | 立即刷新结果；不足两个禁止生成图表 |
| 导出 | 点击导出仓库/研究 CSV | 浏览器实际下载，无空操作 |
| 深度采集 | 详情里启动深度分析 | 同一任务在任务页与详情可见 |
| 错误与重试 | failed → retry | 新任务入队；历史失败保留 |
| 空库 | 清空个人库 | 入口明确、没有大面积无意义容器 |
| 少样本 | 数据集或仓库只有 n=1 | 不画假的分布/历史趋势 |
| 深浅色 | 切换主题 | UI 与图表同时变化，刷新持久化 |
| 小屏 | 打开侧边抽屉、切换页面 | 抽屉关闭，焦点恢复，页面不横向溢出 |
| 快捷键 | ⌘/Ctrl+K，Escape，键盘箭头 | 搜索框打开、关闭、聚焦正确 |

## 6. 需要特别注意的真实数据原则

- `null` 不等于 `0`，不能靠 `value || 0` 处理指标。
- 默认 Mock 图表允许有**明确标注的示例值**，不允许用拟合生成没有说明的“历史事实”。
- 非同类项目比较不作无依据的综合排序；同名 `Stars` 指标也需要合理时间口径。
- 研究样本与个人库隔离、样本版本可查看、已冻结状态真实/Mock 明示。
- 错误消息不能暴露本地 Token、内部网络路径、SQL 或调试 Traceback。
