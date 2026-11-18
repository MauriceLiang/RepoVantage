import type { RepositoryChartData, TimePoint } from '@/services/types'

const WEEK_MS = 7 * 24 * 60 * 60 * 1000

/** 整理同一时间轴上的提交与活跃账号；缺失或部分覆盖不能当作零。 */
export function buildCommitActivity(
  points: TimePoint[],
  weeks: RepositoryChartData['commitWeekly'],
  windowStart: string | null,
  windowEnd: string | null,
) {
  const byDate = new Map(weeks.map((week) => [week.start, week]))
  const start = windowStart ? Date.parse(windowStart) : NaN
  const end = windowEnd ? Date.parse(windowEnd) : NaN
  const hasWindow = Number.isFinite(start) && Number.isFinite(end) && start < end
  const rows = points.map((point, sourceIndex) => {
    const week = byDate.get(point.date)
    const complete = point.value !== null && point.completeWeek === true && point.quality === 'ready' && (week?.complete ?? true)
    const commits = point.value ?? (point.observedValue != null && point.observedValue > 0 ? point.observedValue : null)
    const authors = week?.activeAuthors ?? null
    return {
      date: point.date,
      sourceIndex,
      complete,
      commits,
      authors: complete || (authors !== null && authors > 0) ? authors : null,
      unidentifiedCommits: commits !== null ? week?.unidentifiedCommits ?? null : null,
    }
  }).filter((row) => {
    if (!hasWindow) return true
    const weekStart = Date.parse(row.date)
    return Number.isFinite(weekStart) && weekStart < end && weekStart + WEEK_MS > start
  })

  return rows
}
