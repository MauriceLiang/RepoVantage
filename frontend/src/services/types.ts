/**
 * RepoVantage 前端数据模型。
 *
 * 类型按界面需要定义；后端 API 响应由 httpRepositoryDataSource.ts 转换。
 * 后端未提供的数值保持为 null，不能当作零或自行推算。
 */

export type TimeWindow = 30 | 90 | 180

export type RepositoryStatus = 'ready' | 'partial' | 'running' | 'idle' | 'failed'

/** 覆盖情况：未知数据不能显示为零，界面通过覆盖说明提示原因。 */
export interface Coverage {
  state: 'complete' | 'partial' | 'missing'
  label: string
  detail?: string
}

export interface TimePoint {
  /** UTC 时间分桶的起点，采用 ISO 日期格式。 */
  date: string
  value: number | null
  /** 覆盖不完整而隐藏正式数值时，仍可展示该分桶已观察到的数量。 */
  observedValue?: number | null
  /** 后端分析时间点可能附带自然周质量和完整性信息。 */
  quality?: string
  completeWeek?: boolean
}

export interface WindowAvailability {
  requestedDays: TimeWindow
  available: boolean
  availableDays: number | null
  reason: string | null
}

export interface NamedSeries {
  key: string
  label: string
  points: TimePoint[]
}

export interface TimeSeriesResult {
  series: NamedSeries[]
  unit: string
  window: { start: string | null; end: string | null; startUtc?: string | null; endUtc?: string | null }
  /** 来源指标报告的有效样本数，与图表分桶数量无关。 */
  sampleSize: number | null
  coverage: Coverage
  collectedAt: string | null
  /** 展示给用户的限制说明，例如“当周尚未完整”。 */
  limitation?: string
}

export interface Metric {
  id: string
  label: string
  /** null 表示指标不可用，界面显示“—”并结合说明解释原因。 */
  value: number | null
  unit: string
  note: string
  sampleSize?: number
}

export interface MetricSet {
  metrics: Metric[]
  window: { start: string | null; end: string | null }
  collectedAt: string | null
  coverage: Coverage
}

export interface HistogramBucket {
  label: string
  count: number
}

export interface HistogramResult {
  unit: string
  buckets: HistogramBucket[]
  percentiles: { p50: number | null; p75: number | null; p90: number | null }
  sampleSize: number
  coverage: Coverage
  note?: string
}

export interface ActivityTrend {
  changePercent: number | null
  recentCommits: number | null
  previousCommits: number | null
  qualityStatus: string
  comparisonReason: string | null
}

export interface RepositorySummary {
  /** 路由使用的后端仓库编号。 */
  id: string
  fullName: string
  description: string | null
  language: string | null
  stars: number | null
  /** 仓库资料取自最近一次 GitHub 快照。 */
  forks?: number | null
  license: string | null
  topics: string[]
  createdAt?: string | null
  pushedAt?: string | null
  archived?: boolean | null
  sizeKb?: number | null
  /** GitHub 的 open_issues_count 同时包含开放 Issue 和 PR。 */
  openIssuesAndPrCount?: number | null
  status: RepositoryStatus
  lastAnalyzedAt: string | null
  /** 最近 4 个完整周相对前 4 周的变化百分比；不可比较时为 null。 */
  activityDelta: number | null
  htmlUrl?: string
  alreadyInLibrary?: boolean
}

export interface CommitEvent {
  sha: string
  title: string
  author: string
  isBot: boolean
  anonymous?: boolean
  date: string
  url?: string
}

export interface CommitActivityPage {
  items: CommitEvent[]
  page: number
  perPage: number
  total: number
  available: boolean
  coverage: Coverage
  note: string
  windowStart: string | null
  windowEnd: string | null
  commitCount: number
  authorCount: number
  dailyCounts: { date: string; count: number }[]
  authors: AuthorContribution[]
  authorDistribution: { commits: number; authors: number }[] | null
  unidentifiedCommitCount: number | null
}

export interface IssueRecord {
  number: number
  title: string
  createdAt: string | null
  closedAt: string
  durationDays: number | null
  state: 'closed'
  url?: string
}

export interface IssueRecordDetail extends IssueRecord {
  body: string | null
  commentsCount: number
}

export interface IssueComment {
  author: string
  body: string
  createdAt: string | null
}

export interface IssueOnlineDetail {
  number: number
  title: string
  createdAt: string | null
  closedAt: string | null
  url?: string
  body: string | null
  state: 'open' | 'closed'
  author: string | null
  labels: string[]
  updatedAt: string | null
  source: 'github' | 'mock'
  commentsCount: number
  comments: IssueComment[]
  commentsComplete: boolean
  commentsError: string | null
}

