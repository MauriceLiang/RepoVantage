import type { Coverage, NamedSeries, TimePoint } from '@/services/types'

const WEEK_MS = 7 * 24 * 60 * 60 * 1000

/** 对齐新增与关闭的 UTC 周；只有两个计数均完整时才计算差值。 */
export function buildIssueTrend(
  series: NamedSeries[],
  coverage: Coverage['state'],
  windowStart: string | null,
  windowEnd: string | null,
) {
  const opened = series.find((item) => item.key === 'opened' || item.key === 'created')?.points ?? []
  const closed = series.find((item) => item.key === 'closed')?.points ?? []
  const openedMap = new Map(opened.map((point) => [point.date, point]))
  const closedMap = new Map(closed.map((point) => [point.date, point]))
  const start = windowStart ? Date.parse(windowStart) : NaN
  const end = windowEnd ? Date.parse(windowEnd) : NaN
  const hasWindow = Number.isFinite(start) && Number.isFinite(end) && start < end

  function count(point: TimePoint | undefined) {
    if (!point) return { value: null, complete: false }
    const weekStart = Date.parse(point.date)
    const completeWeek = point.completeWeek ?? (hasWindow && weekStart >= start && weekStart + WEEK_MS <= end)
    const complete = point.value !== null && completeWeek && (
      point.quality === 'ready' || (point.quality === undefined && coverage === 'complete')
    )
    const observed = point.value ?? point.observedValue ?? null
    return { value: complete || (observed !== null && observed > 0) ? observed : null, complete }
  }

  const dates = [...new Set([...openedMap.keys(), ...closedMap.keys()])].filter((date) => {
    const weekStart = Date.parse(date)
    return Number.isFinite(weekStart) && (!hasWindow || (weekStart < end && weekStart + WEEK_MS > start))
  }).sort()

  // 如果两条序列都漏掉某周，补一个缺失点以断开折线，而不是连过空档。
  if (hasWindow && dates.length > 1) {
    const lastWeek = Date.parse(dates[dates.length - 1])
    for (let week = Date.parse(dates[0]) + WEEK_MS; week < lastWeek; week += WEEK_MS) {
      const date = new Date(week).toISOString().slice(0, 10)
      if (!dates.includes(date)) dates.push(date)
    }
    dates.sort()
  }

  return dates.map((date) => {
    const added = count(openedMap.get(date))
    const resolved = count(closedMap.get(date))
    return {
      date,
      added,
      resolved,
      difference: added.complete && resolved.complete ? (added.value ?? 0) - (resolved.value ?? 0) : null,
    }
  })
}
