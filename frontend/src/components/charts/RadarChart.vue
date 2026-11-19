<script setup lang="ts">
import { computed } from 'vue'
import type { G2Spec } from '@antv/g2'
import G2Chart from './G2Chart.vue'

const props = withDefaults(defineProps<{
  rows: Array<Record<string, string | number | null>>
  dimensions: string[]
  dimensionLabels?: string[]
  seriesField: string
  label: string
  height?: number
}>(), { height: 360 })
const spec = computed<G2Spec>(() => ({
  type: 'line',
  coordinate: { type: 'radar' },
  data: props.rows,
  encode: { position: props.dimensions, color: props.seriesField },
  scale: Object.fromEntries(props.dimensions.map((_, index) => [`position${index || ''}`, { domain: [0, 100], nice: false }])),
  axis: Object.fromEntries(props.dimensions.map((_, index) => [`position${index || ''}`, { label: true, labelFontSize: 9, title: props.dimensionLabels?.[index] ?? props.dimensions[index], titleFontSize: 9, line: true, grid: true }])),
  legend: { color: { position: 'bottom', itemLabelFontSize: 9 } },
  style: { lineWidth: 1.8, strokeOpacity: 0.74 },
  interaction: { tooltip: { series: false } },
  tooltip: { title: props.seriesField, items: props.dimensions.map((field) => ({ field, name: field })) },
}))
</script>

<template><G2Chart :spec="spec" :label="label" :height="height" /></template>
