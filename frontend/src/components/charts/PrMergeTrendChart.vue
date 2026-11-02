<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { EChartsOption } from 'echarts'
import type { RepositoryChartData, TimePoint } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { comboTooltip, escapeHtml, observedValue } from './comboHelpers'
import { chartTheme, fontFamily, MONO } from './theme'

const props = withDefaults(defineProps<{ points: TimePoint[]; data: RepositoryChartData; durationP90?: number | null; height?: number }>(), { durationP90: null, height: 270 })
const ui = useUiStore()
const midpoint = (date: string) => Date.parse(`${date}T00:00:00Z`) + 3.5 * 86400000
const dayMs = 86400000
const timeBounds = computed(() => {
  const values = [
    ...props.points.map((point) => midpoint(point.date)),
    ...props.data.prSamples.map((sample) => Date.parse(sample.mergedAt)),
  ].filter(Number.isFinite)
  return values.length ? { start: Math.min(...values), end: Math.max(...values) } : null
})
const selectedWindow = ref<{ start: number; end: number } | null>(null)
const visibleWindow = computed(() => selectedWindow.value ?? timeBounds.value)
const windowLabel = computed(() => {
  const range = visibleWindow.value
  if (!range) return ''
  const start = new Date(range.start).toISOString().slice(0, 10)
  const end = new Date(range.end).toISOString().slice(0, 10)
  const days = Math.max(1, Math.round((range.end - range.start) / dayMs))
  return `${start} 至 ${end} · ${days} 天`
})
watch([() => props.data, () => props.points, () => props.durationP90, () => ui.isDark], () => { selectedWindow.value = null })
function toTimestamp(value: number | string | undefined) {
  if (typeof value === 'number') return value
  if (typeof value !== 'string') return null
  const numeric = Number(value)
  const parsed = Number.isFinite(numeric) && /^\d+$/.test(value) ? numeric : Date.parse(value)
  return Number.isFinite(parsed) ? parsed : null
}
function updateWindow(payload: { start?: number; end?: number; startValue?: number | string; endValue?: number | string }) {
  const bounds = timeBounds.value
  if (!bounds) return
  const span = bounds.end - bounds.start
  const start = toTimestamp(payload.startValue) ?? (payload.start == null ? bounds.start : bounds.start + span * payload.start / 100)
  const end = toTimestamp(payload.endValue) ?? (payload.end == null ? bounds.end : bounds.start + span * payload.end / 100)
  if (Number.isFinite(start) && Number.isFinite(end)) selectedWindow.value = { start: Math.min(start, end), end: Math.max(start, end) }
}
const option = computed<EChartsOption>(() => {
  const t = chartTheme(ui.isDark)
  const zoomEnabled = timeBounds.value !== null && timeBounds.value.end > timeBounds.value.start
  const tailCap = props.durationP90 != null && props.durationP90 > 0 ? props.durationP90 : null
  return {
    useUTC: true, animation: false, grid: { left: 44, right: 50, top: 55, bottom: zoomEnabled ? 50 : 30 },
    legend: { top: 0, left: 0, data: ['合并数量', '单条耗时', '每周中位耗时'], textStyle: { color: t.muted, fontSize: 10, fontFamily }, itemWidth: 10, itemHeight: 8 },
    tooltip: { ...comboTooltip(t), trigger: 'item', formatter: (params: unknown) => {
      const p = params as { seriesName: string; dataIndex: number }
      if (p.seriesName === '单条耗时') {
        const sample = props.data.prSamples[p.dataIndex]
        return sample ? `<div>PR ID ${escapeHtml(sample.id)}</div><div>${escapeHtml(sample.mergedAt.replace('T', ' ').replace('Z', ' UTC'))}</div><div>合并耗时：<b>${(sample.durationHours / 24).toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 天</b></div>` : ''
      }
      const point = props.points[p.dataIndex]
      if (!point) return ''
      const week = props.data.prWeekly.find((item) => item.start === point.date)
      return `<div>${point.date} 起的 UTC 周${point.value === null ? ' · 已观察样本' : ''}</div><div>合并：<b>${observedValue(point) ?? '—'}</b></div><div>中位耗时：<b>${week?.medianHours == null ? '—' : `${(week.medianHours / 24).toFixed(1)} 天`}</b> · n=${week?.validSamples ?? 0}</div>`
    } },
    xAxis: { type: 'time', axisLine: { lineStyle: { color: t.border } }, axisTick: { show: false }, axisLabel: { color: t.muted, fontFamily: MONO, fontSize: 10, hideOverlap: true, formatter: (value: number) => new Date(value).toISOString().slice(5, 10) }, splitLine: { show: false } },
    yAxis: [
      { type: 'value', name: '合并数', minInterval: 1, nameTextStyle: { color: t.muted, fontSize: 10 }, axisLabel: { color: t.muted, fontSize: 10 }, splitLine: { lineStyle: { color: t.grid } } },
      { type: 'value', name: '耗时（天）', min: 0, nameTextStyle: { color: t.muted, fontSize: 10 }, axisLabel: { color: t.muted, fontSize: 10 }, splitLine: { show: false } },
    ],
    dataZoom: zoomEnabled ? [
      { type: 'inside', xAxisIndex: 0, filterMode: 'filter', startValue: timeBounds.value!.start, endValue: timeBounds.value!.end, zoomOnMouseWheel: true, moveOnMouseWheel: true, moveOnMouseMove: true },
      { type: 'slider', xAxisIndex: 0, filterMode: 'filter', startValue: timeBounds.value!.start, endValue: timeBounds.value!.end, height: 12, bottom: 0, showDetail: true, showDataShadow: false, brushSelect: false, borderColor: t.border, backgroundColor: t.soft, fillerColor: t.dark ? 'rgba(242,148,194,.2)' : 'rgba(206,63,124,.16)', handleStyle: { color: t.series[2], borderColor: t.border } },
    ] : undefined,
    series: [
      { name: '合并数量', type: 'bar', barMaxWidth: 25, data: props.points.map((point) => ({ value: [midpoint(point.date), observedValue(point)], itemStyle: { opacity: point.value === null ? 0.45 : 0.85 } })), itemStyle: { color: t.series[3] } },
      { name: '单条耗时', type: 'scatter', yAxisIndex: 1, symbolSize: 6, data: props.data.prSamples.map((sample) => { const days = sample.durationHours / 24; const longTail = tailCap !== null && days > tailCap; return { value: [sample.mergedAt, longTail ? tailCap * 0.94 : days], symbol: longTail ? 'triangle' : 'circle', symbolSize: longTail ? 9 : 6 } }), itemStyle: { color: t.series[2], opacity: 0.62 }, z: 3 },
      { name: '每周中位耗时', type: 'line', yAxisIndex: 1, connectNulls: false, symbol: 'circle', symbolSize: 5, data: props.points.map((point) => { const week = props.data.prWeekly.find((item) => item.start === point.date); const days = week?.medianHours == null ? null : week.medianHours / 24; const longTail = days !== null && tailCap !== null && days > tailCap; return { value: [midpoint(point.date), days === null ? null : longTail ? tailCap! * 0.94 : days], symbol: longTail ? 'triangle' : 'circle', symbolSize: longTail ? 9 : 5 } }), lineStyle: { color: t.series[0], width: 2.5 }, itemStyle: { color: t.series[0] }, z: 4 },
    ],
  }
})
</script>

<template>
  <div>
    <EChart :option="option" :height="height" @data-zoom="updateWindow" />
    <div v-if="timeBounds && timeBounds.end > timeBounds.start" class="mt-1 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-[10px] text-muted">
      <span>当前窗口：{{ windowLabel }}</span>
      <span>拖动两端调整长度，拖动选区平移</span>
    </div>
  </div>
</template>
