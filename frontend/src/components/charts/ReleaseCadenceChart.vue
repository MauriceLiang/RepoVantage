<script setup lang="ts">
import { computed } from 'vue'
import type { G2Spec } from '@antv/g2'
import G2Chart from './G2Chart.vue'

interface ReleaseCadencePoint {
  tag: string
  previousTag: string
  date: string
  days: number
  previousDate: string | null
  commitCount: number | null
  reason: string | null
}
const props = withDefaults(defineProps<{ items: ReleaseCadencePoint[]; height?: number }>(), { height: 280 })
const emit = defineEmits<{ select: [tag: string] }>()
const sorted = computed(() => {
  const items = [...props.items].sort((a, b) => a.date.localeCompare(b.date))
  const years = new Set(items.map((item) => item.date.slice(0, 4)))
  return items.map((item, dataIndex) => ({
    ...item,
    label: years.size > 1 ? item.date.slice(2, 10).replace(/-/g, '/') : item.date.slice(5, 10).replace('-', '/'),
    dataIndex,
    seriesName: '发布间隔',
  }))
})
const spec = computed<G2Spec>(() => ({
  type: 'interval', data: sorted.value,
  encode: { x: 'label', y: 'days' },
  style: { fill: '#4d819b', radiusTopLeft: 3, radiusTopRight: 3 },
  axis: { x: { labelFontSize: 8, labelAutoRotate: false }, y: { title: '间隔（天）', gridLineDash: [3, 3] } },
  tooltip: { title: 'label', items: [{ field: 'previousTag', name: '上一版本' }, { field: 'tag', name: '当前版本' }, { field: 'days', name: '发布间隔（天）' }, { field: 'commitCount', name: '期间 Commit' }, { field: 'reason', name: 'Commit 覆盖说明' }] },
}))
function select(payload: { dataIndex: number; seriesName: string }) {
  if (payload.seriesName !== '发布间隔') return
  const item = sorted.value[payload.dataIndex]
  if (item) emit('select', item.tag)
}
</script>

<template><G2Chart :spec="spec" label="相邻正式 Release 间隔，单位天；点击查看版本" :height="height" @select="select" /></template>
