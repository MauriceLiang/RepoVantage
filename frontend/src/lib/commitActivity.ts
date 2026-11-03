import type { ReleaseRecord, RepositoryChartData, TimePoint } from '@/services/types'

const WEEK_MS = 7 * 24 * 60 * 60 * 1000

/** 整理同一时间轴上的提交、账号和发布；缺失或部分覆盖不能当作零。 */
export function buildCommitActivity(
  points: TimePoint[],
  weeks: RepositoryChartData['commitWeekly'],
  releases: ReleaseRecord[],
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
      releases: [] as ReleaseRecord[],
    }
  }).filter((row) => {
    if (!hasWindow) return true
    const weekStart = Date.parse(row.date)
    return Number.isFinite(weekStart) && weekStart < end && weekStart + WEEK_MS > start
  })

  if (hasWindow) {
    for (const release of releases) {
      if (release.prerelease) continue
      const published = Date.parse(release.publishedAt)
      if (!Number.isFinite(published) || published < start || published >= end) continue
      const row = rows.find((item) => {
        const weekStart = Date.parse(item.date)
        return Number.isFinite(weekStart) && weekStart <= published && published < weekStart + WEEK_MS
      })
      row?.releases.push(release)
    }
  }
  for (const row of rows) row.releases.sort((a, b) => Date.parse(a.publishedAt) - Date.parse(b.publishedAt))
  return rows
}
