export type MetricKey = 'commits' | 'issueHours' | 'prHours' | 'releaseDays'

export interface Repository {
  id: string
  owner: string
  name: string
  fullName: string
  description: string
  language: string
  stars: number
  forks: number
  weeklyCommits: number
  activeWeeks: number
  issueMedianHours: number
  prMedianHours: number
  releaseIntervalDays: number
  createdYear: number
  coverage: number
}

export interface MockTask {
  id: string
  repository: string
  module: string
  status: 'running' | 'queued' | 'done' | 'partial'
  stage: string
  progress: number | null
  updated: string
}

const catalog = [
  ['steady-core', 'Rust', '高性能事件处理与时间序列聚合工具。'],
  ['docs-site', 'TypeScript', '面向开发团队的文档与知识站点。'],
  ['grid-lite', 'TypeScript', '轻量级数据网格与可视化组件。'],
  ['sparse-kit', 'Python', '面向研究工作流的稀疏数据工具包。'],
  ['queue-demo', 'Go', '可观察、可恢复的分布式任务队列。'],
  ['api-surface', 'Go', '服务端 API 规范与契约检查工具。'],
  ['search-engine', 'Rust', '小型全文检索与索引引擎。'],
  ['build-kit', 'JavaScript', '面向前端项目的构建工具集合。'],
  ['graph-viz', 'TypeScript', '用于探索关系数据的图形组件。'],
  ['auth-service', 'Python', '用于示例项目的身份认证服务。'],
  ['web-runtime', 'TypeScript', '可组合的 Web 渲染运行时。'],
  ['event-store', 'Go', '面向事件流的持久化存储层。'],
  ['tiny-lab', 'Python', '小型实验与复现脚本集合。'],
  ['release-bot', 'TypeScript', '自动化发布和版本记录助手。'],
  ['query-tools', 'JavaScript', 'SQL 查询构建和迁移辅助工具。'],
  ['service-map', 'Rust', '服务依赖关系与拓扑分析。'],
] as const

const owners = ['demo-labs', 'sample-foundation', 'open-workbench', 'northstar-dev', 'acme-sandbox']

export const repositories: Repository[] = Array.from({ length: 300 }, (_, index) => {
  const [baseName, language, description] = catalog[index % catalog.length]
  const owner = owners[Math.floor(index / catalog.length) % owners.length]
  const suffix = index < catalog.length ? '' : `-${String(Math.floor(index / catalog.length) + 1).padStart(2, '0')}`
  const name = `${baseName}${suffix}`
  const stars = 120 + ((index * 1_387 + 2_941) % 64_800)
  return {
    id: String(index + 1),
    owner,
    name,
    fullName: `${owner}/${name}`,
    description,
    language,
    stars,
    forks: Math.round(stars * (0.08 + (index % 8) * 0.018)),
    weeklyCommits: 2 + ((index * 97 + 13) % 840) / 10,
    activeWeeks: (index * 5 + 3) % 13,
    issueMedianHours: 2 + ((index * 41 + 19) % 190),
    prMedianHours: 1 + ((index * 29 + 11) % 92),
    releaseIntervalDays: 4 + ((index * 17 + 7) % 145),
    createdYear: 2014 + ((index * 7 + 3) % 12),
    coverage: 100,
  }
})

export const defaultCompareIds = repositories.slice(0, 3).map((repository) => repository.id)

export const commitTrend = [
  { week: '08/18', commits: 8_190 }, { week: '08/25', commits: 8_440 }, { week: '09/01', commits: 8_105 },
  { week: '09/08', commits: 8_820 }, { week: '09/15', commits: 9_240 }, { week: '09/22', commits: 8_970 },
  { week: '09/29', commits: 9_510 }, { week: '10/06', commits: 9_380 }, { week: '10/13', commits: 9_870 },
  { week: '10/20', commits: 10_240 }, { week: '10/27', commits: 10_060 }, { week: '11/03', commits: 10_610 },
]

export const recentChanges = [
  { id: '1', repository: 'demo-labs/steady-core', metric: '周均 Commit', change: '+18.4%', direction: 'up', note: '最近 4 个完整周较前 4 周增加' },
  { id: '2', repository: 'demo-labs/docs-site', metric: 'Issue 关闭耗时', change: '−12.1%', direction: 'down', note: '处理时间缩短，基于相同 90 天窗口' },
  { id: '3', repository: 'demo-labs/grid-lite', metric: '活跃周数', change: '+2 周', direction: 'up', note: '最近 12 周的活动连续性提高' },
]

export const researchCoverage = [
  { key: 'commits', label: 'Commit 周记录', complete: 3_600, partial: 0, total: 3_600 },
  { key: 'issues', label: 'Issue 处理记录', complete: 3_600, partial: 0, total: 3_600 },
  { key: 'pulls', label: 'PR 合并记录', complete: 3_600, partial: 0, total: 3_600 },
]

export const tasks: MockTask[] = [
  { id: 'task-1', repository: 'demo-labs/queue-demo', module: 'Commit 采集', status: 'running', stage: '读取 12 周提交记录', progress: 68, updated: '刚刚' },
  { id: 'task-2', repository: 'sample-foundation/api-surface', module: 'Issue 采集', status: 'queued', stage: '等待前序任务', progress: null, updated: '1 分钟前' },
  { id: 'task-3', repository: 'open-workbench/event-store', module: '仓库分析', status: 'partial', stage: '部分记录已保存，可重试未完成模块', progress: null, updated: '12 分钟前' },
  { id: 'task-4', repository: 'northstar-dev/web-runtime', module: 'Release 采集', status: 'done', stage: '采集完成', progress: 100, updated: '昨天' },
]

export const weekLabels = ['08/18', '08/25', '09/01', '09/08', '09/15', '09/22', '09/29', '10/06', '10/13', '10/20', '10/27', '11/03']

export function repositoryById(id: string | null | undefined) {
  return repositories.find((repository) => repository.id === id) ?? repositories[0]
}

export function repositoryWeeklyActivity(repository: Repository) {
  return weekLabels.map((week, index) => ({
    week,
    commits: Math.max(0, Math.round(repository.weeklyCommits * (0.76 + ((index * 7 + Number(repository.id)) % 47) / 100))),
  }))
}

export function formatNumber(value: number) {
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 1 })
}
