<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { fontFamily, MONO, chartTheme } from './theme'

interface ComparisonDurationItem {
  label: string
  color: string
  issueP50: number | null
  issueSample: number
  issueQuality: string
  prP50: number | null
  prSample: number
  prQuality: string
}

const props = withDefaults(defineProps<{ items: ComparisonDurationItem[]; height?: number }>(), { height: 260 })
const ui = useUiStore()
const option = computed<EChartsOption>(() => {
  const t = chartTheme(ui.isDark)
  const categories = ['Issue 关闭 P50', 'PR 合并 P50']
  const escapeHtml = (value: string) => value.replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]!)
  const formatDays = (value: number | null, sample: number, quality: string) => value === null
    ? `— · 有效样本 n=${sample}`
    : `${value.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 天 · n=${sample}${quality === 'partial' ? ' · 部分覆盖' : ''}`
  const baseline = props.items[0]
  const differenceFromBaseline = (value: number | null, baselineValue: number | null, partial: boolean) => {
    if (value === null || baselineValue === null) return '差值不可用'
    const difference = value - baselineValue
    if (difference === 0) return '与参照相同'
    const percent = baselineValue === 0 ? null : Math.abs(difference / baselineValue * 100)
    const direction = difference > 0 ? '较慢' : '较快'
    return `${partial ? '已观察样本' : ''}比参照${direction} ${Math.abs(difference).toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 天${percent === null ? '' : `（${percent.toLocaleString('zh-CN', { maximumFractionDigits: 1 })}%）`}${partial ? ' · 部分覆盖' : ''}`
  }
  return {
    animation: false,
    grid: { left: 142, right: 30, top: 16, bottom: 28 },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      backgroundColor: t.panel, borderColor: t.border, borderWidth: 1, padding: [9, 11],
      textStyle: { color: t.ink, fontSize: 11.5, fontFamily },
      extraCssText: `border-radius:8px;box-shadow:${t.dark ? '0 8px 24px rgba(0,0,0,.5)' : '0 6px 18px rgba(0,0,0,.12)'};`,
      formatter: (params: unknown) => {
        const points = (Array.isArray(params) ? params : [params]) as { seriesName?: string; dataIndex?: number; value?: number | null }[]
        const metricIndex = points[0]?.dataIndex
        if (metricIndex === undefined) return ''
        const metricName = categories[metricIndex]
        return `<div style="color:${t.muted};font-size:10.5px;margin-bottom:5px">${metricName}</div>${props.items.map((item) => {
          const isIssue = metricIndex === 0
          const value = isIssue ? item.issueP50 : item.prP50
          const sample = isIssue ? item.issueSample : item.prSample
          const quality = isIssue ? item.issueQuality : item.prQuality
          const baselineValue = isIssue ? baseline?.issueP50 ?? null : baseline?.prP50 ?? null
          const baselineQuality = isIssue ? baseline?.issueQuality : baseline?.prQuality
          const detail = value === null ? '' : `<div style="color:${t.muted};font-size:10.5px;margin-left:12px">${differenceFromBaseline(value, baselineValue, quality === 'partial' || baselineQuality === 'partial')}</div>`
          return `<div><span style="color:${item.color}">●</span> ${escapeHtml(item.label)}：<b>${formatDays(value, sample, quality)}</b>${detail}</div>`
        }).join('')}`
      },
    },
    xAxis: {
      type: 'value', min: 0, name: '天', nameLocation: 'end', nameTextStyle: { color: t.muted, fontSize: 10 },
      axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.muted, fontSize: 10, fontFamily: MONO },
      splitLine: { lineStyle: { color: t.grid } },
    },
    yAxis: {
      type: 'category', inverse: true, data: categories,
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: t.ink, fontSize: 11.5, fontFamily, width: 128, overflow: 'break' },
    },
    series: [
      ...props.items.map((item) => ({
        name: item.label,
        type: 'bar' as const,
        barMaxWidth: 18,
        barMinHeight: 3,
        itemStyle: { color: item.color, borderRadius: [0, 3, 3, 0] },
        emphasis: { focus: 'series' as const },
        data: [
          { value: item.issueP50, itemStyle: { opacity: item.issueQuality === 'partial' ? 0.6 : 1 } },
          { value: item.prP50, itemStyle: { opacity: item.prQuality === 'partial' ? 0.6 : 1 } },
        ],
      })),
    ],
  }
})
</script>

<template>
  <EChart :option="option" :height="height" />
</template>
