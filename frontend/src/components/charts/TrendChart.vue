<script setup lang="ts">
import { computed } from 'vue'
import type { G2Spec } from '@antv/g2'
import type { TimePoint } from '@/services/types'
import G2Chart from './G2Chart.vue'

const emit = defineEmits<{ select: [payload: { dataIndex: number; seriesName: string; name: string; value: unknown }] }>()
const props = withDefaults(defineProps<{ points: TimePoint[]; unit: string; color?: string; height?: number; movingAverageWindow?: number }>(), { color: '#2e8fcb', height: 260, movingAverageWindow: 0 })
const data = computed(() => props.points.flatMap((point, dataIndex) => {
  const rows = [{
    date: point.date, series: props.unit, value: point.value,
    plotted: point.value ?? point.observedValue ?? null, observedValue: point.observedValue ?? null,
    quality: point.quality ?? 'unknown', completeWeek: point.completeWeek ?? null,
    dataIndex, sourceIndex: dataIndex, seriesName: props.unit,
  }]
  if (props.movingAverageWindow > 1) {
    const window = props.points.slice(dataIndex - props.movingAverageWindow + 1, dataIndex + 1)
    const valid = window.length === props.movingAverageWindow && window.every((item) => item.value !== null && item.quality === 'ready' && item.completeWeek === true)
    rows.push({
      date: point.date, series: `${props.movingAverageWindow} 周均值`, value: valid ? window.reduce((sum, item) => sum + (item.value ?? 0), 0) / props.movingAverageWindow : null,
      plotted: valid ? window.reduce((sum, item) => sum + (item.value ?? 0), 0) / props.movingAverageWindow : null,
      observedValue: null, quality: valid ? 'ready' : 'insufficient_complete_weeks', completeWeek: valid,
      dataIndex, sourceIndex: dataIndex, seriesName: `${props.movingAverageWindow} 周均值`,
    })
  }
  return rows
}))
const spec = computed<G2Spec>(() => ({
  type: 'line', data: data.value,
  encode: { x: 'date', y: 'plotted', color: 'series' },
  scale: { color: { domain: props.movingAverageWindow > 1 ? [props.unit, `${props.movingAverageWindow} 周均值`] : [props.unit], range: [props.color, '#e5a03a'] } },
  style: { lineWidth: 2.2, lineJoin: 'round' },
  axis: { x: { labelFontSize: 9, labelAutoRotate: true }, y: { title: props.unit, gridLineDash: [3, 3] } },
  legend: { color: { position: 'bottom' } },
  interaction: { tooltip: { shared: true } },
  tooltip: { title: 'date', items: [
    { field: 'series', name: '序列' }, { field: 'value', name: props.unit },
    { field: 'observedValue', name: '部分周已观察数' }, { field: 'quality', name: '覆盖状态' },
  ] },
}))
</script>

<template><G2Chart :spec="spec" :label="`${unit}时间序列`" :height="height" @select="emit('select', $event)" /></template>
