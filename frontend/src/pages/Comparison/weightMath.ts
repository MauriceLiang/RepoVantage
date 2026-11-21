import type { SelectionMetric } from '@/services/types'

export type WeightPreset = 'balanced' | 'activity' | 'collaboration' | 'release' | 'custom'

export interface SelectionMetricOption {
  key: SelectionMetric
  label: string
  color: string
  direction: '越多越好' | '越短越好'
}

export interface MetricReadiness {
  ready: number
  total: number
  partial: number
  comparableForAll: boolean
}

export const selectionMetrics: SelectionMetricOption[] = [
  { key: 'commits_weekly_mean', label: '每周 Commit', color: '#E2683C', direction: '越多越好' },
  { key: 'issue_median_hours', label: 'Issue 关闭耗时', color: '#CE3F7C', direction: '越短越好' },
  { key: 'pr_median_hours', label: 'PR 合并耗时', color: '#2E8FCB', direction: '越短越好' },
  { key: 'release_interval_days', label: 'Release 间隔', color: '#E5A03A', direction: '越短越好' },
]

export type SelectionWeights = Record<SelectionMetric, number>

export function presetWeights(preset: Exclude<WeightPreset, 'custom'>): SelectionWeights {
  switch (preset) {
    case 'balanced':
      return { commits_weekly_mean: 25, issue_median_hours: 25, pr_median_hours: 25, release_interval_days: 25 }
    case 'activity':
      return { commits_weekly_mean: 100, issue_median_hours: 0, pr_median_hours: 0, release_interval_days: 0 }
    case 'collaboration':
      return { commits_weekly_mean: 0, issue_median_hours: 50, pr_median_hours: 50, release_interval_days: 0 }
    case 'release':
      return { commits_weekly_mean: 0, issue_median_hours: 0, pr_median_hours: 0, release_interval_days: 100 }
  }
}

/** Changes one percentage and proportionally redistributes the remainder. */
export function rebalanceWeight(
  current: SelectionWeights,
  changed: SelectionMetric,
  requested: number,
): SelectionWeights {
  if (!Number.isFinite(requested)) return { ...current }

  const desired = Math.min(100, Math.max(0, requested))
  const siblings = selectionMetrics.map(({ key }) => key).filter((key) => key !== changed)
  if (siblings.length === 0) return { ...current, [changed]: 100 }

  const next = { ...current, [changed]: desired }
  const remaining = 100 - desired
  const siblingTotal = siblings.reduce((sum, key) => sum + Math.max(0, current[key]), 0)
  let assigned = 0

  siblings.forEach((key, index) => {
    const prior = Math.max(0, current[key])
    const proportion = siblingTotal > 0 ? prior / siblingTotal : 1 / siblings.length
    const share = index === siblings.length - 1 ? remaining - assigned : remaining * proportion
    next[key] = share
    assigned += share
  })

  return next
}
