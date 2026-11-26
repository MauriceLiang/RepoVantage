<script setup lang="ts">
import { computed, ref } from 'vue'

type Dimension = { key: string; label: string; sampleKey?: string; sampleTotalKey?: string; qualityKey?: string }
type RadarRow = Record<string, string | number | null>

const props = defineProps<{
  rows: RadarRow[]
  dimensions: Dimension[]
}>()

const width = 580
const height = 400
const centerX = 290
const centerY = 200
const radius = 145
const labelRadius = radius + 28
const gridLevels = [20, 40, 60, 80, 100]
const linePatterns = ['none', '6 3', '2 2', '8 2 1.5 2', '1 3']
const hiddenSeries = ref(new Set<string>())
const comparableAxes = computed(() => props.dimensions.filter((dimension) =>
  props.rows.filter((row) => typeof row[`${dimension.key}Score`] === 'number' && Number.isFinite(row[`${dimension.key}Score`])).length >= 2,
))
const chartDimensions = computed(() => comparableAxes.value.length >= 3 ? comparableAxes.value : props.dimensions)
const hasEnoughAxes = computed(() => comparableAxes.value.length >= 3)

function axisPoint(index: number, level = 100, axisCount = chartDimensions.value.length) {
  const angle = (Math.PI * 2 * index) / Math.max(axisCount, 1) - Math.PI / 2
  const distance = radius * level / 100
  return {
    x: centerX + Math.cos(angle) * distance,
    y: centerY + Math.sin(angle) * distance,
  }
}

const grid = computed(() => gridLevels.map((level) => ({
  level,
  points: chartDimensions.value.map((_, index) => axisPoint(index, level, chartDimensions.value.length)).map(({ x, y }) => `${x},${y}`).join(' '),
  labelY: centerY - radius * level / 100 + 4,
})))

const axes = computed(() => chartDimensions.value.map((dimension, index) => {
  const angle = (Math.PI * 2 * index) / chartDimensions.value.length - Math.PI / 2
  const point = axisPoint(index, 100, chartDimensions.value.length)
  const labelX = centerX + Math.cos(angle) * labelRadius
  const labelY = centerY + Math.sin(angle) * labelRadius
  return {
    ...dimension,
    point,
    labelX,
    labelY,
    textAnchor: Math.cos(angle) > 0.3 ? 'start' : Math.cos(angle) < -0.3 ? 'end' : 'middle',
  }
}))

const series = computed(() => props.rows.map((row, seriesIndex) => {
  const points = chartDimensions.value.map((dimension, index) => {
    const raw = row[dimension.key]
    const rawScore = row[`${dimension.key}Score`]
    const score = typeof rawScore === 'number' && Number.isFinite(rawScore) ? rawScore : null
    const coordinates = score !== null ? axisPoint(index, Math.max(0, Math.min(100, score)), chartDimensions.value.length) : null
    const angle = (Math.PI * 2 * index) / chartDimensions.value.length - Math.PI / 2
    const overlapping = score === null ? [] : props.rows.flatMap((candidate, candidateIndex) => {
      const candidateScore = candidate[`${dimension.key}Score`]
      return typeof candidateScore === 'number' && Number.isFinite(candidateScore) && Math.abs(candidateScore - score) <= 7.5
        ? [{ index: candidateIndex }]
        : []
    })
    const overlapIndex = overlapping.findIndex((candidate) => candidate.index === seriesIndex)
    const pointOffset = overlapping.length > 1 ? (overlapIndex - (overlapping.length - 1) / 2) * 6 : 0
    const sampleCount = dimension.sampleKey ? row[dimension.sampleKey] : null
    const sampleTotal = dimension.sampleTotalKey ? row[dimension.sampleTotalKey] : null
    const quality = dimension.qualityKey ? row[dimension.qualityKey] : null
    return {
      index,
      key: dimension.key,
      label: dimension.label,
      raw,
      score,
      sampleCount: typeof sampleCount === 'number' ? sampleCount : null,
      sampleTotal: typeof sampleTotal === 'number' ? sampleTotal : null,
      quality: typeof quality === 'string' ? quality : null,
      markerX: coordinates ? coordinates.x - Math.sin(angle) * pointOffset : undefined,
      markerY: coordinates ? coordinates.y + Math.cos(angle) * pointOffset : undefined,
      ...coordinates,
    }
  })
  const complete = points.every((point) => point.score !== null)
  const edges = points.flatMap((point, index) => {
    const next = points[(index + 1) % points.length]
    return point.score !== null && next?.score !== null && point.x !== undefined && point.y !== undefined && next.x !== undefined && next.y !== undefined
      ? [{ key: `${point.index}-${next.index}`, x1: point.x, y1: point.y, x2: next.x, y2: next.y }]
      : []
  })
  return {
    label: String(row.repository ?? ''),
    color: String(row.color ?? '#64748b'),
    points,
    complete,
    edges,
    strokeDasharray: linePatterns[seriesIndex % linePatterns.length],
    polygonPoints: complete ? points.map((point) => `${point.x},${point.y}`).join(' ') : '',
    comparableCount: points.filter((point) => point.score !== null).length,
    measuredCount: props.dimensions.filter((dimension) => typeof row[dimension.key] === 'number' && Number.isFinite(row[dimension.key])).length,
  }
}))

