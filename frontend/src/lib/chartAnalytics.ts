export interface NumericSample {
  group: string
  value: number
}

export interface CorrelationCell {
  x: string
  y: string
  correlation: number | null
  sampleSize: number
}

export interface DistributionSummary {
  group: string
  count: number
  p50: number
  p90: number
}

export function dailyCoveragePoints(
  counts: Array<{ date: string; count: number }>,
  windowStart: string | null | undefined,
  windowEnd: string | null | undefined,
  complete: boolean,
): Array<{ date: string; value: number | null; observedValue?: number; quality?: string }> {
  const observed = new Map<string, number>()
  for (const item of counts) {
    const date = item.date.slice(0, 10)
    if (/^\d{4}-\d{2}-\d{2}$/.test(date) && Number.isFinite(item.count) && item.count >= 0) {
      observed.set(date, (observed.get(date) ?? 0) + item.count)
    }
  }
  if (!complete) {
    return [...observed.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([date, count]) => ({
      date,
      value: null,
      observedValue: count,
      quality: '部分覆盖',
    }))
  }

  const exactObservedDays = () => [...observed.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([date, count]) => ({
    date,
    value: count,
    quality: '完整归档',
  }))
  if (!windowStart || !windowEnd) return exactObservedDays()

  const start = Date.parse(windowStart)
  const end = Date.parse(windowEnd)
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return exactObservedDays()
  const cursor = new Date(start)
  cursor.setUTCHours(0, 0, 0, 0)
  const points: Array<{ date: string; value: number; quality: string }> = []
  while (cursor.getTime() < end) {
    const date = cursor.toISOString().slice(0, 10)
    points.push({ date, value: observed.get(date) ?? 0, quality: '完整覆盖' })
    cursor.setUTCDate(cursor.getUTCDate() + 1)
  }
  return points
}

export function summarizeByGroup(samples: NumericSample[]): DistributionSummary[] {
  const groups = new Map<string, number[]>()
  for (const sample of samples) {
    if (!Number.isFinite(sample.value)) continue
    const values = groups.get(sample.group) ?? []
    values.push(sample.value)
    groups.set(sample.group, values)
  }
  const quantile = (values: number[], probability: number) => {
    const sorted = [...values].sort((left, right) => left - right)
    const position = (sorted.length - 1) * probability
    const lower = Math.floor(position)
    const upper = Math.ceil(position)
    return sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower)
  }
  return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([group, values]) => ({
    group,
    count: values.length,
    p50: quantile(values, 0.5),
    p90: quantile(values, 0.9),
  }))
}

export function populationStandardDeviation(values: number[]): number {
  if (values.length === 0) return 0
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length
  return Math.sqrt(values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length)
}

export function linearSlope(values: number[]): number {
  if (values.length < 2) return 0
  const xMean = (values.length - 1) / 2
  const yMean = values.reduce((sum, value) => sum + value, 0) / values.length
  let covariance = 0
  let variance = 0
  values.forEach((value, index) => {
    const delta = index - xMean
    covariance += delta * (value - yMean)
    variance += delta ** 2
  })
  return variance === 0 ? 0 : covariance / variance
}

export function groupByMonth(samples: Array<{ date: string | null; value: number | null }>, minimumSampleSize = 5): NumericSample[] {
  const groups = new Map<string, number[]>()
  for (const sample of samples) {
    if (!sample.date || sample.value === null || !Number.isFinite(sample.value) || sample.value < 0) continue
    const month = sample.date.slice(0, 7)
    if (!/^\d{4}-\d{2}$/.test(month)) continue
    const values = groups.get(month) ?? []
    values.push(sample.value)
    groups.set(month, values)
  }
  return [...groups.entries()]
    .filter(([, values]) => values.length >= minimumSampleSize)
    .sort(([left], [right]) => left.localeCompare(right))
    .flatMap(([group, values]) => values.map((value) => ({ group, value })))
}

export function pearsonCorrelation(left: number[], right: number[]): number | null {
  const pairs = left.flatMap((value, index) => Number.isFinite(value) && Number.isFinite(right[index]) ? [[value, right[index]] as const] : [])
  if (pairs.length < 3) return null
  const meanX = pairs.reduce((sum, pair) => sum + pair[0], 0) / pairs.length
  const meanY = pairs.reduce((sum, pair) => sum + pair[1], 0) / pairs.length
  const covariance = pairs.reduce((sum, pair) => sum + (pair[0] - meanX) * (pair[1] - meanY), 0)
  const varianceX = pairs.reduce((sum, pair) => sum + (pair[0] - meanX) ** 2, 0)
  const varianceY = pairs.reduce((sum, pair) => sum + (pair[1] - meanY) ** 2, 0)
  if (!varianceX || !varianceY) return null
  return covariance / Math.sqrt(varianceX * varianceY)
}

export function correlationMatrix<T>(rows: T[], dimensions: Array<{ key: keyof T; label: string }>): CorrelationCell[] {
  return dimensions.flatMap((xDimension) => dimensions.map((yDimension) => {
    const pairs = rows.flatMap((row) => {
      const x = row[xDimension.key]
      const y = row[yDimension.key]
      return typeof x === 'number' && Number.isFinite(x) && typeof y === 'number' && Number.isFinite(y) ? [{ x, y }] : []
    })
    return {
      x: xDimension.label,
      y: yDimension.label,
      correlation: pearsonCorrelation(pairs.map((pair) => pair.x), pairs.map((pair) => pair.y)),
      sampleSize: pairs.length,
    }
  }))
}

export function normalizeMetrics<T extends Record<string, string | number | null>>(
  rows: T[],
  dimensions: Array<{ key: string; direction: 'higher' | 'lower' }>,
): Array<T & { [key: string]: string | number | null }> {
  return rows.map((row) => {
    const normalized: Record<string, string | number | null> = { ...row }
    for (const dimension of dimensions) {
      const values = rows.map((candidate) => candidate[dimension.key]).filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
      const value = row[dimension.key]
      if (typeof value !== 'number' || !Number.isFinite(value) || values.length === 0) {
        normalized[`${dimension.key}Score`] = null
        continue
      }
      const min = Math.min(...values)
      const max = Math.max(...values)
      const scaled = max === min ? 50 : ((value - min) / (max - min)) * 100
      normalized[`${dimension.key}Score`] = dimension.direction === 'higher' ? scaled : 100 - scaled
    }
    return normalized as T & { [key: string]: string | number | null }
  })
}

export function countBy<T>(items: T[], key: (item: T) => string): Array<{ label: string; value: number }> {
  const counts = new Map<string, number>()
  for (const item of items) counts.set(key(item), (counts.get(key(item)) ?? 0) + 1)
  return [...counts.entries()].map(([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value || a.label.localeCompare(b.label))
}

export function histogram(values: number[], bins: Array<{ label: string; max: number }>): Array<{ label: string; count: number }> {
  const counts = bins.map(() => 0)
  for (const value of values) {
    if (!Number.isFinite(value) || value < 0) continue
    const index = bins.findIndex((bin) => value <= bin.max)
    if (index >= 0) counts[index] += 1
  }
  return bins.map((bin, index) => ({ label: bin.label, count: counts[index] }))
}
