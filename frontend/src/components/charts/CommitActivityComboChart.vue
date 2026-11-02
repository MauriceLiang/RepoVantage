<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import type { ReleaseRecord, RepositoryChartData, TimePoint } from '@/services/types'
import { buildCommitActivity } from '@/lib/commitActivity'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { comboTooltip, escapeHtml } from './comboHelpers'
import { chartTheme, fontFamily, MONO } from './theme'

const props = withDefaults(defineProps<{
  points: TimePoint[]
  weeks: RepositoryChartData['commitWeekly']
  releases: ReleaseRecord[]
  windowStart: string | null
  windowEnd: string | null
  height?: number
}>(), { height: 420 })
const emit = defineEmits<{
  select: [index: number]
  'select-releases': [payload: { date: string; releases: ReleaseRecord[] }]
}>()
const ui = useUiStore()
const rows = computed(() => buildCommitActivity(props.points, props.weeks, props.releases, props.windowStart, props.windowEnd))

const option = computed<EChartsOption>(() => {
  const t = chartTheme(ui.isDark)
  const dates = rows.value.map((row) => row.date)
  const xAxis = (gridIndex: number) => ({
    type: 'category' as const, gridIndex, data: dates, boundaryGap: true,
    axisLine: { show: gridIndex === 2, lineStyle: { color: t.border } },
    axisTick: { show: false },
    axisLabel: { show: gridIndex === 2, color: t.muted, fontFamily: MONO, fontSize: 10, formatter: (value: string) => value.slice(5), hideOverlap: true },
  })
  return {
    animation: false,
    grid: [
      { left: 52, right: 20, top: 54, height: '41%' },
      { left: 52, right: 20, top: '62%', height: '17%' },
      { left: 52, right: 20, top: '85%', height: '5%' },
    ],
    legend: { type: 'scroll', top: 0, left: 0, right: 0, data: ['每周提交', '4 周均值', '活跃账号', '正式发布'], textStyle: { color: t.muted, fontSize: 10.5, fontFamily }, itemWidth: 10, itemHeight: 8 },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    tooltip: {
      ...comboTooltip(t), trigger: 'axis', triggerOn: 'mousemove', axisPointer: { type: 'line', lineStyle: { color: t.border } },
      formatter: (params: unknown) => {
        const items = params as { dataIndex: number }[]
        const row = rows.value[items[0]?.dataIndex]
        if (!row) return ''
        const display = (value: number | null, unit: string) => value === null ? '—' : `${value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} ${unit}`
        const partial = row.complete ? '' : ' · 仅已观察样本'
        const releaseList = row.releases.slice(0, 3).map((release) => `${escapeHtml(release.identifierType === 'release_id' ? `#${release.tag}` : release.tag)}（${escapeHtml(new Date(release.publishedAt).toISOString().slice(0, 10))}）`).join('、')
        const more = row.releases.length > 3 ? ` 等 ${row.releases.length} 个` : ''
        return `<div>${escapeHtml(row.date)} 起的 UTC 周${partial}</div>` +
          `<div>提交：<b>${display(row.commits, '次')}</b></div>` +
          `<div>4 周均值：<b>${display(row.average, '次 / 周')}</b></div>` +
          `<div>已识别活跃账号：<b>${display(row.authors, '个')}</b></div>` +
          `<div>未关联账号的提交：<b>${display(row.unidentifiedCommits, '次')}</b></div>` +
          `<div>已观察正式发布：<b>${row.releases.length ? `${releaseList}${more}` : '—'}</b></div>`
      },
    },
    xAxis: [xAxis(0), xAxis(1), xAxis(2)],
    yAxis: [
      { type: 'value', gridIndex: 0, name: '提交 / 次', min: 0, minInterval: 1, nameTextStyle: { color: t.muted, fontSize: 10 }, axisLabel: { color: t.muted, fontSize: 10 }, splitLine: { lineStyle: { color: t.grid } } },
      { type: 'value', gridIndex: 1, name: '活跃账号 / 个', min: 0, minInterval: 1, nameTextStyle: { color: t.muted, fontSize: 10 }, axisLabel: { color: t.muted, fontSize: 10 }, splitLine: { lineStyle: { color: t.grid } } },
      { type: 'value', gridIndex: 2, min: 0, max: 1, name: '发布', nameLocation: 'middle', nameGap: 14, nameRotate: 0, nameTextStyle: { color: t.muted, fontSize: 10 }, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { show: false }, splitLine: { show: false } },
    ],
    series: [
      { name: '每周提交', type: 'bar', barMaxWidth: 28, itemStyle: { color: t.series[0], borderRadius: [3, 3, 0, 0] }, data: rows.value.map((row) => ({ value: row.commits, itemStyle: { opacity: row.complete ? 1 : 0.5 } })) },
      { name: '4 周均值', type: 'line', data: rows.value.map((row) => row.average), connectNulls: false, symbol: 'circle', symbolSize: 4, lineStyle: { color: t.ink, width: 2, type: 'dashed' }, itemStyle: { color: t.ink }, z: 3 },
      { name: '活跃账号', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: rows.value.map((row) => row.complete ? row.authors : null), connectNulls: false, symbol: 'circle', symbolSize: 6, lineStyle: { color: t.series[3], width: 2 }, itemStyle: { color: t.series[3] } },
      { name: '活跃账号', type: 'scatter', xAxisIndex: 1, yAxisIndex: 1, data: rows.value.map((row) => row.complete ? null : row.authors), symbolSize: 8, itemStyle: { color: t.panel, borderColor: t.series[3], borderWidth: 2 } },
      { name: '正式发布', type: 'scatter', xAxisIndex: 2, yAxisIndex: 2, symbol: 'diamond', data: rows.value.map((row) => row.releases.length ? { value: 0.5, count: row.releases.length } : null), symbolSize: 12, itemStyle: { color: t.series[2] }, label: { show: true, position: 'top', color: t.series[2], fontSize: 9, formatter: (params: unknown) => { const count = (params as { data?: { count?: number } }).data?.count ?? 0; return count > 1 ? String(count) : '' } }, z: 4 },
    ],
  }
})

function select(payload: { dataIndex: number; seriesName: string }) {
  const row = rows.value[payload.dataIndex]
  if (!row) return
  if (payload.seriesName === '正式发布') {
    if (row.releases.length) emit('select-releases', { date: row.date, releases: row.releases })
  } else {
    emit('select', row.sourceIndex)
  }
}
</script>

<template>
  <EChart :option="option" :height="height" hide-tooltip-on-select class="relative z-0" data-testid="commit-activity-chart" @select="select" />
</template>
