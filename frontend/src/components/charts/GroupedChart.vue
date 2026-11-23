<script setup lang="ts">
import { computed } from 'vue'
import type { G2Spec } from '@antv/g2'
import type { NamedSeries } from '@/services/types'
import G2Chart from './G2Chart.vue'

const emit = defineEmits<{ select: [payload: { dataIndex: number; seriesName: string; name: string; value: unknown }] }>()
const props = withDefaults(defineProps<{ series: NamedSeries[]; unit: string; colors?: string[]; height?: number; showLegend?: boolean }>(), { colors: () => [], height: 240, showLegend: true })
const rows = computed(() => props.series.flatMap((series) => series.points.map((point, dataIndex) => ({
  date: point.date, series: series.label, value: point.value, plotted: point.value ?? point.observedValue ?? null,
  observedValue: point.observedValue ?? null, quality: point.quality ?? 'unknown', completeWeek: point.completeWeek ?? null,
  dataIndex, sourceIndex: dataIndex, seriesName: series.label,
}))))
const spec = computed<G2Spec>(() => ({
  type: 'line', data: rows.value,
  encode: { x: 'date', y: 'plotted', color: 'series' },
  scale: { color: { domain: props.series.map((item) => item.label), range: props.colors.length ? props.colors : undefined } },
  style: { lineWidth: 2.1, lineJoin: 'round' },
  axis: { x: { labelFontSize: props.height < 140 ? 8 : 9, labelAutoRotate: true }, y: { title: props.unit, gridLineDash: [3, 3] } },
  legend: props.showLegend && props.series.length > 1 ? { color: { position: 'bottom' } } : false,
  interaction: { tooltip: { shared: true } },
  tooltip: { title: 'date', items: [
    { field: 'series', name: '序列' }, { field: 'value', name: props.unit },
    { field: 'observedValue', name: '部分周已观察数' }, { field: 'quality', name: '覆盖状态' },
  ] },
}))
</script>

<template><G2Chart :spec="spec" :label="`${unit}分组时间序列`" :height="height" @select="emit('select', $event)" /></template>
