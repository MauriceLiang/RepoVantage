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
}>(), { height: 260, shape: 'box' })
const groupSummaries = computed(() => summarizeByGroup(props.samples))
const spec = computed<G2Spec>(() => {
  const shared = {
    data: props.samples,
    scale: { x: { paddingInner: 0.24, paddingOuter: 0.08 } },
    axis: { x: { labelFontSize: 9 }, y: { title: props.unit, gridLineDash: [3, 3] } },
    legend: false,
  }

  if (props.shape === 'violin') {
    return {
      ...shared,
      type: 'view',
      children: [
        {
          type: 'density',
          data: { transform: [{ type: 'kde', field: 'value', groupBy: ['group'], size: 40 }] },
          encode: { x: 'group', y: 'y', color: 'group', size: 'size' },
          tooltip: false,
          style: { fillOpacity: 0.28, lineWidth: 1 },
        },
        {
          type: 'boxplot',
          encode: { x: 'group', y: 'value', color: 'group', shape: 'violin' },
          style: { opacity: 0.75, strokeOpacity: 0.85, point: false },
          tooltip: { title: 'group', items: [{ field: 'value', name: props.unit }] },
        },
      ],
    }
  }

  return {
    ...shared,
    type: 'boxplot',
    encode: { x: 'group', y: 'value', color: 'group' },
    style: { boxFill: '#6d8fa3', boxFillOpacity: 0.52, boxStroke: '#527489', pointFill: '#d18a43', pointStroke: '#fff' },
    tooltip: { title: 'group', items: [{ field: 'value', name: props.unit }] },
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
