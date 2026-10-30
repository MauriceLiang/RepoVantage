<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { fontFamily, MONO, chartTheme } from './theme'

interface QualityRow {
  field: string
  missingCount: number
  totalRecords: number
}

const props = withDefaults(defineProps<{ items: QualityRow[]; height?: number }>(), { height: 220 })
const ui = useUiStore()
const rows = computed(() => props.items.filter((item) => item.totalRecords > 0 && item.missingCount >= 0))
const option = computed<EChartsOption>(() => {
  const t = chartTheme(ui.isDark)
  const findRow = (name: string) => rows.value.find((row) => row.field === name)
  return {
    animation: false,
    grid: { left: 112, right: 18, top: 28, bottom: 26 },
    legend: {
      top: 0, left: 0, icon: 'roundRect', itemWidth: 8, itemHeight: 8, itemGap: 14,
      textStyle: { color: t.muted, fontSize: 10.5, fontFamily },
      data: ['资料已具备', '资料缺失'],
    },
    tooltip: {
      trigger: 'item', backgroundColor: t.panel, borderColor: t.border, borderWidth: 1, padding: [9, 11],
      textStyle: { color: t.ink, fontSize: 11.5, fontFamily },
      extraCssText: `border-radius:8px;box-shadow:${t.dark ? '0 8px 24px rgba(0,0,0,.5)' : '0 6px 18px rgba(0,0,0,.12)'};`,
      formatter: (params: unknown) => {
        const p = params as { name: string; seriesName: string; value: number }
        const row = findRow(p.name)
        if (!row) return ''
        const missingRate = row.missingCount / row.totalRecords * 100
        const count = p.seriesName === '资料缺失' ? row.missingCount : row.totalRecords - row.missingCount
        return `<div style="font-size:11px;margin-bottom:4px">${row.field}</div><div>${p.seriesName}仓库：<b>${count.toLocaleString('zh-CN')} / ${row.totalRecords.toLocaleString('zh-CN')}</b></div><div style="color:${t.muted};font-size:10.5px;margin-top:2px">缺失率 ${missingRate.toLocaleString('zh-CN', { maximumFractionDigits: 1 })}%</div>`
      },
    },
    xAxis: {
      type: 'value', min: 0, max: 100, axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: t.muted, fontSize: 9.5, fontFamily: MONO, formatter: (value: number) => `${value}%` },
      splitLine: { lineStyle: { color: t.grid } },
    },
    yAxis: {
      type: 'category', inverse: true, data: rows.value.map((row) => row.field),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: t.muted, fontSize: 10.5, fontFamily, width: 102, overflow: 'truncate' },
    },
    series: [
      {
        name: '资料已具备', type: 'bar', stack: 'records', barMaxWidth: 15,
        data: rows.value.map((row) => ({ name: row.field, value: row.totalRecords ? (row.totalRecords - row.missingCount) / row.totalRecords * 100 : 0 })),
        itemStyle: { color: t.series[0], borderRadius: [3, 0, 0, 3] },
      },
      {
        name: '资料缺失', type: 'bar', stack: 'records', barMaxWidth: 15,
        data: rows.value.map((row) => ({ name: row.field, value: row.totalRecords ? row.missingCount / row.totalRecords * 100 : 0 })),
        itemStyle: { color: t.series[1], borderRadius: [0, 3, 3, 0] },
      },
    ],
  }
})
</script>

<template>
  <EChart v-if="rows.length" :option="option" :height="height" />
  <p v-else class="py-6 text-center text-[12px] text-muted">后端没有返回可计算缺失率的字段记录数。</p>
</template>
