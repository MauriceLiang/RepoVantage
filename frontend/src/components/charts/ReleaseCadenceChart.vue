<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { fontFamily, MONO, chartTheme } from './theme'

interface ReleaseCadencePoint {
  tag: string
  date: string
  days: number
}

const props = withDefaults(defineProps<{ items: ReleaseCadencePoint[]; median: number | null; height?: number }>(), { height: 280 })
const emit = defineEmits<{ select: [tag: string] }>()
const ui = useUiStore()
const sorted = computed(() => [...props.items].sort((a, b) => a.date.localeCompare(b.date)))
const option = computed<EChartsOption>(() => {
  const t = chartTheme(ui.isDark)
  const escape = (value: string) => value.replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]!)
  return {
    animation: false,
    grid: { left: 48, right: 18, top: 20, bottom: 34 },
    tooltip: {
      trigger: 'item', backgroundColor: t.panel, borderColor: t.border, borderWidth: 1, padding: [9, 11],
      textStyle: { color: t.ink, fontSize: 11.5, fontFamily },
      extraCssText: `border-radius:8px;box-shadow:${t.dark ? '0 8px 24px rgba(0,0,0,.5)' : '0 6px 18px rgba(0,0,0,.12)'};`,
      formatter: (params: unknown) => {
        const data = (params as { data: ReleaseCadencePoint }).data
        return `<div style="font-family:${MONO};font-size:11px">${escape(data.tag)}</div><div style="color:${t.muted};font-size:10.5px;margin-top:3px">${escape(data.date)}</div><div style="margin-top:2px">距上次正式发布 <b>${data.days.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 天</b></div>`
      },
    },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: t.border } }, axisTick: { show: false },
      axisLabel: { color: t.ink, fontSize: 9.5, fontFamily: MONO, hideOverlap: true, formatter: (value: number) => {
        const date = new Date(value)
        return `${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(date.getUTCDate()).padStart(2, '0')}`
      } },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value', min: 0, name: '间隔天数', nameTextStyle: { color: t.muted, fontSize: 9.5 },
      axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.muted, fontSize: 9.5, fontFamily: MONO },
      splitLine: { lineStyle: { color: t.grid } },
    },
    series: [{
      name: '相邻发布间隔', type: 'scatter', symbol: 'circle', symbolSize: 9, z: 3,
      data: sorted.value.map((item) => ({ name: item.tag, value: [item.date, item.days], ...item })),
      itemStyle: { color: t.series[0], borderColor: t.panel, borderWidth: 1.5 },
      emphasis: { scale: 1.35 },
      ...(props.median === null ? {} : {
        markLine: {
          silent: true, symbol: 'none',
          lineStyle: { color: t.series[2], type: 'dashed', width: 1.5 },
          label: { show: true, position: 'insideEndTop', color: t.series[2], fontSize: 9.5, formatter: `P50 ${props.median.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 天` },
          data: [{ yAxis: props.median }],
        },
      }),
    }],
  }
})

function select(payload: { dataIndex: number; seriesName: string }) {
  if (payload.seriesName !== '相邻发布间隔') return
  const item = sorted.value[payload.dataIndex]
  if (item) emit('select', item.tag)
}
</script>

<template>
  <EChart :option="option" :height="height" @select="select" />
</template>