export interface IssueRecordPage {
  items: IssueRecord[]
  page: number
  perPage: number
  total: number
  available: boolean
  coverage: Coverage
  note: string
  windowStart: string | null
  windowEnd: string | null
}

export interface PullRequestActivityRecord {
  number: number
  title: string
  createdAt: string | null
  closedAt: string | null
  mergedAt: string | null
  durationDays: number | null
  state: 'closed' | 'merged'
  draft: boolean
  commentsCount: number
  url?: string
}

export interface PullRequestActivityDetail extends PullRequestActivityRecord {
  body: string | null
}

export interface PullRequestOnlineDetail {
  number: number
  title: string
  body: string | null
  state: 'open' | 'closed' | 'merged'
  author: string | null
  labels: string[]
  createdAt: string | null
  closedAt: string | null
  mergedAt: string | null
  updatedAt: string | null
  url?: string
  source: 'github' | 'mock'
  commentsCount: number
  comments: IssueComment[]
  commentsComplete: boolean
  commentsError: string | null
}

export interface PullRequestActivityPage {
  items: PullRequestActivityRecord[]
  page: number
  perPage: number
  total: number
  available: boolean
  coverage: Coverage
  note: string
  windowStart: string | null
  windowEnd: string | null
}

export interface ReleaseRecord {
  tag: string
  identifierType?: 'tag' | 'release_id'
  publishedAt: string
  prerelease: boolean
  intervalDays: number | null
  note: string
  url?: string
}

export interface ReleaseDetails {
  name: string | null
  body: string | null
}

export interface AuthorContribution {
  author: string
  commits: number
  isBot: boolean
  anonymous?: boolean
}

export interface Observation {
  id: string
  text: string
  evidence: string
}

export interface PrDurationPeriod {
  /** UTC 左闭右开时间区间。 */
  start: string
  end: string
  counts: number[]
  medianHours: number | null
  validSamples: number
  complete: boolean
}

export interface RepositoryChartData {
  /** 所选窗口内按提交量排序的前五个可识别 GitHub 账号标识。 */
  commitAccounts: string[]
  /** 按周观察到的数量；complete=false 时不能视为完整一周的总量。 */
  commitWeekly: { start: string; complete: boolean; observedCommits: number; activeAuthors: number | null; contributors: number[]; otherCommits: number; unidentifiedCommits: number }[]
  issueOpenedWeekly: TimePoint[]
  issueClosedWeekly: TimePoint[]
  prMergedWeekly: TimePoint[]
  prMonthly: (PrDurationPeriod & { month: string })[]
  prWeekly: PrDurationPeriod[]
  prBiweekly: PrDurationPeriod[]
  /** 散点可能经过抽样；周、双周和月聚合仍使用全部有效 PR。 */
  prSamples: { id: string; mergedAt: string; durationHours: number }[]
  prSampleTotal: number
  prSamplesTruncated: boolean
  /** Commit 数对应 [上次发布, 本次发布)；null 表示无法证明区间覆盖完整。 */
  releaseIntervals: { id: string; previousPublishedAt: string; publishedAt: string; commitCount: number | null; reason: string | null }[]
}

export interface RepositoryAnalysis {
  /** 覆盖证明和当前事件库计算各有独立来源，不能混为同一次采集。 */
  provenance?: {
    calculationBasis: string
    calculatedAt: string | null
    coverageRunId: string | null
    coverageAnalyzedAt: string | null
    coverageSourceTaskIds: string[]
    coverageArchivePaths: string[]
    eventSourceTaskIds: string[]
  }
  repository: RepositorySummary
  chartData: RepositoryChartData | null
  metrics: MetricSet
  /** 主图使用的每周 Commit 序列。 */
  commits: TimeSeriesResult
  issues: TimeSeriesResult
  issueDuration: HistogramResult
  pullRequests: TimeSeriesResult
  prDuration: HistogramResult
  releases: ReleaseRecord[]
  releaseIntervals: { tag: string; days: number }[]
  coverage: Coverage
  collectedAt: string | null
  observations: Observation[]
  windowAvailability: WindowAvailability
}

export type ComparisonMode = 'same_period' | 'individual_periods'
export type ResearchAnalysisMode = 'formal' | 'exploratory'

export interface ComparisonBasis {
  scope: 'shared_observation' | 'repository_windows'
  requestedWindowDays: TimeWindow
  sharedWindow: { start: string; end: string } | null
  effectiveDays: number | null
  minimumCoverageRatio: number | null
  minimumEffectiveDays: number | null
  status: 'comparable' | 'not_comparable' | 'separate_windows'
  reasonCode: string | null
  reason: string | null
}

