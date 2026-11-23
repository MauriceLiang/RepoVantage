<script setup lang="ts">
import { computed } from 'vue'
import type { G2Spec } from '@antv/g2'
import type { HistogramBucket } from '@/services/types'
import G2Chart from './G2Chart.vue'

const props = withDefaults(defineProps<{
  buckets: HistogramBucket[]; color?: string; unit?: string; height?: number; medianDays?: number | null; showMedianReference?: boolean
}>(), { color: '#e5a03a', unit: '条记录', height: 200, medianDays: null, showMedianReference: false })
const rows = computed(() => {
  const total = props.buckets.reduce((sum, bucket) => sum + bucket.count, 0)
  let cumulative = 0
  return props.buckets.map((bucket) => {
    cumulative += bucket.count
    const cumulativePercent = total ? cumulative / total * 100 : null
    return { ...bucket, cumulativePercent }
  })
})
const spec = computed<G2Spec>(() => ({
  type: 'view', data: rows.value,
  children: [
    {
      type: 'interval',
      encode: { x: 'label', y: 'count' },
      scale: { y: { domainMin: 0 } },
      axis: { y: { title: '区间样本数', gridLineDash: [3, 3] } },
      style: { fill: props.color, fillOpacity: 0.82 },
    },
    {
      type: 'line',
      encode: { x: 'label', y: 'cumulativePercent' },
      scale: { y: { independent: true, domain: [0, 100] } },
      axis: { y: { position: 'right', title: '累计占比', labelFormatter: (value: number) => `${value}%`, grid: null } },
      style: { stroke: '#4d819b', lineWidth: 2.2, lineDash: [4, 2] },
    },
  ],
  axis: { x: { labelFontSize: 9, labelAutoRotate: true } },
  legend: false,
  tooltip: { title: 'label', items: [{ field: 'count', name: '该区间数量' }, { field: 'cumulativePercent', name: '累计占比', valueFormatter: (value: number | null) => value === null ? '—' : `${value.toFixed(1)}%` }] },
}))
</script>

<template>
  <div><G2Chart :spec="spec" :label="`${unit}区间分布`" :height="height" /><p v-if="showMedianReference" class="chart-note">P50：{{ medianDays === null ? '—' : `${medianDays.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 天` }}</p></div>
</template>

<style scoped>.chart-note { margin:4px 0 0; color:var(--muted); font-size:10.5px; }</style>
