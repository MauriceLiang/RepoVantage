<script setup lang="ts">
import { computed } from 'vue'
import type { G2Spec } from '@antv/g2'
import G2Chart from './G2Chart.vue'

const props = withDefaults(defineProps<{
  rows: Array<{ stage: string; value: number; definition: string }>
  label: string
  height?: number
}>(), { height: 300 })
const spec = computed<G2Spec>(() => ({
  type: 'interval',
  data: props.rows,
  encode: { x: 'stage', y: 'value', color: 'stage', shape: 'funnel' },
  coordinate: { transform: [{ type: 'transpose' }] },
  transform: [{ type: 'symmetryY' }],
  scale: { x: { padding: 0.04 } },
  axis: false,
  legend: false,
  labels: [{ text: (datum: { stage: string; value: number }) => `${datum.stage} · ${datum.value}`, position: 'inside', transform: [{ type: 'contrastReverse' }] }],
  tooltip: { title: 'stage', items: [{ field: 'value', name: '候选数' }, { field: 'definition', name: '阶段定义' }] },
}))
</script>

<template><G2Chart :spec="spec" :label="label" :height="height" /></template>
