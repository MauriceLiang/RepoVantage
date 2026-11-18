<script setup lang="ts">
import { Chart } from '@antv/g2'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { AtlasBrushSelection, AtlasChartPoint, AtlasPoint, AtlasSelectionRange } from '@/data/researchTypes'

interface ChartPoint extends AtlasChartPoint {
  star_size: number
  selected_size: number
  window_start: string
  window_end_exclusive: string
  commit_coverage: string
  prs_coverage: string
}

const props = defineProps<{
  points: AtlasChartPoint[]
  selectedId: number | null
  isDark: boolean
  brushSelection: AtlasSelectionRange | null
}>()
const emit = defineEmits<{
  select: [point: AtlasPoint]
  brush: [selection: AtlasBrushSelection]
}>()
const root = ref<HTMLDivElement | null>(null)
let chart: Chart | null = null
let renderSequence = 0
let chartPoints: ChartPoint[] = []
let reducedMotion = false
let motionPreference: MediaQueryList | null = null

const colors = ['#55b7f3', '#53c998', '#f2b35d', '#f17878', '#56c0bd', '#91c66b', '#f08d5d']

function sortedRange(value: unknown): [number, number] | null {
  if (!Array.isArray(value) || value.length < 2 || typeof value[0] !== 'number' || typeof value[1] !== 'number') return null
  return [Math.min(value[0], value[1]), Math.max(value[0], value[1])]
}

