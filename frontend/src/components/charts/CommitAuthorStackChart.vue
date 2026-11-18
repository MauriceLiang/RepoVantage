<script setup lang="ts">
import { computed } from 'vue'
import type { G2Spec } from '@antv/g2'
import type { RepositoryChartData, TimePoint } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import { observedValue } from './comboHelpers'
import { buildCompleteFourWeekAverage } from '@/lib/commitAverages'
import G2Chart from './G2Chart.vue'

const props = withDefaults(defineProps<{ points: TimePoint[]; data: RepositoryChartData; height?: number }>(), { height: 260 })
const emit = defineEmits<{ select: [index: number] }>()
const ui = useUiStore()
const authors = computed(() => props.data.commitAccounts.map((account) => account || '未知账号'))
const labels = computed(() => [...authors.value, '其他账号', '未关联账号'])
const colors = computed(() => ui.isDark
  ? ['#8ab8cf', '#a79bc9', '#8cb7a1', '#cba88c', '#b99cab', '#858c98', '#555d67']
  : ['#4d819b', '#8177a0', '#679884', '#b38770', '#a4798f', '#929aa5', '#c5ccd4'])
const rows = computed(() => {
  const weeks = new Map(props.data.commitWeekly.map((week) => [week.start, week]))
  return props.points.flatMap((point, dataIndex) => {
    const week = weeks.get(point.date)
    if (!week || observedValue(point) === null) return []
    return labels.value.map((label, index) => {
      const value = index < authors.value.length ? week.contributors[index] ?? 0 : index === authors.value.length ? week.otherCommits : week.unidentifiedCommits
      return { date: point.date, series: label, value, quality: week.complete ? 'complete' : 'partial', dataIndex, sourceIndex: dataIndex, seriesName: label }
    })
  })
})
const averages = computed(() => buildCompleteFourWeekAverage(props.points))
const spec = computed<G2Spec>(() => ({
  type: 'view',
  scale: { color: { domain: labels.value, range: colors.value } },
  axis: { x: { labelFontSize: 9, labelAutoRotate: true }, y: { title: '提交 / 周', gridLineDash: [3, 3] } },
  legend: false,
  children: [
    { type: 'interval', data: rows.value, transform: [{ type: 'stackY' }], encode: { x: 'date', y: 'value', color: 'series' } },
    { type: 'line', data: averages.value, encode: { x: 'date', y: 'value' }, style: { stroke: ui.isDark ? '#f0f1f2' : '#252c32', lineWidth: 2.1 } },
  ],
  interaction: { tooltip: { shared: true } },
  tooltip: { title: 'date', items: [{ field: 'series', name: '作者分组' }, { field: 'value', name: '提交数' }, { field: 'quality', name: '覆盖状态' }] },
}))
</script>

<template>
  <div class="commit-author-stack">
    <G2Chart :spec="spec" label="按作者堆叠的每周 Commit 数与四周均值" :height="height" @select="emit('select', $event.dataIndex)" />
    <div class="commit-author-stack__legend" role="list" aria-label="Commit 作者分组图例">
      <span v-for="(label, index) in labels" :key="`${label}-${index}`" class="commit-author-stack__legend-item" role="listitem" :title="label">
        <i class="commit-author-stack__legend-swatch" :style="{ backgroundColor: colors[index] }" aria-hidden="true" />
        <span class="commit-author-stack__legend-label">{{ label }}</span>
      </span>
    </div>
  </div>
</template>

<style scoped>
.commit-author-stack { min-width:0; }
.commit-author-stack__legend { display:flex; min-width:0; flex-wrap:wrap; align-items:center; gap:6px 12px; padding:2px 3px 0; }
.commit-author-stack__legend-item { display:inline-flex; min-width:0; max-width:min(240px,100%); align-items:center; gap:6px; color:var(--muted); font-size:11px; line-height:1.4; }
.commit-author-stack__legend-swatch { width:8px; height:8px; flex:0 0 8px; border-radius:2px; }
.commit-author-stack__legend-label { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
</style>
