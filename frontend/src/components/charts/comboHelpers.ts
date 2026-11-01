import type { RepositoryChartData, TimePoint } from '@/services/types'
import { fontFamily, type ChartTheme } from './theme'

// A zero observed in an incomplete bucket is not evidence that the true count is zero.
export const observedValue = (point: TimePoint | undefined) => point?.value != null
  ? point.value
  : point?.observedValue != null && point.observedValue > 0 ? point.observedValue : null

export function coveredCommitPoints(points: TimePoint[], weeks: RepositoryChartData['commitWeekly']): TimePoint[] {
  // The chart-specific coverage also checks a possibly narrower incremental query.
  // Preserve observed samples while withholding a total for unproven weeks.
  const byDate = new Map(weeks.map((week) => [week.start, week]))
  return points.map((point) => {
    const week = byDate.get(point.date)
    return { ...point, value: week?.complete ? week.observedCommits : null, observedValue: week?.observedCommits ?? null, quality: week?.complete ? 'ready' : 'partial' }
  })
}

export const escapeHtml = (value: string) => value.replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]!)
export const accountLabel = (key: string) => key.startsWith('github:') ? `GitHub #${key.slice(7)}` : key.startsWith('demo:') ? key.slice(5) : key

export const comboTooltip = (theme: ChartTheme) => ({
  backgroundColor: theme.panel, borderColor: theme.border, borderWidth: 1, padding: [9, 11] as [number, number],
  textStyle: { color: theme.ink, fontSize: 11.5, fontFamily },
  extraCssText: `border-radius:8px;box-shadow:${theme.dark ? '0 8px 24px rgba(0,0,0,.5)' : '0 6px 18px rgba(0,0,0,.12)'};`,
})
