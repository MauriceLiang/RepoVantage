<script setup lang="ts">
import { computed } from 'vue'
import type { G2Spec } from '@antv/g2'
import G2Chart from './G2Chart.vue'
import { summarizeByGroup } from '@/lib/chartAnalytics'

const props = withDefaults(defineProps<{
  samples: Array<{ group: string; value: number }>
  label: string
  unit: string
  height?: number
  shape?: 'box' | 'violin'
  scale?: 'linear' | 'log1p'
}>(), { height: 260, shape: 'box', scale: 'linear' })
const groupSummaries = computed(() => summarizeByGroup(props.samples))
const chartSamples = computed(() => props.samples.map((sample) => ({
  ...sample,
  plotValue: props.scale === 'log1p' ? Math.log1p(Math.max(0, sample.value)) : sample.value,
})))
function formatPlotValue(value: unknown) {
  const numeric = Number(value)
  const actualValue = props.scale === 'log1p' ? Math.expm1(numeric) : numeric
  return `${actualValue.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} ${props.unit}`
}
const spec = computed<G2Spec>(() => {
  const shared = {
    data: chartSamples.value,
    scale: { x: { paddingInner: 0.24, paddingOuter: 0.08 } },
    axis: {
      x: { labelFontSize: 9 },
      y: {
        title: props.scale === 'log1p' ? `${props.unit}（log1p 压缩）` : props.unit,
        gridLineDash: [3, 3],
        ...(props.scale === 'log1p' ? { labelFormatter: (value: unknown) => Math.expm1(Number(value)).toLocaleString('zh-CN', { maximumFractionDigits: 1 }) } : {}),
      },
    },
    legend: false,
  }

  if (props.shape === 'violin') {
    return {
      ...shared,
      type: 'view',
      children: [
        {
          type: 'density',
          data: { transform: [{ type: 'kde', field: 'plotValue', groupBy: ['group'], size: 40 }] },
          encode: { x: 'group', y: 'y', color: 'group', size: 'size' },
          tooltip: false,
          style: { fillOpacity: 0.28, lineWidth: 1 },
        },
        {
          type: 'boxplot',
          encode: { x: 'group', y: 'plotValue', color: 'group', shape: 'violin' },
          style: { opacity: 0.75, strokeOpacity: 0.85, point: false },
          tooltip: { title: 'group', items: [{ field: 'plotValue', name: props.unit, valueFormatter: formatPlotValue }] },
        },
      ],
    }
  }

  return {
    ...shared,
    type: 'boxplot',
    encode: { x: 'group', y: 'plotValue', color: 'group' },
    style: { boxFill: '#6d8fa3', boxFillOpacity: 0.52, boxStroke: '#527489', pointFill: '#d18a43', pointStroke: '#fff' },
    tooltip: { title: 'group', items: [{ field: 'plotValue', name: props.unit, valueFormatter: formatPlotValue }] },
  }
})
</script>

<template>
  <div class="boxplot-chart">
    <G2Chart :spec="spec" :label="label" :height="height" />
    <p class="boxplot-chart__counts">{{ groupSummaries.map((row) => `${row.group} · n=${row.count} · P50 ${row.p50.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} · P90 ${row.p90.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} ${unit}`).join('　') }}</p>
  </div>
</template>

<style scoped>
.boxplot-chart { min-width: 0; }
.boxplot-chart__counts { margin: 2px 0 0; color: var(--muted); font-size: 10px; line-height: 1.5; }
</style>
