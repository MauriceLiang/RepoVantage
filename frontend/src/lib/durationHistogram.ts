import type { HistogramBucket } from '@/services/types'

/** 将后端耗时桶原样转换为区间柱或累计数量线，不插补桶内精确耗时。 */
export function buildHistogramRows(buckets: HistogramBucket[], cumulativeStep: boolean) {
  let cumulative = 0
  return buckets.map((bucket, dataIndex) => {
    cumulative += bucket.count
    return { label: bucket.label, count: bucket.count, plotted: cumulativeStep ? cumulative : bucket.count, dataIndex, seriesName: cumulativeStep ? '累计样本' : '区间数量' }
  })
}
