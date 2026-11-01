<script setup lang="ts">
import { computed } from 'vue'
import type { CustomSeriesRenderItem, EChartsOption } from 'echarts'
import type { NamedSeries } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { comboTooltip, observedValue } from './comboHelpers'
import { chartTheme, fontFamily, MONO } from './theme'

const props = withDefaults(defineProps<{ series: NamedSeries[]; height?: number }>(), { height: 250 })
const ui = useUiStore()
const option = computed<EChartsOption>(() => {
  const t = chartTheme(ui.isDark)
  const opened = props.series.find((series) => series.key === 'opened' || series.key === 'created')?.points ?? []
  const closed = props.series.find((series) => series.key === 'closed')?.points ?? []
  const dates = [...new Set([...opened, ...closed].map((point) => point.date))].sort()
  const openedMap = new Map(opened.map((point) => [point.date, point]))
  const closedMap = new Map(closed.map((point) => [point.date, point]))
  const pairs = dates.map((date) => [observedValue(openedMap.get(date)), observedValue(closedMap.get(date))] as const)
  const segments = pairs.slice(0, -1).flatMap(([a, b], index) => {
    const [c, d] = pairs[index + 1]
    return a === null || b === null || c === null || d === null ? [] : [[index, a, b, c, d]]
  })
  const renderItem: CustomSeriesRenderItem = (_params, api) => {
    const index = Number(api.value(0))
    const a = Number(api.value(1)), b = Number(api.value(2)), c = Number(api.value(3)), d = Number(api.value(4))
    const p0 = api.coord([index, a]), q0 = api.coord([index, b])
    const p1 = api.coord([index + 1, c]), q1 = api.coord([index + 1, d])
    const color = (difference: number) => difference >= 0 ? t.series[0] : t.series[3]
    const polygon = (points: number[][], difference: number) => ({ type: 'polygon' as const, shape: { points }, style: { fill: color(difference), opacity: 0.16 } })
    const left = a - b, right = c - d
    if (left * right < 0) {
      // Split at the linear crossing so each side of the gap uses the color of
      // the series that is actually higher, rather than filling across the lines.
      const ratio = Math.abs(left) / (Math.abs(left) + Math.abs(right))
      const cross = [p0[0] + (p1[0] - p0[0]) * ratio, p0[1] + (p1[1] - p0[1]) * ratio]
      return { type: 'group', children: [polygon([p0, q0, cross], left), polygon([cross, p1, q1], right)] }
    }
    return polygon([p0, p1, q1, q0], left || right)
  }
  return {
    animation: false, grid: { left: 44, right: 18, top: 55, bottom: 30 },
    legend: { top: 0, left: 0, selectedMode: false, data: ['新增', '关闭'], textStyle: { color: t.muted, fontSize: 10.5, fontFamily }, itemWidth: 10, itemHeight: 8 },
    tooltip: { ...comboTooltip(t), trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: t.border } }, formatter: (params: unknown) => {
      const index = (params as { dataIndex: number }[])[0]?.dataIndex
      const pair = pairs[index]
      if (!pair) return ''
      const [a, b] = pair
      const partial = openedMap.get(dates[index])?.value === null || closedMap.get(dates[index])?.value === null
      return `<div>${dates[index]} 起的 UTC 周${partial ? ' · 已观察样本' : ''}</div><div>新增：<b>${a ?? '—'}</b></div><div>关闭：<b>${b ?? '—'}</b></div><div>新增 − 关闭：<b>${a === null || b === null ? '—' : a - b}</b></div>`
    } },
    xAxis: { type: 'category', boundaryGap: false, data: dates, axisLine: { lineStyle: { color: t.border } }, axisTick: { show: false }, axisLabel: { color: t.muted, fontFamily: MONO, fontSize: 10, formatter: (value: string) => value.slice(5), hideOverlap: true } },
    yAxis: { type: 'value', minInterval: 1, name: 'Issue', nameTextStyle: { color: t.muted, fontSize: 10 }, axisLabel: { color: t.muted, fontSize: 10 }, splitLine: { lineStyle: { color: t.grid } } },
    series: [
      { type: 'custom', name: '差值区域', renderItem, data: segments, silent: true, tooltip: { show: false }, z: 1 },
      { name: '新增', type: 'line', data: pairs.map((pair) => pair[0]), connectNulls: false, symbol: 'circle', symbolSize: 5, lineStyle: { color: t.series[0], width: 2 }, itemStyle: { color: t.series[0] }, z: 3 },
      { name: '关闭', type: 'line', data: pairs.map((pair) => pair[1]), connectNulls: false, symbol: 'circle', symbolSize: 5, lineStyle: { color: t.series[3], width: 2 }, itemStyle: { color: t.series[3] }, z: 3 },
    ],
  }
})
</script>

<template>
  <EChart :option="option" :height="height" />
</template>
