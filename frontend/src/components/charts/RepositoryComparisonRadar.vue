<script setup lang="ts">
import { computed } from 'vue'

type Dimension = { key: string; label: string }
type RadarRow = Record<string, string | number | null>

const props = defineProps<{
  rows: RadarRow[]
  dimensions: Dimension[]
}>()

const width = 620
const height = 410
const centerX = 310
const centerY = 198
const radius = 132
const labelRadius = radius + 27
const gridLevels = [20, 40, 60, 80, 100]

function axisPoint(index: number, level = 100) {
  const angle = (Math.PI * 2 * index) / props.dimensions.length - Math.PI / 2
  const distance = radius * level / 100
  return {
    x: centerX + Math.cos(angle) * distance,
    y: centerY + Math.sin(angle) * distance,
  }
}

const grid = computed(() => gridLevels.map((level) => ({
  level,
  points: props.dimensions.map((_, index) => axisPoint(index, level)).map(({ x, y }) => `${x},${y}`).join(' '),
  labelY: centerY - radius * level / 100 + 4,
})))

const axes = computed(() => props.dimensions.map((dimension, index) => {
  const angle = (Math.PI * 2 * index) / props.dimensions.length - Math.PI / 2
  const point = axisPoint(index)
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

const series = computed(() => props.rows.map((row) => {
  const points = props.dimensions.map((dimension, index) => {
    const raw = row[dimension.key]
    const score = row[`${dimension.key}Score`]
    const coordinates = typeof score === 'number' && Number.isFinite(score)
      ? axisPoint(index, Math.max(0, Math.min(100, score)))
      : null
    return {
      index,
      label: dimension.label,
      raw,
      score: typeof score === 'number' && Number.isFinite(score) ? score : null,
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
    polygonPoints: complete ? points.map((point) => `${point.x},${point.y}`).join(' ') : '',
    available: points.filter((point) => point.score !== null).length,
  }
}))

function formatRaw(key: string, value: unknown) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '无可用数据'
  const amount = Number(value.toFixed(1)).toLocaleString('zh-CN')
  if (key === 'commitsWeekly') return `${amount} 次 / 周`
  if (key === 'activeWeekRatio') return `${amount}%`
  return `${amount} 天`
}
</script>

<template>
  <div class="comparison-radar">
    <div class="comparison-radar__stage">
      <svg
        class="comparison-radar__svg"
        :viewBox="`0 0 ${width} ${height}`"
        role="img"
        aria-label="所有已选仓库的多维指标雷达图；颜色区分仓库，空缺指标不补值"
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

        <g v-for="item in series" :key="item.label" class="comparison-radar__series">
          <polygon v-if="item.complete" :points="item.polygonPoints" :fill="item.color" fill-opacity="0.09" :stroke="item.color" stroke-width="2.2" stroke-linejoin="round" />
          <g v-else>
            <line v-for="edge in item.edges" :key="edge.key" :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2" :stroke="item.color" stroke-width="2.4" stroke-linecap="round" />
          </g>
          <template v-for="point in item.points" :key="point.index">
            <circle v-if="point.score !== null && point.x !== undefined && point.y !== undefined" :cx="point.x" :cy="point.y" r="4.5" :fill="item.color" stroke="white" stroke-width="1.8">
              <title>{{ item.label }} · {{ point.label }} · 归一值 {{ point.score.toFixed(1) }} / 100 · 原值 {{ formatRaw(props.dimensions[point.index].key, point.raw) }}</title>
            </circle>
          </template>
        </g>
      </svg>
    </div>

    <ul class="comparison-radar__legend" aria-label="参与对比的仓库">
      <li v-for="item in series" :key="item.label" :title="item.label">
        <span class="comparison-radar__swatch" :style="{ '--series-color': item.color }" aria-hidden="true" />
        <span class="comparison-radar__legend-name">{{ item.label }}</span>
        <span class="comparison-radar__coverage">{{ item.available }} / {{ dimensions.length }} 项</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.comparison-radar { display: grid; gap: 8px; min-width: 0; }
.comparison-radar__stage { display: flex; justify-content: center; min-width: 0; }
.comparison-radar__svg { display: block; width: min(100%, 760px); height: auto; overflow: visible; }
.comparison-radar__grid polygon { fill: none; stroke: var(--line, #dce2e7); stroke-width: 1; stroke-dasharray: 4 5; }
.comparison-radar__grid line { stroke: var(--line, #dce2e7); stroke-width: 1; }
.comparison-radar__scale text { fill: var(--muted, #78838d); font-size: 10px; }
.comparison-radar__axis-label text { fill: var(--ink, #27313a); font-size: 12px; font-weight: 600; }
.comparison-radar__legend { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 7px 12px; margin: 0; padding: 0; list-style: none; }
.comparison-radar__legend li { display: flex; min-width: 0; align-items: center; gap: 8px; padding: 7px 9px; border: 1px solid var(--line, #dce2e7); border-radius: 8px; background: var(--surface-soft, #f8f9fa); font-size: 11px; }
.comparison-radar__swatch { width: 11px; height: 11px; flex: 0 0 auto; border: 2px solid var(--series-color); border-radius: 50%; background: color-mix(in srgb, var(--series-color) 18%, white); }
.comparison-radar__legend-name { overflow: hidden; flex: 1 1 auto; color: var(--ink, #27313a); font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.comparison-radar__coverage { flex: 0 0 auto; color: var(--muted, #78838d); font-variant-numeric: tabular-nums; font-size: 10px; }
@media (max-width: 520px) {
  .comparison-radar__axis-label text { font-size: 11px; }
  .comparison-radar__legend { grid-template-columns: 1fr; }
}
</style>
