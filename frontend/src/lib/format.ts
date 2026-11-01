/** 将 API 时间统一按 UTC 显示；无法解析的日期保留原文，避免掩盖数据问题。 */
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
