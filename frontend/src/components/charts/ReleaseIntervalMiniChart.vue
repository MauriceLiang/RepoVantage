<script setup lang="ts">
import { computed } from 'vue'
import type { G2Spec } from '@antv/g2'
import G2Chart from './G2Chart.vue'

interface ReleaseIntervalPoint {
  previousTag: string
  tag: string
  previousPublishedAt: string
  publishedAt: string
  days: number
}
const props = withDefaults(defineProps<{ items: ReleaseIntervalPoint[]; height?: number }>(), { height: 112 })
const sorted = computed(() => [...props.items].sort((a, b) => a.publishedAt.localeCompare(b.publishedAt)).map((item, dataIndex) => ({
  ...item,
  label: item.publishedAt.slice(5, 10).replace('-', '/'),
  dataIndex,
  seriesName: '发布间隔',
})))
const median = computed(() => {
  const values = props.items.map((item) => item.days).sort((a, b) => a - b)
  if (!values.length) return null
  const middle = Math.floor(values.length / 2)
  return values.length % 2 ? values[middle] : (values[middle - 1] + values[middle]) / 2
})
const spec = computed<G2Spec>(() => ({
  type: 'interval', data: sorted.value,
  encode: { x: 'label', y: 'days' },
  style: { fill: '#8177a0', radiusTopLeft: 2, radiusTopRight: 2 },
  axis: { x: { labelFontSize: 8, labelAutoRotate: false }, y: { title: false, label: false, grid: false } },
  tooltip: { title: 'label', items: [{ field: 'previousTag', name: '上一版本' }, { field: 'tag', name: '当前版本' }, { field: 'previousPublishedAt', name: '上一发布日期' }, { field: 'publishedAt', name: '发布日期' }, { field: 'days', name: '间隔（天）' }] },
}))
</script>

<template>
  <div><G2Chart :spec="spec" label="相邻正式 Release 间隔；单位天" :height="height" /><p class="median">发布间隔 P50：{{ median === null ? '—' : median.toLocaleString('zh-CN', { maximumFractionDigits: 1 }) + ' 天' }}</p></div>
</template>

<style scoped>.median { margin:1px 0 0; color:var(--muted); font-size:10px; text-align:right; }</style>
