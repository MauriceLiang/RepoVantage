<script setup lang="ts">
import { computed } from 'vue'
import type { G2Spec } from '@antv/g2'
import type { Coverage, NamedSeries } from '@/services/types'
import { buildIssueTrend } from '@/lib/issueTrend'
import G2Chart from './G2Chart.vue'

const props = withDefaults(defineProps<{
  series: NamedSeries[]
  coverage: Coverage['state']
  windowStart: string | null
  windowEnd: string | null
  height?: number
}>(), { height: 310 })
const rows = computed(() => buildIssueTrend(props.series, props.coverage, props.windowStart, props.windowEnd))
const counts = computed(() => rows.value.flatMap((row, dataIndex) => [
  { date: row.date, group: '新增 Issue', value: row.added.value, complete: row.added.complete, quality: row.added.complete ? '完整周' : row.added.value === null ? '缺少数据' : '部分覆盖', dataIndex, seriesName: '新增 Issue' },
  { date: row.date, group: '关闭 Issue', value: row.resolved.value, complete: row.resolved.complete, quality: row.resolved.complete ? '完整周' : row.resolved.value === null ? '缺少数据' : '部分覆盖', dataIndex, seriesName: '关闭 Issue' },
]))
const differences = computed(() => rows.value.map((row, dataIndex) => ({ date: row.date, value: row.difference, dataIndex, seriesName: '新增 − 关闭' })))
function sourceCount(key: string, date: string) {
  const source = props.series.find((item) => item.key === key || (key === 'opened' && item.key === 'created'))
  return source?.points.find((point) => point.date === date)
}
const accessibleRows = computed(() => rows.value.map((row) => {
  const format = (point: ReturnType<typeof sourceCount>, fallback: number | null, complete: boolean) => {
    if (fallback !== null) return fallback + (complete ? '，完整覆盖' : '，部分覆盖')
    if (!point) return '无可用数据'
    if (point.observedValue !== null && point.observedValue !== undefined) return point.observedValue + ' 已观察，覆盖不完整'
    return '无可用数据，覆盖不完整'
  }
  return {
    date: row.date,
    added: format(sourceCount('opened', row.date), row.added.value, row.added.complete),
    closed: format(sourceCount('closed', row.date), row.resolved.value, row.resolved.complete),
    difference: row.difference === null ? '覆盖不完整，未计算' : String(row.difference),
  }
}))
const spec = computed<G2Spec>(() => ({
  type: 'view',
  scale: { color: { domain: ['新增 Issue', '关闭 Issue'], range: ['#e5a03a', '#ce3f7c'] } },
  children: [
    { type: 'interval', data: counts.value, transform: [{ type: 'dodgeX' }], encode: { x: 'date', y: 'value', color: 'group' }, style: { fillOpacity: 0.78 } },
    { type: 'line', data: differences.value, encode: { x: 'date', y: 'value' }, style: { stroke: '#8177a0', lineWidth: 2.4 } },
    { type: 'point', data: differences.value.filter((row) => row.value !== null), encode: { x: 'date', y: 'value' }, style: { fill: '#8177a0', r: 3 } },
  ],
  axis: { x: { labelFontSize: 9, labelAutoRotate: true }, y: { title: '数量 / 新增减关闭', gridLineDash: [3, 3] } },
  legend: { color: { position: 'bottom' } },
  interaction: { tooltip: { shared: true } },
  tooltip: { title: 'date', items: [{ field: 'group', name: '指标' }, { field: 'value', name: '数量' }, { field: 'quality', name: '覆盖状态' }] },
}))
</script>

<template>
  <div data-testid="issue-trend-chart">
    <G2Chart :spec="spec" label="Issue 每周新增、关闭及完整周差值" :height="height" />
    <details class="issue-trend__data-list"><summary>查看 UTC 周数据与覆盖状态</summary><ul><li v-for="row in accessibleRows" :key="row.date">{{ row.date }}：新增 {{ row.added }}；关闭 {{ row.closed }}；新增减关闭 {{ row.difference }}</li></ul></details>
  </div>
</template>

<style scoped>
.issue-trend__data-list { color:var(--muted); font-size:10px; }
.issue-trend__data-list ul { display:grid; gap:3px; max-height:160px; overflow:auto; margin:6px 0; padding-left:18px; }
</style>
