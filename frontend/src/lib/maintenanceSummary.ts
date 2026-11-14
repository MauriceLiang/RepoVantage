import type { RepositoryEvaluation } from '@/services/types'

export interface MaintenanceSummaryView {
  status: 'available' | 'partial' | 'waiting' | 'limited' | 'error'
  headline: string
  activityLine: string
  anomalyLine: string
}

const REASON_LABELS: Record<string, string> = {
  not_collected: '尚未采集最近 12 个完整 UTC 周。',
  insufficient_history: '仓库尚无可观察的完整 UTC 周。',
  incomplete_commits_coverage: 'Commit 覆盖不完整；缺失周不按零计算。',
  maintenance_page_budget_exceeded: 'Commit 采集达到课程版页数预算；只保留已观察事实，模型暂不可用。',
  stale: '维护活动数据已过期，请重新采集。',
  source_integrity_mismatch: '来源校验不一致，请重新采集。',
  source_archive_unavailable: '来源归档不可用，暂不能确认模型输入。',
  short_observation_window: '完整观察周不足 12 周，只展示可核实事实。',
  short_history: '最近 8 个完整 UTC 周不足，无法判断实际变化。',
  invalid_observation_length: '完整观察周数不足或无效，只展示可核实事实。',
  model_unavailable: '模型文件不可用，只展示近期事实。',
  low_activity_scope: '近期提交活动不足，不提供未来趋势预测。',
  partial_data: '数据覆盖不完整，暂不能生成此项结果。',
  insufficient_data: '当前样本不足以生成此项结果。',
  temporarily_unavailable: '当前暂时无法生成此项结果。',
}

export function maintenanceReason(reasonCode: string | null | undefined): string {
  return REASON_LABELS[reasonCode ?? ''] ?? '当前没有足够证据生成维护行为分析。'
}

function isMachineLearningTrend(evaluation: RepositoryEvaluation): boolean {
  return evaluation.activityTrend.status === 'available'
    && evaluation.activityTrend.method === 'machine_learning'
    && Boolean(evaluation.activityTrend.trend)
}

export function buildMaintenanceSummary(
  evaluation: RepositoryEvaluation | null,
  readError: string | null = null,
): MaintenanceSummaryView {
  if (readError) {
    return {
      status: 'error',
      headline: '近期分析数据读取失败',
      activityLine: '没有根据读取失败的请求生成任何趋势或异常判断。',
      anomalyLine: '请重试读取，或在任务页核对近期采集任务。',
    }
  }

  if (!evaluation) {
    return {
      status: 'waiting',
      headline: '尚未生成近期分析',
      activityLine: '采集完成后，这里会显示最近 4 周实际变化和未来 4 周模型预测。',
      anomalyLine: '异常提示也需要完整的近期 Commit 数据。',
    }
  }

  const pattern = evaluation.maintenancePattern
  const hasPatternEvidence = Object.keys(pattern.evidence).length > 0
  const patternLabel = pattern.displayName ?? pattern.patternName
  const patternAvailable = pattern.status === 'available'
    && pattern.method === 'machine_learning'
    && Boolean(patternLabel)
  const recent = evaluation.recentActivityChange
  const trend = evaluation.activityTrend
  const anomaly = evaluation.activityAnomaly
  const incomplete = pattern.coverage.commits === 'partial'
    || recent.status === 'partial_data'
    || trend.status === 'partial_data'
    || anomaly.status === 'partial_data'

  const headline = patternAvailable
    ? `近 12 周默认分支为「${patternLabel}」`
    : incomplete
      ? '近期 Commit 覆盖不完整'
      : !hasPatternEvidence && pattern.reasonCode === 'not_collected'
        ? '尚未生成近期分析'
        : hasPatternEvidence
          ? '近期默认分支 Commit 事实可读，模式模型暂不可用'
          : '近期分析证据有限'

  const actualLine = recent.status === 'available'
    ? `最近 4 周实际变化：${recent.trend ?? '已统计'}（${recent.recent4wCommits ?? '—'} vs ${recent.previous4wCommits ?? '—'} Commit）。`
    : `最近 4 周实际变化无法判定：${maintenanceReason(recent.reasonCode)} `
  const forecastLine = isMachineLearningTrend(evaluation)
    ? `未来 4 周活动趋势预测：${trend.trend}，可能存在预测误差。`
    : `未来 4 周预测暂不可用：${maintenanceReason(trend.reasonCode ?? trend.status)} `
  const anomalyLine = anomaly.status === 'baseline_only' && anomaly.method === 'statistical_baseline'
    ? anomaly.suspected ? 'MAD 统计规则提示疑似偏离，需结合项目事件人工核查。' : 'MAD 统计规则未发现明显异常。'
    : `异常提示暂无法判定：${maintenanceReason(anomaly.reasonCode ?? anomaly.status)}`

  return {
    status: incomplete ? 'partial' : patternAvailable || recent.status === 'available' ? 'available' : hasPatternEvidence ? 'limited' : 'waiting',
    headline,
    activityLine: `${actualLine}${forecastLine}`,
    anomalyLine,
  }
}
