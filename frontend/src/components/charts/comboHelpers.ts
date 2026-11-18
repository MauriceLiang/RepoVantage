import type { RepositoryChartData, TimePoint } from '@/services/types'

// 覆盖不完整时，观察到零并不能证明真实数量为零。
export const observedValue = (point: TimePoint | undefined) => point?.value != null
  ? point.value
  : point?.observedValue != null && point.observedValue > 0 ? point.observedValue : null

export function coveredCommitPoints(points: TimePoint[], weeks: RepositoryChartData['commitWeekly']): TimePoint[] {
  // 图表覆盖状态还要检查增量查询是否只包含更窄的区间。
  // 对无法证明完整的周保留已观察样本，但不展示完整周总量。
  const byDate = new Map(weeks.map((week) => [week.start, week]))
  return points.map((point) => {
    const week = byDate.get(point.date)
    return { ...point, value: week?.complete ? week.observedCommits : null, observedValue: week?.observedCommits ?? null, quality: week?.complete ? 'ready' : 'partial' }
  })
}
