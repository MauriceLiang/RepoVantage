import type {
  ActivityTrend, CollectionSettings, CommitActivityPage, ComparisonBundle, ComparisonMode, MaintenanceCollectionResult, ReleaseDetails, RepositoryAnalysis, RepositoryEvaluation, RepositorySummary,
  FeaturedDatasetImportResult, FeaturedDatasetStatus, IssueOnlineDetail, IssueRecordDetail, IssueRecordPage, PullRequestActivityDetail, PullRequestActivityPage, PullRequestOnlineDetail, ResearchAnalysisMode, ResearchDataset, RepositoryDashboardData, SelectionFeedback, SelectionRequest, SelectionResult, TaskItem, TimeWindow,
} from './types'

/**
 * 应用统一的数据访问边界。
 *
 * 页面和图表不直接引用示例数据；真实模式与显式开启的演示模式
 * 均实现此接口，调用方无需了解数据来自哪种实现。
 */
export interface RepositoryDataSource {
  getCollectionSettings(): Promise<CollectionSettings>
  saveCollectionSettings(settings: CollectionSettings): Promise<CollectionSettings>

  listRepositories(): Promise<RepositorySummary[]>
  getFeaturedDatasetStatus(): Promise<FeaturedDatasetStatus>
  importFeaturedDataset(): Promise<FeaturedDatasetImportResult>
  exportFeaturedDataset(): Promise<Blob>
  /** 返回当前本地 Commit 趋势；无法计算变化百分比时同时返回原因。 */
  getActivityTrend(id: string): Promise<ActivityTrend>
  searchRepositories(query: string): Promise<(RepositorySummary & { alreadyInLibrary: boolean })[]>
  addRepository(input: string): Promise<{ repositoryId: string; taskId: string | null; existing: boolean }>
  removeRepository(id: string): Promise<void>
  clearRepositoryData(ids: string[], options?: { removeFromLibrary?: boolean }): Promise<void>
  refreshRepository(id: string, options: { scopeKind: 'quick' | 'window'; windowDays: TimeWindow }): Promise<string>

  /**
   * 返回单个仓库的完整分析数据。
   *
   * 浏览器网关返回指标摘要和基于事件的图表数据，逐条记录需要单独请求。
   * 不可用的值保持为 null，不能通过聚合总数倒推出明细。
   */
  getAnalysis(id: string, window: TimeWindow): Promise<RepositoryAnalysis>
  getEvaluation(id: string): Promise<RepositoryEvaluation>
  collectMaintenance(id: string, lookbackWeeks?: 12 | 24): Promise<MaintenanceCollectionResult>
  getCommitActivity(id: string, page: number, perPage: number, search: string, weekStart?: string, windowDays?: TimeWindow): Promise<CommitActivityPage>
  getIssueRecords(id: string, page: number, perPage: number, search: string, windowDays?: TimeWindow): Promise<IssueRecordPage>
  getIssueDetail(id: string, issueNumber: number): Promise<IssueRecordDetail>
  getIssueOnlineDetail(id: string, issueNumber: number): Promise<IssueOnlineDetail>
  exportIssueRecords(id: string, search: string, windowDays?: TimeWindow): Promise<Blob>
  getPullRequestRecords(id: string, page: number, perPage: number, search: string, mergedFrom?: string, mergedTo?: string, windowDays?: TimeWindow): Promise<PullRequestActivityPage>
  getPullRequestDetail(id: string, pullNumber: number): Promise<PullRequestActivityDetail>
  getPullRequestOnlineDetail(id: string, pullNumber: number): Promise<PullRequestOnlineDetail>
  exportPullRequestRecords(id: string, search: string, mergedFrom?: string, mergedTo?: string, windowDays?: TimeWindow): Promise<Blob>
  getReleaseDetails(repositoryId: string, releaseId: string): Promise<ReleaseDetails>

  /** 对比 2 至 5 个仓库，可选共同时间区间或各仓库自己的完整区间。 */
  getComparison(ids: string[], window: TimeWindow, mode: ComparisonMode): Promise<ComparisonBundle>
  getSelection(input: SelectionRequest): Promise<SelectionResult>
  listSelectionFeedback(): Promise<SelectionFeedback[]>
  saveSelectionFeedback(input: SelectionRequest, signature: string, repositoryId: string, choiceKind: SelectionFeedback['choiceKind'], reason: string): Promise<SelectionFeedback>
  deleteSelectionFeedback(id: string): Promise<void>

  getResearchDataset(id?: string, mode?: ResearchAnalysisMode | 'auto'): Promise<ResearchDataset>
  getOverviewDashboard(): Promise<RepositoryDashboardData>

  listTasks(): Promise<TaskItem[]>
  retryTask(id: string): Promise<string>
  exportInsights(id: string, windowDays: TimeWindow): Promise<Blob>
  exportComparison(ids: string[], windowDays: TimeWindow, mode: ComparisonMode): Promise<Blob>
  exportRepositories(scope: 'library' | 'research', datasetId?: string, mode?: ResearchAnalysisMode): Promise<Blob>
  exportResearchStatistics(datasetId: string, mode: ResearchAnalysisMode): Promise<Blob>
}