const visibleSeries = computed(() => series.value.filter((item) => !hiddenSeries.value.has(item.label)))
const coverage = computed(() => props.dimensions.map((dimension) => ({
  key: dimension.key,
  label: dimension.label,
  measured: props.rows.filter((row) => typeof row[dimension.key] === 'number' && Number.isFinite(row[dimension.key])).length,
  comparable: props.rows.filter((row) => typeof row[`${dimension.key}Score`] === 'number' && Number.isFinite(row[`${dimension.key}Score`])).length,
})))
const singletonObservations = computed(() => props.dimensions.flatMap((dimension) => {
  const observations = props.rows.filter((row) => typeof row[dimension.key] === 'number' && Number.isFinite(row[dimension.key]))
  if (observations.length !== 1) return []
  const row = observations[0]
  if (!row) return []
  const sample = dimension.sampleKey ? row[dimension.sampleKey] : null
  return [{
    key: dimension.key,
    label: dimension.label,
    repository: String(row.repository ?? ''),
    color: String(row.color ?? '#64748b'),
    raw: row[dimension.key] as number,
    sampleCount: typeof sample === 'number' ? sample : null,
  }]
}))

function toggleSeries(label: string) {
  const next = new Set(hiddenSeries.value)
  if (next.has(label)) next.delete(label)
  else next.add(label)
  hiddenSeries.value = next
}

function qualityLabel(value: string | null) {
  if (value === 'ready') return '数据可用'
  if (value === 'partial') return '部分采集（仅已观察数）'
  if (value === 'insufficient_samples') return '样本不足'
  if (value === 'missing') return '未采集'
  return value ?? '—'
}

function formatRaw(key: string, value: unknown) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '无可用数据'
  const amount = Number(value.toFixed(1)).toLocaleString('zh-CN')
  if (key === 'commitsWeekly') return `${amount} 次 / 周`
  if (key === 'issueClosedCount') return `${Math.round(value).toLocaleString('zh-CN')} 个 Issue`
  if (key === 'prMergedCount') return `${Math.round(value).toLocaleString('zh-CN')} 个 PR`
  if (key === 'releaseCount') return `${Math.round(value).toLocaleString('zh-CN')} 次正式 Release`
  if (key === 'activeWeekRatio') return `${amount}%`
  return `${amount} 天`
}

function pointDetails(itemLabel: string, point: (typeof series.value)[number]['points'][number]) {
  const sample = point.sampleTotal !== null
    ? `完整周 ${point.sampleCount ?? 0}/${point.sampleTotal}`
    : point.sampleCount !== null
      ? `有效样本 n=${point.sampleCount}`
      : `数据状态：${qualityLabel(point.quality)}`
  return `${itemLabel} · ${point.label} · 归一值 ${point.score?.toFixed(1) ?? '—'} / 100 · 原值 ${formatRaw(point.key, point.raw)} · ${sample}`
}
</script>

