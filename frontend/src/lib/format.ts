/** Format API timestamps consistently in UTC; keep unparseable dates visible. */
export function formatDate(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toISOString().slice(0, 10)
}

export function formatTime(value: string | null | undefined) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : `${date.toISOString().slice(11, 19)} UTC`
}

export function formatDuration(value: number | null) {
  return value === null ? '—' : `${value.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 天`
}
