<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { G2Spec } from '@antv/g2'
import type { ReleaseRecord, TimePoint } from '@/services/types'
import G2Chart from './G2Chart.vue'

const props = withDefaults(defineProps<{ releases: ReleaseRecord[]; commits?: TimePoint[]; height?: number; compact?: boolean }>(), { commits: () => [], height: 150, compact: false })
const emit = defineEmits<{ select: [release: ReleaseRecord] }>()
const eventDates = computed(() => [
  ...props.releases.map((release) => release.publishedAt.slice(0, 10)),
  ...props.commits.map((point) => point.date.slice(0, 10)),
].filter((date) => /^\d{4}-\d{2}-\d{2}$/.test(date)).sort())
const minDate = computed(() => eventDates.value[0] ?? '')
const maxDate = computed(() => eventDates.value.at(-1) ?? '')
const startDate = ref('')
const endDate = ref('')
watch([minDate, maxDate], ([min, max]) => {
  if (!min || !max) { startDate.value = ''; endDate.value = ''; return }
  const latest = Date.parse(max + 'T00:00:00Z')
  startDate.value = new Date(Math.max(Date.parse(min + 'T00:00:00Z'), latest - 90 * 86400000)).toISOString().slice(0, 10)
  endDate.value = max
}, { immediate: true })
const range = computed(() => {
  if (!startDate.value || !endDate.value || startDate.value > endDate.value) return null
  return { start: Date.parse(startDate.value + 'T00:00:00Z'), end: Date.parse(endDate.value + 'T00:00:00Z') + 86400000 }
})
const commitRows = computed(() => props.commits.flatMap((point, dataIndex) => {
  const time = Date.parse(point.date + 'T00:00:00Z')
  if (!range.value || !Number.isFinite(time) || time < range.value.start || time >= range.value.end) return []
  // G2 的 time scale 只接受 Date/number；ISO 日期字符串会被转成 NaN，
  // 导致所有仓库的时间序列都挤到同一个位置。
  return [{ date: new Date(time), commits: point.value ?? point.observedValue ?? null, quality: point.value === null ? '部分覆盖或缺失' : '完整数据', dataIndex, seriesName: '每周提交' }]
}))
const releaseRows = computed(() => props.releases.flatMap((release, dataIndex) => {
  const time = Date.parse(release.publishedAt)
  if (!range.value || !Number.isFinite(time) || time < range.value.start || time >= range.value.end) return []
  return [{
    date: new Date(time),
    day: release.publishedAt.slice(0, 10),
    tag: release.tag,
    lane: release.prerelease ? '预发布' : '正式发布',
    symbol: 'diamond',
    dataIndex,
    sourceIndex: dataIndex,
    seriesName: release.prerelease ? '预发布' : '正式发布',
  }]
}))
const commitsSpec = computed<G2Spec>(() => ({
  type: 'line', data: commitRows.value,
  encode: { x: 'date', y: 'commits' },
  scale: { x: { type: 'time', utc: true } },
  style: { stroke: '#4d819b', lineWidth: 1.8 },
  axis: { x: { label: !props.compact, labelFontSize: 8 }, y: { title: 'Commit / 周', gridLineDash: [3, 3] } },
  tooltip: { title: 'date', items: [{ field: 'commits', name: 'Commit（完整或已观察）' }, { field: 'quality', name: '覆盖状态' }] },
}))
const releasesSpec = computed<G2Spec>(() => ({
  type: 'point', data: releaseRows.value,
  encode: { x: 'date', y: 'lane' },
  scale: { x: { type: 'time', utc: true }, y: { domain: ['正式发布', '预发布'] } },
  style: { shape: 'diamond', fill: '#ce3f7c', stroke: '#ce3f7c', r: 5 },
  axis: { x: { label: !props.compact, labelFontSize: 8 }, y: { title: false } },
  tooltip: { title: 'day', items: [{ field: 'tag', name: '版本' }, { field: 'lane', name: '类型' }] },
}))
function select(payload: { dataIndex: number; seriesName: string }) {
  if (payload.seriesName !== '正式发布' && payload.seriesName !== '预发布') return
  const release = props.releases[payload.dataIndex]
  if (release) emit('select', release)
}
function resetRange() {
  if (!minDate.value || !maxDate.value) return
  const latest = Date.parse(maxDate.value + 'T00:00:00Z')
  startDate.value = new Date(Math.max(Date.parse(minDate.value + 'T00:00:00Z'), latest - 90 * 86400000)).toISOString().slice(0, 10)
  endDate.value = maxDate.value
}
</script>

<template>
  <div class="release-timeline" data-testid="release-timeline">
    <div v-if="!compact" class="release-timeline__range">
      <label>起始日期 <input v-model="startDate" type="date" :min="minDate" :max="endDate || maxDate" aria-label="时间线起始日期" /></label>
      <label>结束日期 <input v-model="endDate" type="date" :min="startDate || minDate" :max="maxDate" aria-label="时间线结束日期" /></label>
      <button type="button" @click="resetRange">重置近 90 天</button>
    </div>
    <section><h4>每周 Commit</h4><G2Chart :spec="commitsSpec" label="按 UTC 周排列的 Commit 活动" :height="Math.max(84, Math.round(height * 0.5))" /></section>
    <section><h4>Release 时间点</h4><G2Chart :spec="releasesSpec" label="按日期分道展示正式 Release 和预发布；点击打开详情" :height="Math.max(74, Math.round(height * 0.42))" @select="select" /></section>
  </div>
</template>

<style scoped>
.release-timeline { display:grid; gap:3px; }
.release-timeline section { min-width:0; }
.release-timeline :deep(.g2-chart__canvas) { min-height:0; }
.release-timeline h4 { margin:0; color:var(--muted); font-size:10px; font-weight:600; }
.release-timeline__range { display:flex; flex-wrap:wrap; align-items:center; gap:8px; color:var(--muted); font-size:10px; }
.release-timeline__range label { display:flex; align-items:center; gap:4px; }
.release-timeline__range input { min-width:120px; border:1px solid var(--line); border-radius:5px; background:var(--surface); color:var(--ink); padding:3px 5px; }
.release-timeline__range button { border:0; background:transparent; color:var(--accent,#2e8fcb); text-decoration:underline; cursor:pointer; }
</style>
