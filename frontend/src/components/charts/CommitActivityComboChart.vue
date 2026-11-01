<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import type { RepositoryChartData, TimePoint } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { comboTooltip, observedValue } from './comboHelpers'
import { chartTheme, fontFamily, MONO } from './theme'

const props = withDefaults(defineProps<{ points: TimePoint[]; weeks: RepositoryChartData['commitWeekly']; height?: number }>(), { height: 260 })
const emit = defineEmits<{ select: [index: number] }>()
const ui = useUiStore()
const option = computed<EChartsOption>(() => {
  const t = chartTheme(ui.isDark)
  const weeks = new Map(props.weeks.map((week) => [week.start, week]))
  return {
    animation: false,
    grid: { left: 44, right: 45, top: 55, bottom: 30 },
    legend: { top: 0, left: 0, data: ['每周提交', '活跃账号'], textStyle: { color: t.muted, fontSize: 10.5, fontFamily }, itemWidth: 9, itemHeight: 8 },
    tooltip: { ...comboTooltip(t), trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: t.border } }, formatter: (params: unknown) => {
      const rows = params as { dataIndex: number }[]
      const index = rows[0]?.dataIndex
      const point = props.points[index]
      const week = point ? weeks.get(point.date) : undefined
      if (!point) return ''
      const commits = observedValue(point)
      const partial = point.value === null || point.completeWeek !== true
      return `<div>${point.date} 起的 UTC 周${partial ? ' · 覆盖不完整' : ''}</div><div>提交：<b>${commits ?? '—'}</b></div><div>已识别活跃账号：<b>${week?.activeAuthors ?? '—'}</b></div><div style="color:${t.muted};font-size:10px">未关联账号的提交：${week?.unidentifiedCommits ?? '—'}</div>`
    } },
    xAxis: { type: 'category', boundaryGap: false, data: props.points.map((point) => point.date), axisLine: { lineStyle: { color: t.border } }, axisTick: { show: false }, axisLabel: { color: t.muted, fontFamily: MONO, fontSize: 10, formatter: (value: string) => value.slice(5), hideOverlap: true } },
    yAxis: [
      { type: 'value', name: '提交', minInterval: 1, nameTextStyle: { color: t.muted, fontSize: 10 }, axisLabel: { color: t.muted, fontSize: 10 }, splitLine: { lineStyle: { color: t.grid } } },
      { type: 'value', name: '账号', minInterval: 1, nameTextStyle: { color: t.muted, fontSize: 10 }, axisLabel: { color: t.muted, fontSize: 10 }, splitLine: { show: false } },
    ],
    series: [
      { name: '每周提交', type: 'line', data: props.points.map(observedValue), connectNulls: false, symbol: 'circle', symbolSize: 5, lineStyle: { color: t.series[0], width: 2 }, itemStyle: { color: t.series[0] }, areaStyle: { color: t.series[0], opacity: 0.16 } },
      { name: '活跃账号', type: 'line', yAxisIndex: 1, data: props.points.map((point) => weeks.get(point.date)?.activeAuthors ?? null), connectNulls: false, symbol: 'circle', symbolSize: 5, lineStyle: { color: t.series[3], width: 2 }, itemStyle: { color: t.series[3] } },
    ],
  }
})
</script>

<template>
  <EChart :option="option" :height="height" @select="(payload) => emit('select', payload.dataIndex)" />
</template>
