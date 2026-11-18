<script setup lang="ts">
import { Chart } from '@antv/g2'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

export interface DecisionPoint {
  repository_id: number
  full_name: string
  x: number
  y: number
  eligibility: string
  x_unit: string
  y_unit: string
  x_sample_count: number | null
  y_sample_count: number | null
  x_coverage_status: string
  y_coverage_status: string
  window_start: string | null
  window_end_exclusive: string | null
  net_http_middleware_status: string
}

interface ChartPoint extends DecisionPoint { x_log1p: number; y_log1p: number; selected_size: number }

const props = defineProps<{ points: DecisionPoint[]; selectedId: number | null; isDark: boolean }>()
const emit = defineEmits<{ select: [repositoryId: number] }>()
const root = ref<HTMLDivElement | null>(null)
let chart: Chart | null = null
let sequence = 0
const colors = ['#55b7f3', '#53c998', '#f2b35d', '#f17878']

async function renderChart() {
  if (!root.value) return
  const current = ++sequence
  if (!chart) {
    chart = new Chart({ container: root.value, autoFit: true })
    chart.on('element:click', (event: unknown) => {
      const payload = event as { data?: { data?: ChartPoint } }
      if (payload.data?.data) emit('select', payload.data.data.repository_id)
    })
  }
  const pointData: ChartPoint[] = props.points.map((point) => ({
    ...point,
    x_log1p: Math.log1p(point.x),
    y_log1p: Math.log1p(point.y),
    selected_size: point.repository_id === props.selectedId ? 16 : 8,
  }))
  chart.options({
    type: 'point',
    data: pointData,
    encode: { x: 'x_log1p', y: 'y_log1p', color: 'full_name', shape: 'eligibility', size: 'selected_size' },
    scale: { color: { domain: pointData.map((point) => point.full_name), range: colors }, shape: { domain: ['eligible', 'conditional', 'unknown', 'ineligible'], range: ['point', 'diamond', 'hollow', 'hollow'] }, size: { domain: [0, 16], range: [5, 18] } },
    axis: {
      x: { title: 'log1p（12 周周均 Commit）', labelFontSize: 11, titleFontSize: 11, titleFill: props.isDark ? '#d9e1e8' : '#43515d', titleOpacity: 1, labelFill: props.isDark ? '#c2ccd5' : '#667480', labelOpacity: 1, tickStroke: props.isDark ? '#65717b' : '#aab5be', gridStroke: props.isDark ? '#8a969f' : '#9ba8b2', gridStrokeOpacity: props.isDark ? 0.16 : 0.2 },
      y: { title: 'log1p（12 周周均新开 PR）', labelFontSize: 11, titleFontSize: 11, titleFill: props.isDark ? '#d9e1e8' : '#43515d', titleOpacity: 1, labelFill: props.isDark ? '#c2ccd5' : '#667480', labelOpacity: 1, tickStroke: props.isDark ? '#65717b' : '#aab5be', gridStroke: props.isDark ? '#8a969f' : '#9ba8b2', gridStrokeOpacity: props.isDark ? 0.16 : 0.2 },
    },
    legend: { color: { position: 'bottom', labelFill: props.isDark ? '#c2ccd5' : '#667480', labelFillOpacity: 1 }, shape: false, size: false },
    tooltip: { title: 'full_name', items: [
      { field: 'x', name: '周均 Commit（原始值）' }, { field: 'x_unit', name: 'Commit 单位' }, { field: 'x_sample_count', name: 'Commit 样本量 n' }, { field: 'x_coverage_status', name: 'Commit 覆盖' },
      { field: 'y', name: '周均新开 PR（原始值）' }, { field: 'y_unit', name: 'PR 单位' }, { field: 'y_sample_count', name: 'PR 样本量 n' }, { field: 'y_coverage_status', name: 'PR 覆盖' },
      { field: 'window_start', name: '窗口开始 UTC' }, { field: 'window_end_exclusive', name: '窗口结束 UTC（不含）' }, { field: 'eligibility', name: '硬约束资格状态' },
      { field: 'net_http_middleware_status', name: 'net/http 中间件条件' },
    ] },
    style: { fillOpacity: 0.86, stroke: props.isDark ? '#171d22' : '#ffffff', lineWidth: 1.5 },
  })
  await chart.render()
  if (current !== sequence) return
}

onMounted(() => { void renderChart() })
watch(() => [props.points, props.selectedId, props.isDark], () => { void renderChart() }, { deep: true })
onBeforeUnmount(() => { sequence += 1; chart?.destroy(); chart = null })
</script>

<template>
  <div ref="root" class="decision-scatter" role="img" aria-label="同一场景候选的 12 周 Commit 与新开 PR 活动散点图；不表示综合质量排名" />
</template>

<style scoped>
.decision-scatter { width: 100%; height: 100%; min-height: 320px; }
</style>
