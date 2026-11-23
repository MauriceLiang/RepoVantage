<script setup lang="ts">
import { computed } from 'vue'
import type { G2Spec } from '@antv/g2'
import type { PrDurationPeriod } from '@/services/types'
import G2Chart from './G2Chart.vue'

export type PrDurationGrain = 'weekly' | 'biweekly' | 'monthly'
const props = withDefaults(defineProps<{
  periods: PrDurationPeriod[]
  grain: PrDurationGrain
  selectedPeriodStart?: string | null
  height?: number
}>(), { selectedPeriodStart: null, height: 200 })
const emit = defineEmits<{ select: [period: PrDurationPeriod] }>()
const bucketLabels = ['<1 天', '1–3 天', '3–7 天', '7–30 天', '≥30 天']
const colors = ['#4a937b', '#678fba', '#8877ac', '#c99a59', '#cf716b']
function dateLabel(period: PrDurationPeriod) {
  if (props.grain === 'monthly') return period.start.slice(0, 7)
  return period.start.slice(5, 10).replace('-', '/')
}
function dateRangeLabel(period: PrDurationPeriod) {
  if (props.grain === 'monthly') return period.start.slice(0, 7)
  const lastDay = new Date(Date.parse(period.end) - 1).toISOString().slice(5, 10).replace('-', '/')
  return `${period.start.slice(5, 10).replace('-', '/')}–${lastDay}`
}
const periodLabels = computed(() => props.periods.map(dateLabel))
const rows = computed(() => props.periods.flatMap((period, dataIndex) => period.counts.map((count, bucketIndex) => ({
  label: periodLabels.value[dataIndex],
  periodRange: dateRangeLabel(period),
  bucket: bucketLabels[bucketIndex],
  count,
  complete: period.complete,
  validSamples: period.validSamples,
  dataIndex,
  seriesName: bucketLabels[bucketIndex],
})).filter(() => period.complete || period.validSamples > 0)))
const medianRows = computed(() => props.periods.map((period, dataIndex) => ({
  label: periodLabels.value[dataIndex],
  periodRange: dateRangeLabel(period),
  days: period.medianHours === null ? null : period.medianHours / 24,
  validSamples: period.validSamples,
  complete: period.complete,
  dataIndex,
  seriesName: '中位耗时',
})))
const countsSpec = computed<G2Spec>(() => ({
  type: 'interval', data: rows.value, transform: [{ type: 'stackY' }],
  encode: { x: 'label', y: 'count', color: 'bucket' },
  scale: { x: { domain: periodLabels.value }, color: { domain: bucketLabels, range: colors } },
  axis: { x: { labelFontSize: 9, labelAutoRotate: false }, y: { title: 'PR 数', gridLineDash: [3, 3] } },
  legend: { color: { position: 'bottom' } },
  interaction: { tooltip: { shared: true } },
  tooltip: { title: 'periodRange', items: [{ field: 'bucket', name: '耗时区间' }, { field: 'count', name: 'PR 数' }, { field: 'validSamples', name: '有效样本' }, { field: 'complete', name: '完整覆盖' }] },
}))
const medianSpec = computed<G2Spec>(() => ({
  type: 'line', data: medianRows.value,
  encode: { x: 'label', y: 'days' },
  scale: { x: { domain: periodLabels.value } },
  style: { stroke: '#252c32', lineWidth: 2.1 },
  axis: { x: { labelFontSize: 9, labelAutoRotate: false }, y: { title: '天', gridLineDash: [3, 3] } },
  tooltip: { title: 'periodRange', items: [{ field: 'days', name: '中位耗时（天）' }, { field: 'validSamples', name: '有效样本' }, { field: 'complete', name: '完整覆盖' }] },
}))
function select(payload: { dataIndex: number; seriesName: string }) {
  if (!bucketLabels.includes(payload.seriesName)) return
  const period = props.periods[payload.dataIndex]
  if (period) emit('select', period)
}
</script>

<template>
  <div class="duration-charts-shell">
    <div class="duration-charts" :style="{ minHeight: height + 'px' }">
      <section><h4>各耗时区间的 PR 数</h4><G2Chart :spec="countsSpec" label="按时间段堆叠的 PR 耗时分布；点击筛选该时段" :height="height" @select="select" /></section>
      <section><h4>每段中位耗时</h4><G2Chart :spec="medianSpec" label="每个时间段的 PR 合并中位耗时，单位天" :height="height" /></section>
    </div>
  </div>
</template>

<style scoped>
.duration-charts-shell { container-type:inline-size; min-width:0; }
.duration-charts { display:grid; grid-template-columns:minmax(0,1.3fr) minmax(0,1fr); gap:14px; }
.duration-charts section { min-width:0; }
.duration-charts h4 { margin:0 0 4px; color:var(--muted); font-size:10.5px; font-weight:600; }
@container (max-width: 680px) { .duration-charts { grid-template-columns:minmax(0,1fr); } }
</style>
