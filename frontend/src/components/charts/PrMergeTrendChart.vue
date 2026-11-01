<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import type { RepositoryChartData, TimePoint } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { comboTooltip, escapeHtml, observedValue } from './comboHelpers'
import { chartTheme, fontFamily, MONO } from './theme'

const props = withDefaults(defineProps<{ points: TimePoint[]; data: RepositoryChartData; height?: number }>(), { height: 250 })
const ui = useUiStore()
const midpoint = (date: string) => Date.parse(`${date}T00:00:00Z`) + 3.5 * 86400000
const option = computed<EChartsOption>(() => {
  const t = chartTheme(ui.isDark)
  return {
    useUTC: true, animation: false, grid: { left: 44, right: 50, top: 55, bottom: 30 },
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
      { type: 'value', name: '耗时（天）', nameTextStyle: { color: t.muted, fontSize: 10 }, axisLabel: { color: t.muted, fontSize: 10 }, splitLine: { show: false } },
    ],
    series: [
      { name: '合并数量', type: 'bar', barMaxWidth: 25, data: props.points.map((point) => ({ value: [midpoint(point.date), observedValue(point)], itemStyle: { opacity: point.value === null ? 0.45 : 0.85 } })), itemStyle: { color: t.series[3] } },
      { name: '单条耗时', type: 'scatter', yAxisIndex: 1, symbolSize: 6, data: props.data.prSamples.map((sample) => [sample.mergedAt, sample.durationHours / 24]), itemStyle: { color: t.series[2], opacity: 0.55 }, z: 3 },
      { name: '每周中位耗时', type: 'line', yAxisIndex: 1, connectNulls: false, symbol: 'circle', symbolSize: 5, data: props.points.map((point) => { const week = props.data.prWeekly.find((item) => item.start === point.date); return [midpoint(point.date), week?.medianHours == null ? null : week.medianHours / 24] }), lineStyle: { color: t.series[0], width: 2 }, itemStyle: { color: t.series[0] }, z: 4 },
    ],
  }
})
</script>

<template><EChart :option="option" :height="height" /></template>