<template>
  <div class="comparison-radar">
    <div class="comparison-radar__stage">
      <svg
        class="comparison-radar__svg"
        :viewBox="`0 0 ${width} ${height}`"
        role="img"
        :aria-label="`仓库多维指标雷达图；当前 ${chartDimensions.length} 项指标可比较，单仓库数据不参与归一`"
      >
        <g class="comparison-radar__grid">
          <polygon v-for="ring in grid" :key="ring.level" :points="ring.points" />
          <line v-for="axis in axes" :key="`${axis.key}-line`" :x1="centerX" :y1="centerY" :x2="axis.point.x" :y2="axis.point.y" />
        </g>

        <g class="comparison-radar__scale" aria-hidden="true">
          <text v-for="ring in grid" :key="`${ring.level}-label`" :x="centerX - 8" :y="ring.labelY" text-anchor="end">{{ ring.level }}</text>
          <text :x="centerX - 8" :y="centerY + 4" text-anchor="end">0</text>
        </g>

        <g v-for="axis in axes" :key="axis.key" class="comparison-radar__axis-label">
          <text :x="axis.labelX" :y="axis.labelY" :text-anchor="axis.textAnchor">{{ axis.label }}</text>
        </g>

        <g v-for="item in visibleSeries" :key="item.label" class="comparison-radar__series">
          <polygon v-if="item.complete" :points="item.polygonPoints" :fill="item.color" fill-opacity="0.045" :stroke="item.color" :stroke-dasharray="item.strokeDasharray" stroke-width="2.2" stroke-linejoin="round" />
          <g v-else>
            <line v-for="edge in item.edges" :key="edge.key" :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2" :stroke="item.color" :stroke-dasharray="item.strokeDasharray" stroke-width="2.4" stroke-linecap="round" />
          </g>
          <template v-for="point in item.points" :key="point.index">
            <g v-if="point.score !== null && point.x !== undefined && point.y !== undefined && point.markerX !== undefined && point.markerY !== undefined">
              <line v-if="point.markerX !== point.x || point.markerY !== point.y" :x1="point.x" :y1="point.y" :x2="point.markerX" :y2="point.markerY" :stroke="item.color" stroke-opacity="0.5" stroke-width="0.8" />
              <circle :cx="point.markerX" :cy="point.markerY" r="4.3" :fill="item.color" stroke="white" stroke-width="1.8">
                <title>{{ pointDetails(item.label, point) }}</title>
              </circle>
            </g>
          </template>
        </g>
      </svg>
      <p v-if="visibleSeries.length === 0" class="comparison-radar__empty">所有仓库已隐藏，点击下方图例可重新显示。</p>
      <p v-else-if="!hasEnoughAxes" class="comparison-radar__empty">雷达形状至少需要 3 项指标能在 2 个以上仓库间比较；单仓有值保留在下方。</p>
    </div>

    <div class="comparison-radar__legend" role="group" aria-label="点击图例聚焦仓库">
      <button
        v-for="item in series"
        :key="item.label"
        type="button"
        class="comparison-radar__legend-item"
        :class="{ 'is-hidden': hiddenSeries.has(item.label) }"
        :aria-pressed="!hiddenSeries.has(item.label)"
        :aria-label="`${hiddenSeries.has(item.label) ? '显示' : '隐藏'} ${item.label}，有值 ${item.measuredCount}/${dimensions.length} 项，可比 ${item.comparableCount}/${chartDimensions.length} 项`"
        :title="`${item.label} · 有值 ${item.measuredCount}/${dimensions.length} 项 · 雷达可比 ${item.comparableCount}/${chartDimensions.length} 项`"
        @click="toggleSeries(item.label)"
      >
        <svg class="comparison-radar__legend-mark" viewBox="0 0 20 10" aria-hidden="true">
          <line x1="0.5" y1="5" x2="19.5" y2="5" :stroke="item.color" :stroke-dasharray="item.strokeDasharray" />
          <circle cx="10" cy="5" r="2.5" :fill="item.color" />
        </svg>
        <span class="comparison-radar__legend-name">{{ item.label }}</span>
        <span class="comparison-radar__legend-count">{{ item.comparableCount }}/{{ chartDimensions.length }} 项</span>
      </button>
    </div>

    <div v-if="singletonObservations.length" class="comparison-radar__singletons" aria-label="仅单个仓库有值的指标">
      <span class="comparison-radar__singletons-title">单仓实测 · 不参与雷达归一</span>
      <div class="comparison-radar__singletons-list">
        <div v-for="item in singletonObservations" :key="item.key" class="comparison-radar__singleton">
          <i :style="{ background: item.color }" aria-hidden="true" />
          <span class="comparison-radar__singleton-name">{{ item.label }} · {{ item.repository }}</span>
          <strong>{{ formatRaw(item.key, item.raw) }}</strong>
          <small>{{ item.sampleCount === null ? `有值 1/${rows.length}` : `样本 n=${item.sampleCount} · 有值 1/${rows.length}` }}</small>
        </div>
      </div>
    </div>

    <div class="comparison-radar__coverage" aria-label="各指标数据覆盖">
      <span class="comparison-radar__coverage-label">指标覆盖</span>
      <span v-for="item in coverage" :key="item.key" class="comparison-radar__coverage-item" :title="`${item.label}：${item.measured} 个仓库有值，${item.comparable} 个仓库参与比较`">
        {{ item.label }} <b>{{ item.measured }}/{{ rows.length }}</b><small>可比 {{ item.comparable }}</small>
      </span>
    </div>
  </div>
