<script setup lang="ts">
import { computed } from 'vue'
import type { G2Spec, ViewComposition } from '@antv/g2'
import type { PopularityPoint } from '@/lib/overviewChartData'
import { languageColor } from '@/lib/overviewChartData'
import G2Chart from '@/components/charts/G2Chart.vue'
import { useUiStore } from '@/stores/ui'

const props = defineProps<{
  points: PopularityPoint[]
  total: number
  medianStars: number | null
  medianForks: number | null
  filteredIds: string[]
  filteredCount: number
  selectedRepositoryId: string | null
  overlapGroups: Array<{ fullName: string; repositoryIds: string[]; count: number }>
}>()
const emit = defineEmits<{ selectRepository: [id: string]; clearSelection: [] }>()
const ui = useUiStore()

const filteredSet = computed(() => new Set(props.filteredIds))
const chartPoints = computed(() => props.points.map((point, dataIndex) => ({
  ...point,
  dataIndex,
  sourceIndex: dataIndex,
  focusState: point.repositoryId === props.selectedRepositoryId
    ? 'selected'
    : filteredSet.value.has(point.repositoryId) ? 'matched' : 'muted',
})))
const selectedPoints = computed(() => chartPoints.value.filter((point) => point.focusState === 'selected'))
const matchedPoints = computed(() => chartPoints.value.filter((point) => point.focusState === 'matched'))
const mutedPoints = computed(() => chartPoints.value.filter((point) => point.focusState === 'muted'))
const maxX = computed(() => Math.max(1, ...props.points.map((point) => point.xPlot)))
const maxY = computed(() => Math.max(1, ...props.points.map((point) => point.yPlot)))
const medianXPlot = computed(() => props.medianStars === null ? null : Math.log1p(props.medianStars))
const medianYPlot = computed(() => props.medianForks === null ? null : Math.log1p(props.medianForks))
const languages = computed(() => [...new Set(props.points.map((point) => point.language))].sort((left, right) => left.localeCompare(right)))
const scatterRows = computed(() => {
  const candidates = props.points.filter((point) => point.isOutlier)
  if (!candidates.length) return []
  const medianX = medianXPlot.value ?? 0
  const medianY = medianYPlot.value ?? 0
  const furthest = [...candidates].sort((left, right) =>
    Math.hypot(right.xPlot - medianX, right.yPlot - medianY) - Math.hypot(left.xPlot - medianX, left.yPlot - medianY),
  )[0]
  return [{ xPlot: furthest.xPlot, yPlot: furthest.yPlot, label: furthest.fullName }]
})

