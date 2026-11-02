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
      average: null as number | null,
      releases: [] as ReleaseRecord[],
    }
  }).filter((row) => {
    if (!hasWindow) return true
    const weekStart = Date.parse(row.date)
    return Number.isFinite(weekStart) && weekStart < end && weekStart + WEEK_MS > start
  })

  // 只有连续四个完整 UTC 周才计算均值，缺失周与边界周不参与计算。
  for (let index = 3; index < rows.length; index += 1) {
    const window = rows.slice(index - 3, index + 1)
    if (window.every((row, offset) => row.complete && row.commits !== null && (
      offset === 0 || Date.parse(row.date) - Date.parse(window[offset - 1].date) === WEEK_MS
    ))) {
      rows[index].average = window.reduce((sum, row) => sum + (row.commits ?? 0), 0) / 4
    }
  }

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