</template>

<style scoped>
.comparison-radar { display: flex; min-width: 0; min-height: 0; height: 100%; flex: 1 1 auto; flex-direction: column; gap: 5px; }
.comparison-radar__stage { position: relative; display: flex; min-width: 0; min-height: 0; flex: 1 1 auto; align-items: center; justify-content: center; overflow: hidden; }
.comparison-radar__svg { display: block; width: min(100%, 640px); height: min(100%, 420px); flex: 0 1 auto; overflow: visible; }
.comparison-radar__grid polygon { fill: none; stroke: var(--line, #dce2e7); stroke-width: 1; stroke-dasharray: 4 5; }
.comparison-radar__grid line { stroke: var(--line, #dce2e7); stroke-width: 1; }
.comparison-radar__scale text { fill: var(--muted, #78838d); font-size: 10px; }
.comparison-radar__axis-label text { fill: var(--ink, #27313a); font-size: 12px; font-weight: 600; }
.comparison-radar__legend { display: grid; min-width: 0; flex: 0 0 auto; grid-template-columns: repeat(auto-fit, minmax(min(100%, 175px), 1fr)); gap: 4px 8px; }
.comparison-radar__legend-item { display: flex; min-width: 0; align-items: center; gap: 6px; border: 1px solid var(--line, #dce2e7); border-radius: 7px; background: var(--surface, #fff); padding: 4px 7px; color: var(--ink, #27313a); text-align: left; cursor: pointer; }
.comparison-radar__legend-item:hover, .comparison-radar__legend-item:focus-visible { border-color: var(--accent, #356cf6); outline: none; }
.comparison-radar__legend-item.is-hidden { opacity: 0.52; }
.comparison-radar__legend-mark { width: 20px; height: 10px; flex: 0 0 auto; overflow: visible; }
.comparison-radar__legend-mark line { stroke-width: 1.8; }
.comparison-radar__legend-name { min-width: 0; overflow: hidden; flex: 1 1 auto; font-size: 10.5px; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.comparison-radar__legend-count { flex: 0 0 auto; color: var(--muted, #78838d); font-size: 9.5px; }
.comparison-radar__coverage { display: flex; min-width: 0; flex: 0 0 auto; flex-wrap: wrap; align-items: center; gap: 3px 10px; color: var(--muted, #78838d); font-size: 9.5px; line-height: 1.4; }
.comparison-radar__coverage-label { font-weight: 600; }
.comparison-radar__coverage-item b { color: var(--ink, #27313a); font-weight: 600; }
.comparison-radar__coverage-item small { margin-left: 3px; font-size: 9px; }
.comparison-radar__singletons { display: flex; min-width: 0; flex: 0 0 auto; flex-wrap: wrap; align-items: center; gap: 4px 8px; }
.comparison-radar__singletons-title { color: var(--muted, #78838d); font-size: 9.5px; font-weight: 600; }
.comparison-radar__singletons-list { display: flex; min-width: 0; flex: 1 1 auto; flex-wrap: wrap; gap: 4px; }
.comparison-radar__singleton { display: grid; min-width: 0; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 2px 6px; border: 1px solid var(--line, #dce2e7); border-radius: 6px; background: var(--soft, #f7f8fa); padding: 3px 6px; font-size: 9.5px; }
.comparison-radar__singleton i { grid-row: 1 / span 2; width: 7px; height: 7px; border-radius: 50%; }
.comparison-radar__singleton-name { min-width: 0; overflow: hidden; color: var(--muted, #78838d); text-overflow: ellipsis; white-space: nowrap; }
.comparison-radar__singleton strong { grid-column: 3; grid-row: 1 / span 2; color: var(--ink, #27313a); font-size: 10px; white-space: nowrap; }
.comparison-radar__singleton small { grid-column: 2; color: var(--muted, #78838d); font-size: 8.5px; white-space: nowrap; }
.comparison-radar__empty { position: absolute; inset: 50% auto auto 50%; transform: translate(-50%, -50%); margin: 0; border-radius: 6px; background: var(--surface, #fff); padding: 6px 9px; color: var(--muted, #78838d); font-size: 11px; white-space: nowrap; }
@media (max-width: 520px) {
  .comparison-radar__axis-label text { font-size: 11px; }
  .comparison-radar__legend { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .comparison-radar__legend-count { display: none; }
}
</style>
