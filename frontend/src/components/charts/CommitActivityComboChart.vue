<script setup lang="ts">
import { computed } from 'vue'
import type { G2Spec } from '@antv/g2'
import type { RepositoryChartData, TimePoint } from '@/services/types'
import { buildCommitActivity } from '@/lib/commitActivity'
import { buildCompleteFourWeekAverage } from '@/lib/commitAverages'
import G2Chart from './G2Chart.vue'

const props = withDefaults(defineProps<{
  points: TimePoint[]
  weeks: RepositoryChartData['commitWeekly']
  windowStart: string | null
  windowEnd: string | null
  height?: number
}>(), { height: 420 })
const emit = defineEmits<{ select: [index: number] }>()
const rows = computed(() => buildCommitActivity(props.points, props.weeks, props.windowStart, props.windowEnd))
const commitRows = computed(() => rows.value.map((row) => ({
  date: row.date,
  plotted: row.complete ? row.commits : null,
  observed: row.commits,
  complete: row.complete,
  quality: row.complete ? '完整周' : row.commits === null ? '缺少数据' : '仅已观察样本',
  sourceIndex: row.sourceIndex,
  dataIndex: row.sourceIndex,
  seriesName: '每周提交',
})))
const authorRows = computed(() => rows.value.map((row) => ({
  date: row.date,
  plotted: row.complete ? row.authors : null,
  observed: row.authors,
  quality: row.complete ? '完整周' : row.authors === null ? '缺少数据' : '仅已观察样本',
  sourceIndex: row.sourceIndex,
  dataIndex: row.sourceIndex,
  seriesName: '活跃账号',
})))
const commitAverages = computed(() => {
  const byDate = new Map(buildCompleteFourWeekAverage(props.points).map((point) => [point.date, point]))
  return rows.value.map((row) => ({
    date: row.date,
    value: byDate.get(row.date)?.value ?? null,
    sourceIndex: row.sourceIndex,
    dataIndex: row.sourceIndex,
    seriesName: '连续四个完整周均值',
  }))
})
const commitsSpec = computed<G2Spec>(() => ({
  type: 'view',
  scale: { color: { domain: ['完整周', '仅已观察样本'], range: ['#e5a03a', '#ffffff'] } },
  children: [
    { type: 'interval', data: commitRows.value.filter((row) => row.complete), encode: { x: 'date', y: 'observed', color: 'quality' }, style: { fillOpacity: 0.84 } },
    { type: 'line', data: commitAverages.value, encode: { x: 'date', y: 'value' }, style: { stroke: '#2e8fcb', lineWidth: 2.5, lineDash: [5, 3] } },
    { type: 'point', data: commitRows.value.filter((row) => row.observed !== null && !row.complete), encode: { x: 'date', y: 'observed' }, style: { fill: '#ffffff', stroke: '#e5a03a', lineWidth: 2, r: 3.8 } },
  ],
  axis: { x: { labelFontSize: 8, labelAutoRotate: true }, y: { title: 'Commit / 周', gridLineDash: [3, 3] } },
  interaction: { tooltip: { shared: true } },
  tooltip: { title: 'date', items: [{ field: 'observed', name: '已观察提交数' }, { field: 'value', name: '连续四个完整周均值' }, { field: 'quality', name: '覆盖状态' }] },
}))
const authorsSpec = computed<G2Spec>(() => ({
  type: 'view',
  children: [
    { type: 'area', data: authorRows.value, encode: { x: 'date', y: 'plotted' }, style: { fill: '#2e8fcb', fillOpacity: 0.16 } },
    { type: 'line', data: authorRows.value, encode: { x: 'date', y: 'plotted' }, style: { stroke: '#2e8fcb', lineWidth: 2.2 } },
    { type: 'point', data: authorRows.value.filter((row) => row.observed !== null), encode: { x: 'date', y: 'observed', color: 'quality' }, scale: { color: { domain: ['完整周', '仅已观察样本'], range: ['#2e8fcb', '#ffffff'] } }, style: { stroke: '#2e8fcb', lineWidth: 2, r: 3.5 } },
  ],
  axis: { x: { labelFontSize: 8, labelAutoRotate: true }, y: { title: '活跃账号 / 周', gridLineDash: [3, 3] } },
  interaction: { tooltip: { shared: true } },
  tooltip: { title: 'date', items: [{ field: 'observed', name: '活跃账号' }, { field: 'quality', name: '覆盖状态' }] },
}))
function selectCommit(payload: { dataIndex: number; seriesName: string }) {
  if (payload.seriesName === '每周提交' || payload.seriesName === '活跃账号') emit('select', payload.dataIndex)
}
</script>

<template>
  <div class="commit-activity-charts" data-testid="commit-activity-chart">
    <div class="commit-activity-charts__metrics">
      <section><h4>每周 Commit <span class="chart-hint">柱：完整周 · 虚线：连续四个完整周均值</span></h4><G2Chart :spec="commitsSpec" label="每周 Commit 柱状图与连续四个完整周均值，空心点为部分覆盖" :height="Math.max(140, Math.round(height * 0.48))" @select="selectCommit" /></section>
      <section><h4>活跃账号 <span class="chart-hint">面积：活跃范围 · 空心点：部分覆盖</span></h4><G2Chart :spec="authorsSpec" label="每周活跃账号面积趋势，空心点为部分覆盖" :height="Math.max(140, Math.round(height * 0.48))" @select="selectCommit" /></section>
    </div>
  </div>
</template>

<style scoped>
.commit-activity-charts { display:grid; gap:8px; }
.commit-activity-charts__metrics { display:grid; grid-template-columns:minmax(0,1fr); gap:10px; }
.commit-activity-charts section { min-width:0; }
.commit-activity-charts h4 { display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 8px; margin:0 0 2px; color:var(--muted); font-size:10px; font-weight:600; }
.commit-activity-charts .chart-hint { font-size:9px; font-weight:400; }
@media (min-width: 900px) { .commit-activity-charts__metrics { grid-template-columns:minmax(0,1fr) minmax(0,1fr); } }
</style>
