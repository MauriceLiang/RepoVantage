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
  const maxCommits = Math.max(0, ...rows.value.map((row) => row.commits ?? 0))
  const commitAxisMax = Math.max(1, Math.ceil(maxCommits * 1.35))
  // Release 是时间事件而非数量值，放在同一绘图区顶部预留带中，不另建子图或计数轴。
  const releaseMarkerY = commitAxisMax * 0.93
  const releaseWeeks = rows.value.filter((row) => row.releases.length > 0)

  return {
    animation: false,
    grid: { left: 58, right: 62, top: 48, bottom: 38, containLabel: true },
    legend: {
      top: 0,
      left: 0,
      data: ['每周提交', '活跃账号', '正式发布'],
      textStyle: { color: t.muted, fontSize: 10.5, fontFamily },
      itemWidth: 11,
      itemHeight: 9,
    },
    tooltip: {
      ...comboTooltip(t),
      trigger: 'axis',
      triggerOn: 'mousemove',
      axisPointer: { type: 'line', lineStyle: { color: t.border } },
      formatter: (params: unknown) => {
        const items = params as { dataIndex: number }[]
        const row = rows.value[items[0]?.dataIndex]
        if (!row) return ''
        const display = (value: number | null, unit: string) => value === null
          ? '—'
          : `${value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} ${unit}`
        const quality = row.complete ? '完整周' : '仅已观察样本，不代表完整周总量'
        const releaseList = row.releases.slice(0, 3)
          .map((release) => `${escapeHtml(release.identifierType === 'release_id' ? `#${release.tag}` : release.tag)}（${escapeHtml(new Date(release.publishedAt).toISOString().slice(0, 10))}）`)
          .join('、')
        const more = row.releases.length > 3 ? ` 等 ${row.releases.length} 个` : ''
        return `<div>${escapeHtml(row.date)} 起的 UTC 周 · ${quality}</div>`
          + `<div>提交：<b>${display(row.commits, '次')}</b></div>`
          + `<div>已识别活跃账号：<b>${display(row.authors, '个')}</b></div>`
          + `<div>未关联账号的提交：<b>${display(row.unidentifiedCommits, '次')}</b></div>`
          + `<div>正式发布：<b>${row.releases.length ? `${releaseList}${more}` : '—'}</b></div>`
      },
    },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: t.border } },
      axisTick: { show: false },
      axisLabel: {
        color: t.muted,
        fontFamily: MONO,
        fontSize: 10,
        formatter: (value: string) => value.slice(5),
        hideOverlap: true,
      },
    },
    yAxis: [
      {
        type: 'value',
        name: '提交 / 次',
        nameLocation: 'end',
        nameRotate: 0,
        nameGap: 10,
        min: 0,
        max: commitAxisMax,
        minInterval: 1,
        nameTextStyle: { color: t.muted, fontSize: 10 },
        axisLabel: { color: t.muted, fontSize: 10 },
        splitLine: { lineStyle: { color: t.grid } },
      },
      {
        type: 'value',
        name: '活跃账号 / 个',
        nameLocation: 'end',
        nameRotate: 0,
        nameGap: 10,
        position: 'right',
        min: 0,
        minInterval: 1,
        nameTextStyle: { color: t.muted, fontSize: 10 },
        axisLabel: { color: t.muted, fontSize: 10 },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '每周提交',
        type: 'line',
        data: rows.value.map((row) => row.complete ? row.commits : null),
        connectNulls: false,
        symbol: 'circle',
        symbolSize: 4,
        showSymbol: true,
        lineStyle: { color: t.series[0], width: 2.5 },
        itemStyle: { color: t.series[0] },
        areaStyle: { color: t.series[0], opacity: 0.16 },
        markLine: releaseWeeks.length ? {
          silent: true,
          symbol: ['none', 'none'],
          label: { show: false },
          lineStyle: { color: t.series[2], type: 'dashed', opacity: 0.35, width: 1 },
          data: releaseWeeks.map((row) => ({ xAxis: row.date })),
        } : undefined,
        z: 2,
      },
      {
        name: '每周提交',
        type: 'scatter',
        data: rows.value.map((row) => !row.complete && row.commits !== null ? [row.date, row.commits] : null),
        symbol: 'emptyCircle',
        symbolSize: 8,
        itemStyle: { color: t.panel, borderColor: t.series[0], borderWidth: 2 },
        z: 4,
      },
      {
        name: '活跃账号',
        type: 'line',
        yAxisIndex: 1,
        data: rows.value.map((row) => row.complete ? row.authors : null),
        connectNulls: false,
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: { color: t.series[3], width: 2 },
        itemStyle: { color: t.series[3] },
        z: 3,
      },
      {
        name: '活跃账号',
        type: 'scatter',
        xAxisIndex: 0,
        yAxisIndex: 1,
        data: rows.value.map((row) => !row.complete && row.authors !== null ? [row.date, row.authors] : null),
        symbol: 'emptyCircle',
        symbolSize: 8,
        itemStyle: { color: t.panel, borderColor: t.series[3], borderWidth: 2 },
        z: 4,
      },
      {
        name: '正式发布',
        type: 'scatter',
        data: rows.value.map((row) => row.releases.length ? {
          value: [row.date, releaseMarkerY],
          count: row.releases.length,
        } : null),
        symbol: 'diamond',
        symbolSize: 11,
        itemStyle: { color: t.series[2] },
        label: {
          show: true,
          position: 'top',
          color: t.series[2],
          fontSize: 9,
          formatter: (params: unknown) => {
            const count = (params as { data?: { count?: number } }).data?.count ?? 0
            return count > 1 ? String(count) : ''
          },
        },
        z: 5,
      },
    ],
  }
})

function select(payload: { dataIndex: number; seriesName: string }) {
  const row = rows.value[payload.dataIndex]
  if (!row) return
  if (payload.seriesName === '正式发布') {
    if (row.releases.length) emit('select-releases', { date: row.date, releases: row.releases })
    return
  }
  if (payload.seriesName === '每周提交' || payload.seriesName === '活跃账号') emit('select', row.sourceIndex)
}
</script>

<template>
  <EChart :option="option" :height="height" hide-tooltip-on-select class="relative z-0" data-testid="commit-activity-chart" @select="select" />
</template>
