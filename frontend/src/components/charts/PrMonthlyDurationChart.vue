<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import type { PrDurationPeriod } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { comboTooltip } from './comboHelpers'
import { chartTheme, fontFamily, MONO } from './theme'

export type PrDurationGrain = 'weekly' | 'biweekly' | 'monthly'
const props = withDefaults(defineProps<{
  periods: PrDurationPeriod[]
  grain: PrDurationGrain
  selectedPeriodStart?: string | null
  height?: number
}>(), { selectedPeriodStart: null, height: 200 })
const emit = defineEmits<{ select: [period: PrDurationPeriod] }>()
const ui = useUiStore()
const labels = ['<1 天', '1–3 天', '3–7 天', '7–30 天', '≥30 天']

function dateLabel(period: PrDurationPeriod) {
  if (props.grain === 'monthly') return period.start.slice(0, 7)
  if (props.grain === 'weekly') return period.start.slice(5, 10)
  const lastDay = new Date(Date.parse(period.end) - 1).toISOString().slice(5, 10)
  return `${period.start.slice(5, 10)}–${lastDay}`
}

function selectPeriod(payload: { dataIndex: number; seriesName: string }) {
  if (!labels.includes(payload.seriesName)) return
  const period = props.periods[payload.dataIndex]
  if (period) emit('select', period)
}

const option = computed<EChartsOption>(() => {
  const t = chartTheme(ui.isDark)
  const colors = t.dark ? ['#72b7a0', '#91b0d6', '#b5a7d5', '#e4bb84', '#ef8d87'] : ['#4a937b', '#678fba', '#8877ac', '#c99a59', '#cf716b']
  const topBucket = props.periods.map((period) => {
    for (let index = period.counts.length - 1; index >= 0; index -= 1) {
      if ((period.counts[index] ?? 0) > 0) return index
    }
    return -1
  })
  return {
    animation: false, grid: { left: 43, right: 46, top: 54, bottom: 34 },
    legend: { type: 'scroll', left: 0, right: 0, top: 0, data: [...labels, '中位耗时'], textStyle: { color: t.muted, fontSize: 9.5, fontFamily }, itemWidth: 8, itemHeight: 8, itemGap: 9 },
    tooltip: { ...comboTooltip(t), trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: t.dark ? 'rgba(255,255,255,.06)' : 'rgba(30,41,59,.06)' } }, formatter: (params: unknown) => {
      const index = (params as { dataIndex: number }[])[0]?.dataIndex
      const period = props.periods[index]
      if (!period) return ''
      const counts = labels.map((label, i) => `<div>${label}：<b>${period.complete || period.validSamples ? period.counts[i] ?? 0 : '—'}</b></div>`).join('')
      const status = period.complete ? '完整覆盖' : '已观察样本，覆盖不完整'
      return `<div>UTC ${period.start.slice(0, 10)} 至 ${period.end.slice(0, 10)}（结束时间不含）</div><div>${status} · n=${period.validSamples}</div>${counts}<div>中位耗时：<b>${period.medianHours === null ? '—' : `${(period.medianHours / 24).toFixed(1)} 天`}</b></div>`
    } },
    xAxis: { type: 'category', data: props.periods.map(dateLabel), axisLine: { lineStyle: { color: t.border } }, axisTick: { show: false }, axisLabel: { color: t.muted, fontFamily: MONO, fontSize: 9, hideOverlap: true } },
    yAxis: [
      { type: 'value', name: 'PR 数', minInterval: 1, nameTextStyle: { color: t.muted, fontSize: 9 }, axisLabel: { color: t.muted, fontSize: 9 }, splitLine: { lineStyle: { color: t.grid } } },
      { type: 'value', name: '中位天数', min: 0, nameTextStyle: { color: t.muted, fontSize: 9 }, axisLabel: { color: t.muted, fontSize: 9 }, splitLine: { show: false } },
    ],
    series: [
      ...labels.map((label, index) => ({
        name: label, type: 'bar' as const, stack: 'duration', barMaxWidth: 32,
        itemStyle: { color: colors[index] },
        emphasis: { focus: 'series' as const, itemStyle: { borderColor: t.ink, borderWidth: 1 } },
        data: props.periods.map((period, periodIndex) => {
          const hasSamples = period.complete || period.validSamples > 0
          if (!hasSamples) return null
          const selected = period.start === props.selectedPeriodStart
          const isTop = topBucket[periodIndex] === index
          return {
            value: period.counts[index] ?? 0,
            itemStyle: selected ? { borderColor: t.ink, borderWidth: 1.5 } : undefined,
            label: isTop ? {
              show: true, position: 'top' as const, distance: 3,
              color: t.ink, fontSize: 9, fontFamily: MONO,
              formatter: `n=${period.validSamples}${period.complete ? '' : '*'}`,
            } : { show: false },
          }
        }),
      })),
      {
        name: '中位耗时', type: 'line', yAxisIndex: 1, smooth: false, connectNulls: false,
        symbol: 'circle', symbolSize: 6, lineStyle: { color: t.ink, width: 2 },
        itemStyle: { color: t.ink, borderColor: t.panel, borderWidth: 1 }, z: 5,
        data: props.periods.map((period) => period.medianHours === null ? null : period.medianHours / 24),
      },
    ],
  }
})
</script>

<template><EChart :option="option" :height="height" @select="selectPeriod" /></template>
