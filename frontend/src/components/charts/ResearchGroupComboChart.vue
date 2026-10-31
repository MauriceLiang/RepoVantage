<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { fontFamily, MONO, chartTheme } from './theme'

interface ResearchGroupItem {
  label: string
  repositoryCount: number
  issueSampleSize: number
  medianCloseDays: number | null
}

const props = withDefaults(defineProps<{ groups: ResearchGroupItem[]; height?: number }>(), { height: 240 })
const ui = useUiStore()
const option = computed<EChartsOption>(() => {
  const t = chartTheme(ui.isDark)
  const tooltip = (data: unknown) => {
    const name = (data as { name?: string }).name
    const item = props.groups.find((group) => group.label === name)
    if (!item) return ''
    const median = item.medianCloseDays === null || item.medianCloseDays === undefined
      ? '—'
      : `${item.medianCloseDays.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 天`
    return `<div style="font-family:${fontFamily};font-size:11px;margin-bottom:4px">${item.label}</div><div>组内仓库：<b>${item.repositoryCount}</b></div><div>有效 Issue 样本：<b>${item.issueSampleSize}</b> 个仓库</div><div>Issue P50：<b>${median}</b></div>`
  }
  return {
    animation: false,
    grid: { left: 104, right: 18, top: 38, bottom: 46 },
    tooltip: {
      trigger: 'item', backgroundColor: t.panel, borderColor: t.border, borderWidth: 1, padding: [9, 11],
      textStyle: { color: t.ink, fontSize: 11.5, fontFamily },
      extraCssText: `border-radius:8px;box-shadow:${t.dark ? '0 8px 24px rgba(0,0,0,.5)' : '0 6px 18px rgba(0,0,0,.12)'};`,
      formatter: (params: unknown) => tooltip((params as { data?: unknown }).data),
    },
    xAxis: [
      {
        type: 'value', min: 0, position: 'bottom', name: '有效仓库数', nameLocation: 'middle', nameGap: 26,
        nameTextStyle: { color: t.muted, fontSize: 10 },
        axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.muted, fontSize: 9.5, fontFamily: MONO },
        splitLine: { lineStyle: { color: t.grid } },
      },
      {
        type: 'value', min: 0, position: 'top', name: 'Issue P50（天）', nameLocation: 'middle', nameGap: 24,
        nameTextStyle: { color: t.muted, fontSize: 10 },
        axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.muted, fontSize: 9.5, fontFamily: MONO },
        splitLine: { show: false },
      },
    ],
    yAxis: {
      type: 'category', inverse: true, data: props.groups.map((group) => group.label),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: t.muted, fontSize: 10.5, fontFamily, width: 92, overflow: 'truncate' },
    },
    series: [
      {
        name: '有效 Issue 样本仓库数', type: 'bar', xAxisIndex: 0, yAxisIndex: 0, barMaxWidth: 12,
        data: props.groups.map((group) => ({
          name: group.label,
          value: group.issueSampleSize,
        })),
        itemStyle: { color: t.series[0], borderRadius: [0, 3, 3, 0] },
      },
      {
        name: 'Issue P50', type: 'scatter', xAxisIndex: 1, yAxisIndex: 0, symbolSize: 9,
        data: props.groups.filter((group) => group.medianCloseDays !== null).map((group) => ({
          name: group.label,
          value: [group.medianCloseDays, group.label],
        })),
        itemStyle: { color: t.series[2], borderColor: t.panel, borderWidth: 1.5 },
        z: 3,
      },
    ],
  }
})
</script>

<template>
  <EChart :option="option" :height="height" />
</template>