async function renderChart() {
  if (!root.value) return
  const sequence = ++renderSequence
  const languageOrder = [...new Set(props.points.map((point) => point.language))]
  const hasStars = props.points.length > 0 && props.points.every((point) => typeof point.stars === 'number')
  chartPoints = props.points.map((point) => ({
    ...point,
    star_size: hasStars ? Math.log1p(point.stars ?? 0) : 1,
    selected_size: (hasStars ? Math.log1p(point.stars ?? 0) : 1) + (point.repository_id === props.selectedId ? 8 : 0),
    window_start: point.observation_window.start,
    window_end_exclusive: point.observation_window.end_exclusive,
    commit_coverage: point.coverage.commits,
    prs_coverage: point.coverage.prs_opened,
    selected: point.repository_id === props.selectedId,
  }))
  if (!chart) {
    chart = new Chart({ container: root.value, autoFit: true })
    chart.on('element:click', (event: unknown) => {
      const payload = event as { data?: { data?: ChartPoint } }
      const point = payload.data?.data
      if (point) emit('select', point)
    })
    chart.on('brush:filter', (event: unknown) => {
      const payload = event as { data?: { selection?: unknown[] } }
      const selection = payload.data?.selection
      if (!Array.isArray(selection) || selection.length < 2) return
      const xRange = sortedRange(selection[0])
      const yRange = sortedRange(selection[1])
      if (!xRange || !yRange) return
      const repositoryIds = chartPoints.filter((point) =>
        point.x_position >= xRange[0] && point.x_position <= xRange[1]
        && point.y_position >= yRange[0] && point.y_position <= yRange[1],
      ).map((point) => point.repository_id)
      emit('brush', {
        repository_ids: repositoryIds,
        selection: [xRange, yRange],
        reset: repositoryIds.length === chartPoints.length,
      })
    })
  }
  chart.options({
    type: 'point',
    data: chartPoints,
    encode: { x: 'x_position', y: 'y_position', color: 'language', shape: 'point', size: 'selected_size' },
    scale: {
      x: { nice: true },
      y: { nice: true },
      color: { domain: languageOrder, range: colors },
      size: hasStars ? { domain: [0, 22], range: [5, 18] } : { domain: [0, 10], range: [7, 18] },
    },
    axis: {
      x: { title: props.points[0]?.x_label ?? 'X', titleFontSize: 12, titleFill: props.isDark ? '#d9e1e8' : '#43515d', titleOpacity: 1, labelFontSize: 11, labelFill: props.isDark ? '#c2ccd5' : '#667480', labelOpacity: 1, tickStroke: props.isDark ? '#65717b' : '#aab5be', gridStroke: props.isDark ? '#8a969f' : '#9ba8b2', gridStrokeOpacity: props.isDark ? 0.16 : 0.2 },
      y: { title: props.points[0]?.y_label ?? 'Y', titleFontSize: 12, titleFill: props.isDark ? '#d9e1e8' : '#43515d', titleOpacity: 1, labelFontSize: 11, labelFill: props.isDark ? '#c2ccd5' : '#667480', labelOpacity: 1, tickStroke: props.isDark ? '#65717b' : '#aab5be', gridStroke: props.isDark ? '#8a969f' : '#9ba8b2', gridStrokeOpacity: props.isDark ? 0.16 : 0.2 },
    },
    animate: reducedMotion ? false : { enter: { type: 'fadeIn', duration: 350 }, update: { type: 'morphing', duration: 250 } },
    legend: {
      color: { position: 'bottom', layout: { justifyContent: 'center' }, labelFill: props.isDark ? '#c2ccd5' : '#667480', labelFillOpacity: 1 },
      size: false,
    },
    tooltip: {
      title: 'full_name',
      items: [
        { field: 'language', name: '主要语言' },
        { field: 'x_value', name: props.points[0]?.x_value_label ?? 'X 原始指标值' },
        { field: 'y_value', name: props.points[0]?.y_value_label ?? 'Y 原始指标值' },
        { field: 'weekly_commit_mean', name: '周均 Commit（原始值）' },
        { field: 'weekly_pr_open_mean', name: '周均新开 PR（原始值）' },
        { field: 'stars', name: 'Stars 快照' },
        { field: 'sample_role', name: '样本角色' },
        { field: 'window_start', name: '窗口开始 UTC' },
        { field: 'window_end_exclusive', name: '窗口结束 UTC（不含）' },
        { field: 'commit_coverage', name: 'Commit 覆盖' },
        { field: 'prs_coverage', name: '新开 PR 覆盖' },
      ],
    },
    style: { fillOpacity: 0.9, stroke: props.isDark ? '#171d22' : '#ffffff', lineWidth: 1 },
    state: {
      inactive: { opacity: 0.82, fillOpacity: 0.82 },
      active: { opacity: 1, fillOpacity: 1, lineWidth: 2 },
    },
    interaction: {
      tooltip: { shared: false },
      brushFilter: { maskFill: props.isDark ? '#d9e1e8' : '#2563eb', maskFillOpacity: 0.12, maskStroke: props.isDark ? '#d9e1e8' : '#2563eb', maskStrokeOpacity: 0.55 },
      elementHoverScale: { scale: 1.18, shadow: true, shadowColor: props.isDark ? '#55b7f3' : '#2563eb' },
    },
  })
  await chart.render()
  if (sequence !== renderSequence) return
  if (props.brushSelection) chart.emit('brush:filter', { data: { selection: props.brushSelection } })
}

function onMotionPreferenceChange(event: MediaQueryListEvent) {
  reducedMotion = event.matches
  void renderChart()
}

onMounted(() => {
  motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)')
  reducedMotion = motionPreference.matches
  motionPreference.addEventListener('change', onMotionPreferenceChange)
  void renderChart()
})
watch(() => [props.points, props.selectedId, props.isDark], () => { void renderChart() }, { deep: true })
onBeforeUnmount(() => {
  renderSequence += 1
  motionPreference?.removeEventListener('change', onMotionPreferenceChange)
  motionPreference = null
  chartPoints = []
  chart?.destroy()
  chart = null
})
</script>

<template>
  <div ref="root" class="research-g2-chart" :data-view="points[0] ? `${points[0].x_label}|${points[0].y_label}` : ''" role="img" aria-label="真实仓库活动图谱；可悬停查看坐标原值、拖动框选缩放并双击恢复" />
</template>

<style scoped>
.research-g2-chart { width: 100%; height: 100%; min-height: 500px; }
</style>