export interface ComparisonEntry {
  id: string
  label: string
  color: string
  points: TimePoint[]
  coverage: Coverage
  collectedAt: string
  windowStart: string | null
  windowEnd: string | null
  windowAvailable: boolean
  windowReason: string | null
  issueP50: number | null
  issueSample: number
  issueQuality: string
  issueReasonCode: string | null
  prP50: number | null
  prSample: number
  prQuality: string
  prReasonCode: string | null
  releaseMedianDays: number | null
}

export interface ComparisonBundle {
  requestedWindowDays: TimeWindow
  window: { start: string; end: string }
  mode: ComparisonMode
  comparisonBasis: ComparisonBasis
  entries: ComparisonEntry[]
  notes: string[]
}

export interface ResearchGroup {
  label: string
  count: number
  /** 分组中具有有效 Issue 关闭耗时中位数的仓库数。 */
  issueSampleSize: number
  medianCloseDays: number | null
  p25: number | null
  p75: number | null
}

export interface ResearchScatterPoint {
  repository: string
  issueCloseDays: number
  prMergeDays: number
  issueSample: number
  prSample: number
  group: string
}

export interface ResearchDataset {
  id: string
  name: string
  analysisMode: ResearchAnalysisMode
  populationScope: string
  isProbabilitySample: boolean
  datasetVersion: string | null
  studyStatus: 'pending_confirmation' | 'approved_not_imported' | 'awaiting_collection' | 'analyzable'
  exploratory: boolean
  samplingSource: string
  samplingRule: string
  frozenAt: string | null
  eventWindow: { start: string | null; end: string | null }
  repositoryCount: number
  eventCount: number | null
  missingRate: number | null
  issueMedianDays: number | null
  issueSample: number
  prMedianDays: number | null
  prSample: number
  groups: ResearchGroup[]
  scatter: {
    points: ResearchScatterPoint[]
    spearman: number | null
    sampleSize: number
    pValue: number | null
    note: string
  }
  quality: { field: string; missingRate: number | null; missingCount: number | null; totalRecords: number | null }[]
  metricQuality: { field: string; validSamples: number; missingCount: number; missingRate: number | null; reasons: string[] }[]
  limitations: string[]
}

export type TaskStatus = 'queued' | 'running' | 'analyzing' | 'done' | 'partial' | 'failed' | 'cancelled'

export interface TaskItem {
  id: string
  repository: string
  taskType?: 'repository_collection' | 'dataset_import'
  targetType?: 'repository' | 'dataset'
  targetId?: string
  operation?: string
  repositoryId?: number
  module: string
  status: TaskStatus
  stage: string
  phase?: string | null
  progressPercent?: number | null
  progressKind?: 'stages' | 'records' | 'indeterminate' | 'unknown'
  scopeKind?: 'quick' | 'window' | 'incremental' | 'backfill' | null
  windowDays?: number | null
  windowStart?: string | null
  windowEnd?: string | null
  resumeAfter?: string | null
  modules?: {
    name: string
    status: string
    coverage: string
    pagesFetched: number
    pageCap: number | null
    observedItems: number
    errorCode?: string | null
  }[]
  processed?: number
  total?: number
  processedRecords?: number | null
  totalRecords?: number | null
  currentFile?: string | null
  version?: string | null
  result?: Record<string, unknown> | null
  retryOf?: string | null
  isDemo?: boolean
  updatedAt: string
  error?: string
}

export type DatasetImportTaskStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export interface FeaturedDatasetTaskSummary {
  taskId: string
  status: DatasetImportTaskStatus
  phase: string | null
  progressPercent: number | null
  progressKind: 'records' | 'indeterminate' | 'unknown'
  processedRecords: number
  totalRecords: number | null
  currentFile: string | null
  message: string | null
  errorCode: string | null
  errorMessage: string | null
  createdAt: string | null
  updatedAt: string | null
  finishedAt: string | null
  result: Record<string, unknown> | null
  retryOf: string | null
  version: string | null
  bundleHash: string | null
}

export interface FeaturedDatasetStatus {
  available: boolean
  datasetId: string
  version: string | null
  totalRepositories: number
  importedRepositories: number
  dataAsOf: string | null
  bundleHash: string | null
  reason: string | null
  alreadyCurrent: boolean
  importedVersion: string | null
  importedBundleHash: string | null
  importedAt: string | null
  verificationStatus: 'unknown' | 'pending' | 'verified'
  activeTask: FeaturedDatasetTaskSummary | null
  latestTask: FeaturedDatasetTaskSummary | null
  isDemo?: boolean
}

export interface FeaturedDatasetImportResult {
  taskId: string | null
  datasetId: string
  version: string
  bundleHash: string
  status: DatasetImportTaskStatus
  alreadyCurrent: boolean
}

export interface CollectionSettings {
  githubMaxPages: number
}

export interface DefinitionEntry {
  metricId: string
  title: string
  definition: string
  source: string
  limitation: string
}
