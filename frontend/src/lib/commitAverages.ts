import type { TimePoint } from '@/services/types'

const WEEK_MS = 7 * 24 * 60 * 60 * 1000

/** 最近四个连续、完整且 ready 的 UTC 周提交均值；缺周或部分周不插补。 */
export function buildCompleteFourWeekAverage(points: TimePoint[]) {
  return points.map((point, dataIndex) => {
    const window = points.slice(dataIndex - 3, dataIndex + 1)
    const consecutive = window.length === 4 && window.every((item, index) => index === 0 || Date.parse(item.date + 'T00:00:00Z') - Date.parse(window[index - 1].date + 'T00:00:00Z') === WEEK_MS)
    const valid = consecutive && window.every((item) => item.value !== null && item.quality === 'ready' && item.completeWeek === true)
    return { date: point.date, value: valid ? window.reduce((sum, item) => sum + (item.value ?? 0), 0) / 4 : null, dataIndex, seriesName: '4 周均值' }
  })
}
