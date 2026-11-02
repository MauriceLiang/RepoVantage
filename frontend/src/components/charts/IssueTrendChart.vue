<script setup lang="ts">
import { computed } from 'vue'
import type { CustomSeriesRenderItem, EChartsOption } from 'echarts'
import type { Coverage, NamedSeries } from '@/services/types'
import { buildIssueTrend } from '@/lib/issueTrend'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { comboTooltip, escapeHtml } from './comboHelpers'
import { chartTheme, fontFamily, MONO } from './theme'

const props = withDefaults(defineProps<{
  series: NamedSeries[]
  coverage: Coverage['state']
  windowStart: string | null
  windowEnd: string | null
  height?: number
}>(), { height: 310 })
const ui = useUiStore()
const rows = computed(() => buildIssueTrend(props.series, props.coverage, props.windowStart, props.windowEnd))

const option = computed<EChartsOption>(() => {
  const t = chartTheme(ui.isDark)
  const differenceColor = t.dark ? '#bb9ef5' : '#7054b5'
  const segments = rows.value.slice(0, -1).flatMap((row, index) => {
    const next = rows.value[index + 1]
    return row.difference === null || next.difference === null ? [] : [[index, row.difference, next.difference]]
  })
  const renderArea: CustomSeriesRenderItem = (_params, api) => {
    const index = Number(api.value(0)), left = Number(api.value(1)), right = Number(api.value(2))
    const p0 = api.coord([index, left]), p1 = api.coord([index + 1, right])
    const z0 = api.coord([index, 0]), z1 = api.coord([index + 1, 0])
    const polygon = (points: number[][], positive: boolean) => ({ type: 'polygon' as const, shape: { points }, style: { fill: positive ? t.series[0] : t.series[3], opacity: 0.11 } })
    if (left * right < 0) {
      // 差值跨过零线时分别填充两侧，避免将下降区画成上升区。
      const ratio = Math.abs(left) / (Math.abs(left) + Math.abs(right))
      const crossing = [p0[0] + (p1[0] - p0[0]) * ratio, z0[1]]
      return { type: 'group', children: [polygon([p0, z0, crossing], left > 0), polygon([crossing, z1, p1], right > 0)] }
    }
    return polygon([p0, p1, z1, z0], (left || right) >= 0)
  }

  return {
    animation: false,
    grid: { left: 48, right: 18, top: 55, bottom: 30 },
    legend: {
      type: 'scroll', top: 0, left: 0, right: 0,
      data: [{ name: '新增 Issue', icon: 'roundRect' }, { name: '关闭 Issue', icon: 'roundRect' }, { name: '新增 − 关闭', icon: 'circle' }],
      textStyle: { color: t.muted, fontSize: 10.5, fontFamily }, itemWidth: 10, itemHeight: 8,
    },
    tooltip: {
      ...comboTooltip(t), trigger: 'axis', confine: true, axisPointer: { type: 'line', lineStyle: { color: t.border } },
      formatter: (params: unknown) => {
        const items = (params as { dataIndex: number; seriesName: string; seriesType: string }[]).filter((item) => item.seriesType !== 'custom')
        const row = rows.value[items[0]?.dataIndex]
        if (!row) return ''
        const names = new Set(items.map((item) => item.seriesName))
        const count = (item: typeof row.added) => item.value === null ? '—' : `${item.value} 个${item.complete ? '' : '（已观察）'}`
        const difference = row.difference === null ? '—（覆盖不完整）' : `${row.difference > 0 ? '+' : ''}${row.difference} 个`
        return `<div>${escapeHtml(row.date)} 起的 UTC 周</div>` +
          (names.has('新增 Issue') ? `<div>新增：<b>${count(row.added)}</b></div>` : '') +
          (names.has('关闭 Issue') ? `<div>关闭：<b>${count(row.resolved)}</b></div>` : '') +
          (names.has('新增 − 关闭') ? `<div>新增 − 关闭：<b>${difference}</b></div>` : '')
      },
    },
    xAxis: { type: 'category', data: rows.value.map((row) => row.date), boundaryGap: true, axisLine: { onZero: false, lineStyle: { color: t.border } }, axisTick: { show: false }, axisLabel: { color: t.muted, fontFamily: MONO, fontSize: 10, formatter: (value: string) => value.slice(5), hideOverlap: true } },
    yAxis: { type: 'value', minInterval: 1, name: '数量 / 差值（个）', nameTextStyle: { color: t.muted, fontSize: 10 }, axisLabel: { color: t.muted, fontSize: 10 }, splitLine: { lineStyle: { color: t.grid } } },
    series: [
      { name: '新增 − 关闭', type: 'custom', renderItem: renderArea, data: segments, itemStyle: { color: differenceColor }, silent: true, tooltip: { show: false }, z: 1 },
      { name: '新增 Issue', type: 'bar', barMaxWidth: 19, barGap: '20%', itemStyle: { color: t.series[0], borderRadius: [3, 3, 0, 0] }, data: rows.value.map((row) => ({ value: row.added.value, itemStyle: { opacity: row.added.complete ? 1 : 0.5 } })), z: 2 },
      { name: '关闭 Issue', type: 'bar', barMaxWidth: 19, itemStyle: { color: t.series[3], borderRadius: [3, 3, 0, 0] }, data: rows.value.map((row) => ({ value: row.resolved.value, itemStyle: { opacity: row.resolved.complete ? 1 : 0.5 } })), z: 2 },
      { name: '新增 − 关闭', type: 'line', data: rows.value.map((row) => row.difference), connectNulls: false, symbol: 'circle', symbolSize: 6, lineStyle: { color: differenceColor, width: 2.5 }, itemStyle: { color: differenceColor }, markLine: { silent: true, symbol: 'none', label: { show: false }, lineStyle: { color: t.border, width: 1.3, type: 'solid' }, data: [{ yAxis: 0 }] }, z: 4 },
    ],
  }
})
</script>

<template>
  <EChart :option="option" :height="height" data-testid="issue-trend-chart" />
</template>
