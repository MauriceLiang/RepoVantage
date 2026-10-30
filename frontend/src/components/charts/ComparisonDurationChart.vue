<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { fontFamily, MONO, chartTheme } from './theme'

interface ComparisonDurationItem {
  label: string
  issueP50: number | null
  issueSample: number
  prP50: number | null
  prSample: number
}

const props = withDefaults(defineProps<{ items: ComparisonDurationItem[]; height?: number }>(), { height: 260 })
const ui = useUiStore()
const option = computed<EChartsOption>(() => {
  const t = chartTheme(ui.isDark)
  const items = [...props.items].sort((a, b) => {
    const aGap = a.issueP50 === null || a.prP50 === null ? -1 : Math.abs(a.prP50 - a.issueP50)
    const bGap = b.issueP50 === null || b.prP50 === null ? -1 : Math.abs(b.prP50 - b.issueP50)
    return bGap - aGap || a.label.localeCompare(b.label)
  })
  const valueFor = (item: ComparisonDurationItem | undefined, metric: 'issueP50' | 'prP50', sample: 'issueSample' | 'prSample') =>
    item?.[metric] === null || item?.[metric] === undefined
      ? '—'
      : `${item[metric]!.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 天 · n=${item[sample]}`
  return {
    animation: false,
    grid: { left: 150, right: 24, top: 24, bottom: 42 },
    legend: {
      bottom: 0, left: 0, icon: 'roundRect', itemWidth: 8, itemHeight: 8, itemGap: 16,
      textStyle: { color: t.muted, fontSize: 11, fontFamily },
      data: ['Issue P50', 'PR P50'],
    },
    tooltip: {
      trigger: 'item',
      backgroundColor: t.panel, borderColor: t.border, borderWidth: 1, padding: [9, 11],
      textStyle: { color: t.ink, fontSize: 11.5, fontFamily },
      extraCssText: `border-radius:8px;box-shadow:${t.dark ? '0 8px 24px rgba(0,0,0,.5)' : '0 6px 18px rgba(0,0,0,.12)'};`,
      formatter: (params: unknown) => {
        const point = params as { data: { name?: string } }
        const item = items.find((entry) => entry.label === point.data.name)
        if (!item) return ''
        const delta = item.issueP50 === null || item.prP50 === null ? null : item.prP50 - item.issueP50
        const deltaLabel = delta === null ? '差值不可用' : `${delta > 0 ? 'PR 较慢' : delta < 0 ? 'Issue 较慢' : '耗时相同'}${delta === 0 ? '' : ` ${Math.abs(delta).toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 天`}`
        return `<div style="color:${t.muted};font-size:10.5px;margin-bottom:4px">${item.label}</div><div>Issue 关闭 P50：<b>${valueFor(item, 'issueP50', 'issueSample')}</b></div><div>PR 合并 P50：<b>${valueFor(item, 'prP50', 'prSample')}</b></div><div style="margin-top:3px;color:${t.muted}">${deltaLabel}</div>`
      },
    },
    xAxis: {
      type: 'value', min: 0, name: '天', nameLocation: 'end', nameTextStyle: { color: t.muted, fontSize: 10 },
      axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.muted, fontSize: 10, fontFamily: MONO },
      splitLine: { lineStyle: { color: t.grid } },
    },
    yAxis: {
      type: 'category', inverse: true, data: items.map((item) => item.label),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: t.muted, fontSize: 10.5, fontFamily, width: 136, overflow: 'truncate' },
    },
    series: [
      ...items.filter((item) => item.issueP50 !== null && item.prP50 !== null).map((item) => ({
        name: `${item.label} P50 差距`, type: 'line' as const, symbol: 'none', silent: true, z: 1,
        data: [
          { name: item.label, value: [item.issueP50, item.label] },
          { name: item.label, value: [item.prP50, item.label] },
        ],
        lineStyle: { color: t.border, width: 4 },
      })),
      {
        name: 'Issue P50', type: 'scatter', symbol: 'circle', symbolSize: 12, z: 3,
        data: items.filter((item) => item.issueP50 !== null).map((item) => ({ name: item.label, value: [item.issueP50, item.label] })),
        itemStyle: { color: t.series[1], borderColor: t.panel, borderWidth: 2 },
      },
      {
        name: 'PR P50', type: 'scatter', symbol: 'diamond', symbolSize: 12, z: 3,
        data: items.filter((item) => item.prP50 !== null).map((item) => ({ name: item.label, value: [item.prP50, item.label] })),
        itemStyle: { color: t.series[2], borderColor: t.panel, borderWidth: 2 },
      },
    ],
  }
})
</script>

<template>
  <EChart :option="option" :height="height" />
</template>
