<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { comboTooltip, escapeHtml } from './comboHelpers'
import { fontFamily, MONO, chartTheme } from './theme'

interface ReleaseCadencePoint {
  tag: string
  date: string
  days: number
  previousDate: string | null
  commitCount: number | null
  reason: string | null
}

const props = withDefaults(defineProps<{ items: ReleaseCadencePoint[]; height?: number }>(), { height: 280 })
const emit = defineEmits<{ select: [tag: string] }>()
const ui = useUiStore()
const sorted = computed(() => [...props.items].sort((a, b) => a.date.localeCompare(b.date)))
const option = computed<EChartsOption>(() => {
  const t = chartTheme(ui.isDark)
  const start = sorted.value.length > 20 ? (sorted.value.length - 20) / sorted.value.length * 100 : 0
  return {
    animation: false,
    grid: { left: 46, right: 48, top: 55, bottom: 48 },
    legend: { top: 0, left: 0, data: ['发布间隔', '期间提交'], textStyle: { color: t.muted, fontSize: 10, fontFamily }, itemWidth: 10, itemHeight: 8 },
    tooltip: { ...comboTooltip(t), trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: t.border } }, formatter: (params: unknown) => {
      const index = (params as { dataIndex: number }[])[0]?.dataIndex
      const item = sorted.value[index]
      if (!item) return ''
      return `<div>${escapeHtml(item.tag)}</div><div>${escapeHtml(item.previousDate ?? '—')} → ${escapeHtml(item.date)}</div><div>发布间隔：<b>${item.days.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 天</b></div><div>期间提交：<b>${item.commitCount ?? '—'}</b>${item.commitCount === null ? ` · ${escapeHtml(item.reason ?? '覆盖不完整')}` : ''}</div>`
    } },
    xAxis: { type: 'category', data: sorted.value.map((_, index) => index), axisLine: { lineStyle: { color: t.border } }, axisTick: { show: false }, axisLabel: { color: t.ink, fontSize: 9.5, fontFamily: MONO, hideOverlap: true, formatter: (value: string) => sorted.value[Number(value)]?.date.slice(5, 10) ?? '' } },
    yAxis: [
      { type: 'value', min: 0, name: '间隔（天）', nameTextStyle: { color: t.muted, fontSize: 9.5 }, axisLabel: { color: t.muted, fontSize: 9.5 }, splitLine: { lineStyle: { color: t.grid } } },
      { type: 'value', min: 0, minInterval: 1, name: '提交数', nameTextStyle: { color: t.muted, fontSize: 9.5 }, axisLabel: { color: t.muted, fontSize: 9.5 }, splitLine: { show: false } },
    ],
    dataZoom: sorted.value.length > 20 ? [
      { type: 'inside', xAxisIndex: 0, start, end: 100 },
      { type: 'slider', xAxisIndex: 0, start, end: 100, height: 12, bottom: 0, showDetail: false, showDataShadow: false, brushSelect: false, borderColor: t.border, backgroundColor: t.soft, fillerColor: t.dark ? 'rgba(242,148,194,.2)' : 'rgba(206,63,124,.16)' },
    ] : undefined,
    series: [
      { name: '发布间隔', type: 'bar', data: sorted.value.map((item) => item.days), barMaxWidth: 25, itemStyle: { color: t.series[0], borderRadius: [3, 3, 0, 0] } },
      { name: '期间提交', type: 'line', yAxisIndex: 1, data: sorted.value.map((item) => item.commitCount), connectNulls: false, symbol: 'circle', symbolSize: 6, lineStyle: { color: t.series[3], width: 2 }, itemStyle: { color: t.series[3] }, z: 4 },
    ],
  }
})
function select(payload: { dataIndex: number; seriesName: string }) {
  if (payload.seriesName !== '发布间隔' && payload.seriesName !== '期间提交') return
  const item = sorted.value[payload.dataIndex]
  if (item) emit('select', item.tag)
}
</script>

<template>
  <EChart :option="option" :height="height" @select="select" />
</template>
