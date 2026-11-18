<script setup lang="ts">
import { computed } from 'vue'
import type { G2Spec } from '@antv/g2'
import type { TimePoint } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import G2Chart from './G2Chart.vue'

const props = withDefaults(defineProps<{
  entries: { label: string; color: string; points: TimePoint[] }[]
  height?: number
}>(), { height: 280 })
const ui = useUiStore()
const spec = computed<G2Spec>(() => {
  const data = props.entries.flatMap((entry) => entry.points.map((point) => ({
    date: point.date,
    repository: entry.label,
    plotted: point.value ?? point.observedValue ?? null,
    value: point.value,
    observedValue: point.observedValue ?? null,
    quality: point.quality ?? 'unknown',
    completeWeek: point.completeWeek ?? null,
  })))
  const axisColor = ui.isDark ? '#bec8d0' : '#667480'
  const gridColor = ui.isDark ? '#303942' : '#e6ebef'
  return {
    type: 'line', data,
    encode: { x: 'date', y: 'plotted', color: 'repository' },
    scale: {
      color: { domain: props.entries.map((entry) => entry.label), range: props.entries.map((entry) => entry.color) },
    },
    style: { lineWidth: 2, lineJoin: 'round' },
    axis: {
      x: { labelFill: axisColor, labelFontSize: 9, labelAutoRotate: true, lineStroke: gridColor },
      y: { labelFill: axisColor, labelFontSize: 10, title: 'Commit / 周', gridStroke: gridColor, gridLineDash: [3, 3] },
    },
    legend: { color: { position: 'bottom', itemLabelFill: axisColor, itemLabelFontSize: 10 } },
    interaction: { tooltip: { shared: true, crosshairs: true } },
    tooltip: { title: 'date', items: [
      { field: 'repository', name: '仓库' }, { field: 'value', name: '完整周 Commit' },
      { field: 'observedValue', name: '部分周已观察数' }, { field: 'quality', name: '覆盖状态' },
    ] },
  }
})
</script>

<template><G2Chart :spec="spec" label="多个仓库的每周 Commit 对比图" :height="height" /></template>