function compactCount(value: number) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toLocaleString('zh-CN', { maximumFractionDigits: 1 })}m`
  if (value >= 10_000) return `${(value / 1_000).toLocaleString('zh-CN', { maximumFractionDigits: 1 })}k`
  if (value >= 1_000) return `${(value / 1_000).toLocaleString('zh-CN', { maximumFractionDigits: 1 })}k`
  return Math.round(value).toLocaleString('zh-CN')
}

function formatPlotTick(value: unknown) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return ''
  return compactCount(Math.max(0, Math.expm1(numeric)))
}

const spec = computed<G2Spec>(() => {
  const xLimit = maxX.value * 1.08
  const yLimit = maxY.value * 1.08
  const children: NonNullable<ViewComposition['children']> = []
  if (medianXPlot.value !== null) children.push({
    type: 'line',
    data: [{ xPlot: medianXPlot.value, yPlot: 0 }, { xPlot: medianXPlot.value, yPlot: yLimit }],
    encode: { x: 'xPlot', y: 'yPlot' },
    style: { stroke: ui.isDark ? '#89939e' : '#9aa3ad', lineDash: [4, 4], lineWidth: 1 },
    tooltip: false,
  })
  if (medianYPlot.value !== null) children.push({
    type: 'line',
    data: [{ xPlot: 0, yPlot: medianYPlot.value }, { xPlot: xLimit, yPlot: medianYPlot.value }],
    encode: { x: 'xPlot', y: 'yPlot' },
    style: { stroke: ui.isDark ? '#89939e' : '#9aa3ad', lineDash: [4, 4], lineWidth: 1 },
    tooltip: false,
  })
  const pointTooltip = { title: 'fullName', items: [
      { field: 'language', name: '主语言' },
      { field: 'stars', name: 'Stars', valueFormatter: (value: number) => Number(value).toLocaleString('zh-CN') },
      { field: 'forks', name: 'Forks', valueFormatter: (value: number) => Number(value).toLocaleString('zh-CN') },
    ] }
  const pointStyle = { stroke: ui.isDark ? '#151518' : '#ffffff', lineWidth: 1.5 }
  if (mutedPoints.value.length) children.push({
    type: 'point',
    data: mutedPoints.value,
    encode: { x: 'xPlot', y: 'yPlot', color: 'language', shape: 'point', size: 6 },
    style: { ...pointStyle, fillOpacity: .2 },
    tooltip: pointTooltip,
  })
  if (matchedPoints.value.length) children.push({
    type: 'point',
    data: matchedPoints.value,
    encode: { x: 'xPlot', y: 'yPlot', color: 'language', shape: 'point', size: 6 },
    style: { ...pointStyle, fillOpacity: .9 },
    tooltip: pointTooltip,
  })
  if (selectedPoints.value.length) children.push({
    type: 'point',
    data: selectedPoints.value,
    encode: { x: 'xPlot', y: 'yPlot', color: 'language', shape: 'point', size: 9 },
    style: { ...pointStyle, fillOpacity: 1, lineWidth: 2 },
    tooltip: pointTooltip,
  })
  if (scatterRows.value.length) children.push({
    type: 'text',
    data: scatterRows.value,
    encode: { x: 'xPlot', y: 'yPlot', text: 'label' },
    style: { dx: 7, dy: -8, fontSize: 9, fill: ui.isDark ? '#f0f2f4' : '#303841', stroke: ui.isDark ? '#151518' : '#ffffff', lineWidth: 3, textAlign: 'left' },
    tooltip: false,
  })
  return {
    type: 'view',
    scale: {
      x: { domain: [0, xLimit], tickCount: 6 },
      y: { domain: [0, yLimit], tickCount: 6 },
      color: { domain: languages.value, range: languages.value.map(languageColor) },
    },
    children,
    axis: {
      x: { title: 'Stars', labelFormatter: formatPlotTick, labelFontSize: 10, titleFontSize: 11, grid: false },
      y: { title: 'Forks', labelFormatter: formatPlotTick, labelFontSize: 10, titleFontSize: 11, grid: { stroke: ui.isDark ? '#303942' : '#e6ebef', lineDash: [3, 3] } },
    },
    legend: { color: { position: 'bottom', itemLabelFontSize: 10 }, size: false, opacity: false },
    interaction: { elementHighlight: true, tooltip: { shared: false } },
  }
})

function selectPoint(payload: { datum: Record<string, unknown> }) {
  const id = payload.datum.repositoryId
  if (typeof id === 'string') emit('selectRepository', id)
}

function pointFor(id: string) {
  return props.points.find((point) => point.repositoryId === id)
}
</script>

<template>
  <UiPanel as="article" class="chart-panel scatter-panel" aria-labelledby="overview-popularity-title">
    <div class="panel-heading">
      <div><h2 id="overview-popularity-title" class="panel-title">Stars × Forks 关联</h2><p class="panel-description">每个点代表一个仓库；对数映射压缩长尾，坐标与提示保留真实数量</p></div>
      <div class="scatter-heading-meta"><span class="chart-sample mono">配对 n={{ points.length }} / {{ total }}</span><button v-if="selectedRepositoryId" type="button" class="clear-selection" @click="emit('clearSelection')">清除点选</button></div>
    </div>
    <div class="scatter-subheading"><span v-if="filteredCount !== total">当前筛选 {{ filteredCount }} / {{ total }}</span><span v-else>按当前可比较样本中位数划分参考象限</span><span>描述性分布，不是质量评分</span></div>
    <G2Chart v-if="points.length" :spec="spec" label="Stars 与 Forks 的双变量散点图；坐标为 log1p 映射，虚线分别为原始数值中位数" :height="420" @select="selectPoint" />
    <div v-else class="scatter-empty"><span>没有同时具备有效 Stars 和 Forks 的仓库</span><small>样本不足时不显示中位数参考线。</small></div>
    <div v-if="overlapGroups.length" class="overlap-groups" aria-label="可重叠仓库点位">
      <span class="overlap-label">重合点可展开：</span>
      <span v-for="group in overlapGroups" :key="group.repositoryIds.join(',')" class="overlap-group">
        <span class="overlap-coordinate mono">{{ group.count }} 个</span>
        <button v-for="id in group.repositoryIds" :key="id" type="button" :class="{ 'is-selected': selectedRepositoryId === id }" @click="emit('selectRepository', id)">{{ pointFor(id)?.fullName ?? group.fullName }}</button>
      </span>
    </div>
    <div v-if="points.some((point) => point.isOutlier)" class="outlier-list"><span>分布端点（描述性标注）：</span><button v-for="point in points.filter((item) => item.isOutlier)" :key="point.repositoryId" type="button" @click="emit('selectRepository', point.repositoryId)">{{ point.fullName }} · {{ compactCount(point.stars) }} Stars / {{ compactCount(point.forks) }} Forks</button></div>
    <p class="chart-note">Stars 中位数 {{ medianStars === null ? '—' : medianStars.toLocaleString('zh-CN') }}；Forks 中位数 {{ medianForks === null ? '—' : medianForks.toLocaleString('zh-CN') }}。0 与 1 使用 log1p 分开定位。</p>
  </UiPanel>
</template>

<style scoped>
.chart-panel { min-width: 0; }
.scatter-heading-meta { display: flex; align-items: center; gap: 10px; }
.chart-sample { color: var(--muted); font-size: 10.5px; white-space: nowrap; }
.clear-selection { padding: 4px 7px; border: 1px solid var(--line); border-radius: 6px; color: var(--ink); background: transparent; font: inherit; font-size: 10px; cursor: pointer; }
.clear-selection:hover { background: var(--surface-soft); }
.scatter-subheading { display: flex; justify-content: space-between; gap: 14px; margin: 10px 0 0; color: var(--muted); font-size: 10px; }
.scatter-empty { display: grid; min-height: 280px; align-content: center; justify-items: center; gap: 6px; color: var(--muted); font-size: 12px; }
.scatter-empty small { font-size: 10px; }
.overlap-groups, .outlier-list { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; margin-top: 6px; color: var(--muted); font-size: 10px; }
.overlap-label, .outlier-list > span { flex: none; }
.overlap-group { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 3px; padding: 3px 5px; border: 1px solid var(--line); border-radius: 6px; }
.overlap-coordinate { padding-right: 3px; color: var(--muted); }
.overlap-group button, .outlier-list button { max-width: 220px; overflow: hidden; padding: 3px 5px; border: 0; border-radius: 4px; color: var(--ink); background: var(--surface-soft); font: inherit; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
.overlap-group button:hover, .overlap-group button.is-selected, .outlier-list button:hover { color: var(--primary-ink); background: var(--primary-soft); }
.chart-note { margin: 8px 0 0; color: var(--muted); font-size: 10px; line-height: 1.5; }
@media (max-width: 600px) { .scatter-heading-meta { align-items: flex-end; flex-direction: column; gap: 5px; } .scatter-subheading { flex-direction: column; gap: 4px; } }
</style>
