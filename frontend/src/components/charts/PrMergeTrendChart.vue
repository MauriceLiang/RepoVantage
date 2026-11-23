<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { G2Spec } from '@antv/g2'
import type { RepositoryChartData, TimePoint } from '@/services/types'
import DateRangeSlider from './DateRangeSlider.vue'
import G2Chart from './G2Chart.vue'

const props = withDefaults(defineProps<{ points: TimePoint[]; data: RepositoryChartData; durationP90?: number | null; height?: number }>(), { durationP90: null, height: 270 })
const DAY = 86_400_000
const allDates = computed(() => [
  ...props.points.map((point) => point.date),
  ...props.data.prSamples.map((sample) => sample.mergedAt.slice(0, 10)),
].filter((date) => /^\d{4}-\d{2}-\d{2}$/.test(date)).sort())
const minDate = computed(() => allDates.value[0] ?? '')
const maxDate = computed(() => allDates.value.at(-1) ?? '')
const startDate = ref('')
const endDate = ref('')
watch([minDate, maxDate], ([min, max]) => {
  if (!min || !max) { startDate.value = ''; endDate.value = ''; return }
  const latest = Date.parse(max + 'T00:00:00Z')
  startDate.value = new Date(Math.max(Date.parse(min + 'T00:00:00Z'), latest - 90 * DAY)).toISOString().slice(0, 10)
  endDate.value = max
}, { immediate: true })
const range = computed(() => {
  if (!startDate.value || !endDate.value || startDate.value > endDate.value) return null
  return { start: Date.parse(startDate.value + 'T00:00:00Z'), end: Date.parse(endDate.value + 'T00:00:00Z') + DAY }
})
const visiblePoints = computed(() => props.points.flatMap((point, dataIndex) => {
  const time = Date.parse(point.date + 'T00:00:00Z')
  if (!range.value || time < range.value.start || time >= range.value.end) return []
  const week = props.data.prWeekly.find((item) => item.start === point.date)
  return [{ date: point.date, count: point.value ?? point.observedValue ?? null, observed: point.value === null, quality: point.quality ?? 'unknown', validSamples: week?.validSamples ?? 0, dataIndex, seriesName: '每周合并' }]
}))
const visibleSamples = computed(() => props.data.prSamples.flatMap((sample, sourceIndex) => {
  const time = Date.parse(sample.mergedAt)
  if (!range.value || time < range.value.start || time >= range.value.end) return []
  const actualDays = sample.durationHours / 24
  const cap = props.durationP90 != null && props.durationP90 > 0 ? props.durationP90 : null
  const clipped = cap !== null && actualDays > cap
  return [{ date: sample.mergedAt, id: sample.id, durationDays: actualDays, plottedDays: clipped ? cap * 0.94 : actualDays, symbol: clipped ? 'triangle' : 'point', sourceIndex, dataIndex: sourceIndex, seriesName: '单条耗时' }]
}))
const visibleMedians = computed(() => props.points.flatMap((point, dataIndex) => {
  const time = Date.parse(point.date + 'T00:00:00Z')
  if (!range.value || time < range.value.start || time >= range.value.end) return []
  const period = props.data.prWeekly.find((item) => item.start === point.date)
  return [{ date: point.date, days: period?.medianHours == null ? null : period.medianHours / 24, validSamples: period?.validSamples ?? 0, dataIndex, seriesName: '每周中位耗时' }]
}))
const countSpec = computed<G2Spec>(() => ({
  type: 'interval', data: visiblePoints.value,
  encode: { x: 'date', y: 'count', color: 'observed' },
  scale: { color: { domain: [false, true], range: ['#4d819b', '#a9c4d1'] } },
  axis: { x: { labelFontSize: 8, labelAutoRotate: true }, y: { title: 'PR / 周', gridLineDash: [3, 3] } },
  tooltip: { title: 'date', items: [{ field: 'count', name: '合并数（完整或已观察）' }, { field: 'quality', name: '覆盖状态' }, { field: 'validSamples', name: '有效耗时样本' }] },
}))
const samplesSpec = computed<G2Spec>(() => ({
  type: 'point', data: visibleSamples.value,
  encode: { x: 'date', y: 'plottedDays', shape: 'symbol' },
  scale: { y: props.durationP90 != null && props.durationP90 > 0 ? { domain: [0, props.durationP90] } : undefined, shape: { domain: ['point', 'triangle'], range: ['point', 'triangle'] } },
  style: { fill: '#ce3f7c', stroke: '#ce3f7c', r: 3.5 },
  axis: { x: { labelFontSize: 8, labelAutoRotate: true }, y: { title: '单条耗时（天）', gridLineDash: [3, 3] } },
  tooltip: { title: 'date', items: [{ field: 'id', name: 'PR ID' }, { field: 'durationDays', name: '合并耗时（真实天数）' }] },
}))
const medianSpec = computed<G2Spec>(() => ({
  type: 'line', data: visibleMedians.value,
  encode: { x: 'date', y: 'days' },
  style: { stroke: '#8177a0', lineWidth: 2.3 },
  axis: { x: { labelFontSize: 8, labelAutoRotate: true }, y: { title: '每周中位（天）', gridLineDash: [3, 3] } },
  tooltip: { title: 'date', items: [{ field: 'days', name: '中位耗时（天）' }, { field: 'validSamples', name: '有效样本' }] },
}))
</script>

<template>
  <div class="pr-merge-chart">
    <div class="pr-merge-chart__range">
      <DateRangeSlider v-model:start-date="startDate" v-model:end-date="endDate" :min-date="minDate" :max-date="maxDate" range-label="PR 合并趋势日期范围" />
    </div>
    <div class="pr-merge-chart__panels">
      <section><h4>每周合并数量</h4><G2Chart :spec="countSpec" label="PR 每周合并数量，单位条" :height="Math.max(210, height)" /></section>
      <section><h4>单条 PR 合并耗时</h4><G2Chart :spec="samplesSpec" label="单条 PR 合并耗时散点，悬浮显示真实天数" :height="Math.max(210, height)" /></section>
      <section><h4>每周耗时中位数</h4><G2Chart :spec="medianSpec" label="每周 PR 合并耗时中位数，单位天" :height="Math.max(210, height)" /></section>
    </div>
    <p v-if="durationP90 != null && durationP90 > 0" class="pr-merge-chart__note">单条耗时纵轴上限为全窗口 P90（{{ durationP90 }} 天）；超过阈值的点靠近顶部显示，悬浮仍列出真实耗时。</p>
  </div>
</template>

<style scoped>
.pr-merge-chart__range { min-width:0; margin:4px 0 8px; }
.pr-merge-chart__panels { display:grid; grid-template-columns:minmax(0,1fr); gap:8px; }
.pr-merge-chart__panels section { min-width:0; }
.pr-merge-chart__panels h4 { margin:0; color:var(--muted); font-size:10px; font-weight:600; }
.pr-merge-chart__note { margin:4px 0; color:var(--muted); font-size:10px; }
@media (min-width: 1000px) { .pr-merge-chart__panels { grid-template-columns:repeat(3,minmax(0,1fr)); } }
</style>
