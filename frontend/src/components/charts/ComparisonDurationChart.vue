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
  return {
    animation: false,
    grid: { left: 110, right: 28, top: 12, bottom: 42 },
    legend: {
      bottom: 0, left: 0, icon: 'roundRect', itemWidth: 8, itemHeight: 8, itemGap: 16,
      textStyle: { color: t.muted, fontSize: 11, fontFamily },
      data: ['Issue 关闭 P50', 'PR 合并 P50'],
    },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      backgroundColor: t.panel, borderColor: t.border, borderWidth: 1, padding: [9, 11],
      textStyle: { color: t.ink, fontSize: 11.5, fontFamily },
      extraCssText: `border-radius:8px;box-shadow:${t.dark ? '0 8px 24px rgba(0,0,0,.5)' : '0 6px 18px rgba(0,0,0,.12)'};`,
      formatter: (params: unknown) => {
        const rows = params as { dataIndex: number; axisValue: string }[]
        const item = props.items[rows[0]?.dataIndex]
        if (!item) return ''
        const value = (name: string, days: number | null, sample: number) =>
          `<div style="display:flex;justify-content:space-between;gap:18px"><span>${name}</span><b>${days === null ? '—' : `${days.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 天`} · n=${sample}</b></div>`
        return `<div style="color:${t.muted};font-size:10.5px;margin-bottom:4px">${item.label}</div>${value('Issue 关闭 P50', item.issueP50, item.issueSample)}${value('PR 合并 P50', item.prP50, item.prSample)}`
      },
    },
    xAxis: {
      type: 'value', min: 0, name: '天', nameLocation: 'end', nameTextStyle: { color: t.muted, fontSize: 10 },
      axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.muted, fontSize: 10, fontFamily: MONO },
      splitLine: { lineStyle: { color: t.grid } },
    },
    yAxis: {
      type: 'category', inverse: true, data: props.items.map((item) => item.label),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: t.muted, fontSize: 10.5, fontFamily, width: 96, overflow: 'truncate' },
    },
    series: [
      {
        name: 'Issue 关闭 P50', type: 'bar', barMaxWidth: 13, barGap: '24%',
        data: props.items.map((item) => item.issueP50),
        itemStyle: { color: t.series[1], borderRadius: [0, 3, 3, 0] },
      },
      {
        name: 'PR 合并 P50', type: 'bar', barMaxWidth: 13,
        data: props.items.map((item) => item.prP50),
        itemStyle: { color: t.series[2], borderRadius: [0, 3, 3, 0] },
      },
    ],
  }
})
</script>

<template>
  <EChart :option="option" :height="height" />
</template>
