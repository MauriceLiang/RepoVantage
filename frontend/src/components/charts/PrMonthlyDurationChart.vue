<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import type { RepositoryChartData } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { comboTooltip } from './comboHelpers'
import { chartTheme, fontFamily, MONO } from './theme'

const props = withDefaults(defineProps<{ months: RepositoryChartData['prMonthly']; height?: number }>(), { height: 200 })
const ui = useUiStore()
const labels = ['<1 天', '1–3 天', '3–7 天', '7–30 天', '≥30 天']
const option = computed<EChartsOption>(() => {
  const t = chartTheme(ui.isDark)
  const colors = t.dark ? ['#72b7a0', '#91b0d6', '#b5a7d5', '#e4bb84', '#ef8d87'] : ['#4a937b', '#678fba', '#8877ac', '#c99a59', '#cf716b']
  return {
    animation: false, grid: { left: 43, right: 46, top: 55, bottom: 30 },
    legend: { type: 'scroll', left: 0, right: 0, top: 0, data: [...labels, '中位耗时'], textStyle: { color: t.muted, fontSize: 9.5, fontFamily }, itemWidth: 8, itemHeight: 8, itemGap: 9 },
    tooltip: { ...comboTooltip(t), trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: t.border } }, formatter: (params: unknown) => {
      const index = (params as { dataIndex: number }[])[0]?.dataIndex
      const month = props.months[index]
      if (!month) return ''
      const counts = labels.map((label, i) => `<div>${label}：<b>${month.complete || month.validSamples ? month.counts[i] ?? 0 : '—'}</b></div>`).join('')
      return `<div>${month.month.slice(0, 7)}${month.complete ? '' : ' · 已观察样本'}</div>${counts}<div>中位耗时：<b>${month.medianHours === null ? '—' : `${(month.medianHours / 24).toFixed(1)} 天`}</b> · n=${month.validSamples}</div>`
    } },
    xAxis: { type: 'category', data: props.months.map((month) => month.month.slice(0, 7)), axisLine: { lineStyle: { color: t.border } }, axisTick: { show: false }, axisLabel: { color: t.muted, fontFamily: MONO, fontSize: 9, hideOverlap: true } },
    yAxis: [
      { type: 'value', name: 'PR 数', minInterval: 1, nameTextStyle: { color: t.muted, fontSize: 9 }, axisLabel: { color: t.muted, fontSize: 9 }, splitLine: { lineStyle: { color: t.grid } } },
      { type: 'value', name: '中位天数', nameTextStyle: { color: t.muted, fontSize: 9 }, axisLabel: { color: t.muted, fontSize: 9 }, splitLine: { show: false } },
    ],
    series: [
      ...labels.map((label, index) => ({ name: label, type: 'bar' as const, stack: 'duration', barMaxWidth: 32, itemStyle: { color: colors[index] }, data: props.months.map((month) => month.complete || month.validSamples ? { value: month.counts[index] ?? 0, itemStyle: { opacity: month.complete ? 1 : 0.5 } } : null) })),
      { name: '中位耗时', type: 'scatter', yAxisIndex: 1, symbol: 'diamond', symbolSize: 10, data: props.months.map((month) => month.medianHours === null ? null : month.medianHours / 24), itemStyle: { color: t.ink, borderColor: t.panel, borderWidth: 1 }, z: 5 },
    ],
  }
})
</script>

<template><EChart :option="option" :height="height" /></template>
