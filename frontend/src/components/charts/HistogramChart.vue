<script setup lang="ts">
import { computed } from 'vue'
import type { G2Spec } from '@antv/g2'
import type { HistogramBucket } from '@/services/types'
import G2Chart from './G2Chart.vue'
import { buildHistogramRows } from '@/lib/durationHistogram'

const props = withDefaults(defineProps<{
  buckets: HistogramBucket[]; color?: string; unit?: string; height?: number; cumulativeStep?: boolean; medianDays?: number | null; showMedianReference?: boolean
}>(), { color: '#e5a03a', unit: '条记录', height: 200, cumulativeStep: true, medianDays: null, showMedianReference: false })
const rows = computed(() => buildHistogramRows(props.buckets, props.cumulativeStep))
const spec = computed<G2Spec>(() => ({
  type: props.cumulativeStep ? 'line' : 'interval', data: rows.value,
  encode: { x: 'label', y: 'plotted' }, style: { stroke: props.color, fill: props.color, lineWidth: 2.2 },
  axis: { x: { labelFontSize: 9, labelAutoRotate: true }, y: { title: props.cumulativeStep ? '累计数量' : props.unit, gridLineDash: [3, 3] } },
  tooltip: { title: 'label', items: [{ field: 'count', name: '该区间数量' }, { field: 'plotted', name: props.cumulativeStep ? '累计数量' : props.unit }] },
}))
</script>

<template>
  <div><G2Chart :spec="spec" :label="`${unit}区间分布`" :height="height" /><p v-if="showMedianReference" class="chart-note">P50：{{ medianDays === null ? '—' : `${medianDays.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 天` }}</p></div>
</template>

<style scoped>.chart-note { margin:4px 0 0; color:var(--muted); font-size:10.5px; }</style>
