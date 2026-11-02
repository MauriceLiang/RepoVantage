<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import type { RepositoryChartData, TimePoint } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { accountLabel, comboTooltip, escapeHtml, observedValue } from './comboHelpers'
import { chartTheme, fontFamily, MONO } from './theme'

const props = withDefaults(defineProps<{ points: TimePoint[]; data: RepositoryChartData; height?: number }>(), { height: 260 })
const emit = defineEmits<{ select: [index: number] }>()
const ui = useUiStore()
const option = computed<EChartsOption>(() => {
  const t = chartTheme(ui.isDark)
  const weeks = new Map(props.data.commitWeekly.map((week) => [week.start, week]))
  const labels = [...props.data.commitAccounts.map(accountLabel), '其他账号', '未关联账号']
  const colors = t.dark ? ['#8ab8cf', '#a79bc9', '#8cb7a1', '#cba88c', '#b99cab', '#858c98', '#555d67'] : ['#4d819b', '#8177a0', '#679884', '#b38770', '#a4798f', '#929aa5', '#c5ccd4']
  const values = (index: number) => props.points.map((point) => {
    const week = weeks.get(point.date)
    if (!week || observedValue(point) === null) return null
    const value = index < props.data.commitAccounts.length ? week.contributors[index] ?? 0 : index === props.data.commitAccounts.length ? week.otherCommits : week.unidentifiedCommits
    return { value, itemStyle: { opacity: week.complete ? 1 : 0.5 } }
  })
  const average = props.points.map((_, index) => {
    const window = props.points.slice(index - 3, index + 1)
    return window.length === 4 && window.every((point) => point.value !== null && point.completeWeek === true && point.quality === 'ready')
      ? window.reduce((sum, point) => sum + (point.value ?? 0), 0) / 4 : null
  })
  return {
    animation: false, grid: { left: 44, right: 18, top: 55, bottom: 30 },
    legend: { type: 'scroll', top: 0, left: 0, right: 0, data: [...labels, '4 周均值'], textStyle: { color: t.muted, fontSize: 10, fontFamily }, itemWidth: 8, itemHeight: 8 },
    tooltip: { ...comboTooltip(t), trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: t.border } }, formatter: (params: unknown) => {
      const rows = params as { dataIndex: number; seriesName: string; value: number | { value: number } | null }[]
      const point = props.points[rows[0]?.dataIndex]
      if (!point) return ''
      const week = weeks.get(point.date)
      const entries = rows.filter((row) => row.seriesName !== '4 周均值').map((row) => {
        const value = typeof row.value === 'object' && row.value !== null ? row.value.value : row.value
        return value ? `<div>${escapeHtml(row.seriesName)}：<b>${value}</b></div>` : ''
      }).join('')
      const avg = average[rows[0]?.dataIndex]
      return `<div>${point.date} 起的 UTC 周${week?.complete ? '' : ' · 已观察样本'}</div>${entries}<div>合计：<b>${observedValue(point) ?? '—'}</b> 次</div><div>4 周均值：<b>${avg == null ? '—' : avg.toFixed(1)}</b></div>`
    } },
    xAxis: { type: 'category', data: props.points.map((point) => point.date), axisLine: { lineStyle: { color: t.border } }, axisTick: { show: false }, axisLabel: { color: t.muted, fontFamily: MONO, fontSize: 10, formatter: (value: string) => value.slice(5), hideOverlap: true } },
    yAxis: { type: 'value', minInterval: 1, name: '提交', nameTextStyle: { color: t.muted, fontSize: 10 }, axisLabel: { color: t.muted, fontSize: 10 }, splitLine: { lineStyle: { color: t.grid } } },
    series: [
      ...labels.map((label, index) => ({ name: label, type: 'bar' as const, stack: 'contributors', barMaxWidth: 24, data: values(index), itemStyle: { color: colors[index] } })),
      { name: '4 周均值', type: 'line', data: average, connectNulls: false, symbol: 'circle', symbolSize: 5, lineStyle: { color: t.ink, width: 2 }, itemStyle: { color: t.ink }, z: 5 },
    ],
  }
})
</script>

<template>
  <EChart :option="option" :height="height" @select="(payload) => emit('select', payload.dataIndex)" />
</template>
