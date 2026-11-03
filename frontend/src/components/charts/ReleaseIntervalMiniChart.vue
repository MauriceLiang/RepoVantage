<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { comboTooltip, escapeHtml } from './comboHelpers'
import { chartTheme, fontFamily, MONO } from './theme'

interface ReleaseIntervalPoint {
  previousTag: string
  tag: string
  previousPublishedAt: string
  publishedAt: string
  days: number
}

const props = withDefaults(defineProps<{ items: ReleaseIntervalPoint[]; height?: number }>(), { height: 112 })
const ui = useUiStore()
const median = computed(() => {
  const values = props.items.map((item) => item.days).sort((a, b) => a - b)
  if (!values.length) return null
  const middle = Math.floor(values.length / 2)
  return values.length % 2 ? values[middle] : (values[middle - 1] + values[middle]) / 2
})
const option = computed<EChartsOption>(() => {
  const t = chartTheme(ui.isDark)
  const labels = props.items.map((item) => `${item.previousPublishedAt.slice(5, 10)}→${item.publishedAt.slice(5, 10)}`)
  const highest = Math.max(0, ...props.items.map((item) => item.days))
  const max = Math.max(1, highest * 1.55)

  return {
    animation: false,
    grid: { left: 8, right: 10, top: 21, bottom: 26 },
    tooltip: {
      ...comboTooltip(t),
      trigger: 'item',
      formatter: (params: unknown) => {
        const point = params as { dataIndex: number }
        const item = props.items[point.dataIndex]
        if (!item) return ''
        const previous = item.previousTag || item.previousPublishedAt.slice(0, 10)
        const current = item.tag || item.publishedAt.slice(0, 10)
        return `<div>${escapeHtml(previous)} → ${escapeHtml(current)}</div>`
          + `<div>${escapeHtml(item.previousPublishedAt.slice(0, 10))} 至 ${escapeHtml(item.publishedAt.slice(0, 10))}</div>`
          + `<div>发布间隔：<b>${item.days.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 天</b></div>`
          + `<div>参考线：P50 ${median.value?.toLocaleString('zh-CN', { maximumFractionDigits: 1 }) ?? '—'} 天</div>`
      },
    },
    xAxis: {
      type: 'category',
      data: labels,
      axisLine: { lineStyle: { color: t.border } },
      axisTick: { show: false },
      axisLabel: { color: t.muted, fontFamily: MONO, fontSize: 8.5, hideOverlap: true, margin: 8 },
    },
    yAxis: { type: 'value', min: 0, max, show: false },
    series: [{
      name: '发布间隔',
      type: 'scatter',
      data: props.items.map((item) => item.days),
      symbol: 'circle',
      symbolSize: 9,
      itemStyle: { color: t.series[2], borderColor: t.panel, borderWidth: 1.5 },
      label: {
        show: props.items.length <= 5,
        position: 'top',
        color: t.ink,
        fontFamily,
        fontSize: 9,
        formatter: (params: unknown) => `${Number((params as { value: number }).value).toLocaleString('zh-CN', { maximumFractionDigits: 1 })}天`,
      },
      markLine: median.value === null ? undefined : {
        silent: true,
        symbol: ['none', 'none'],
        lineStyle: { color: t.ink, type: 'dashed', opacity: 0.65, width: 1 },
        label: {
          show: true,
          position: 'insideEndTop',
          color: t.muted,
          fontSize: 8.5,
          formatter: `P50 ${median.value.toLocaleString('zh-CN', { maximumFractionDigits: 1 })}天`,
        },
        data: [{ yAxis: median.value }],
      },
    }],
  }
})
</script>

<template>
  <EChart :option="option" :height="height" />
</template>
