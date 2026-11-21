<script setup lang="ts">
import { computed } from 'vue'
import type { G2Spec, ViewComposition } from '@antv/g2'
import type { StarsBucketDatum, StarsPoint } from '@/lib/overviewChartData'
import G2Chart from '@/components/charts/G2Chart.vue'

const props = defineProps<{
  buckets: StarsBucketDatum[]
  points: StarsPoint[]
  total: number
  validCount: number
  invalidCount: number
  selectedBucket: string | null
  selectedRepositoryId: string | null
  filteredIds: string[]
  filteredCount: number
}>()
const emit = defineEmits<{
  toggleBucket: [key: string]
  selectRepository: [id: string]
}>()

const leadingBucket = computed(() => [...props.buckets].filter((bucket) => bucket.count > 0).sort((left, right) => right.count - left.count || left.min - right.min)[0] ?? null)
const filteredSet = computed(() => new Set(props.filteredIds))
const chartPoints = computed(() => props.points.map((point, dataIndex) => ({
  ...point,
  dataIndex,
  sourceIndex: dataIndex,
})))
const selectedPoints = computed(() => chartPoints.value.filter((point) => point.repositoryId === props.selectedRepositoryId))
const emphasizedPoints = computed(() => chartPoints.value.filter((point) => point.repositoryId !== props.selectedRepositoryId && (
  props.selectedBucket ? point.bucketKey === props.selectedBucket : filteredSet.value.has(point.repositoryId)
)))
const dimmedPoints = computed(() => chartPoints.value.filter((point) => point.repositoryId !== props.selectedRepositoryId && !emphasizedPoints.value.includes(point)))
const maxPlot = computed(() => Math.max(1, ...props.points.map((point) => point.xPlot)))
const pointTooltip = computed(() => ({
  title: 'fullName',
  items: [
    { field: 'stars', name: 'Stars', valueFormatter: (value: number) => Number(value).toLocaleString('zh-CN') },
    { field: 'bucketKey', name: '区间', valueFormatter: (value: string) => props.buckets.find((bucket) => bucket.key === value)?.label ?? value },
  ],
}))
const pointChildren = computed<NonNullable<ViewComposition['children']>>(() => [
  ...(dimmedPoints.value.length ? [{
    type: 'point' as const,
    data: dimmedPoints.value,
    encode: { x: 'xPlot', y: 'lane', color: 'bucketKey', shape: 'point', size: 6 },
    style: { fillOpacity: 0.2, stroke: '#ffffff', lineWidth: 1.4 },
    tooltip: pointTooltip.value,
  }] : []),
  ...(emphasizedPoints.value.length ? [{
    type: 'point' as const,
    data: emphasizedPoints.value,
    encode: { x: 'xPlot', y: 'lane', color: 'bucketKey', shape: 'point', size: 6 },
    style: { fillOpacity: 0.9, stroke: '#ffffff', lineWidth: 1.4 },
    tooltip: pointTooltip.value,
  }] : []),
  ...(selectedPoints.value.length ? [{
    type: 'point' as const,
    data: selectedPoints.value,
    encode: { x: 'xPlot', y: 'lane', color: 'bucketKey', shape: 'point', size: 9 },
    style: { fillOpacity: 1, stroke: '#ffffff', lineWidth: 2 },
    tooltip: pointTooltip.value,
  }] : []),
])
const spec = computed<G2Spec>(() => ({
  type: 'view',
  scale: {
    x: { domain: [0, maxPlot.value] },
    y: { domain: [0, 1] },
    color: { domain: props.buckets.map((bucket) => bucket.key), range: props.buckets.map((bucket) => bucket.color) },
  },
  children: pointChildren.value,
  axis: {
    x: {
      title: 'Stars（log1p 位置）',
      labelFormatter: (value: unknown) => formatStarsTick(value),
      labelFontSize: 10,
      grid: false,
    },
    y: false,
  },
  legend: false,
  interaction: { elementHighlight: true, tooltip: { shared: false } },
}))

function formatStarsTick(value: unknown) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return ''
  const actual = Math.max(0, Math.expm1(numeric))
  if (actual >= 1_000_000) return `${(actual / 1_000_000).toLocaleString('zh-CN', { maximumFractionDigits: 1 })}m`
  if (actual >= 1_000) return `${(actual / 1_000).toLocaleString('zh-CN', { maximumFractionDigits: 1 })}k`
  return Math.round(actual).toLocaleString('zh-CN')
}

function selectPoint(payload: { datum: Record<string, unknown> }) {
  const id = payload.datum.repositoryId
  if (typeof id === 'string') emit('selectRepository', id)
}

function toggleBucket(key: string) {
  emit('toggleBucket', key)
}
</script>

<template>
  <UiPanel as="article" class="chart-panel stars-panel" aria-labelledby="overview-stars-title">
    <div class="panel-heading">
      <div><h2 id="overview-stars-title" class="panel-title">Stars 关注度分层</h2><p class="panel-description">按区间展示仓库数；长尾使用对数位置</p></div>
      <span class="chart-sample mono">n={{ validCount }} / {{ total }}</span>
    </div>
    <div v-if="filteredCount !== total" class="chart-scope">当前筛选 {{ filteredCount }} / {{ total }}</div>
    <div v-if="leadingBucket" class="stars-lead">
      <div><span class="stars-lead-label">最大档位</span><strong>{{ leadingBucket.label }} <span>· {{ leadingBucket.percent.toFixed(1) }}%</span></strong></div>
      <span class="stars-lead-count mono">{{ leadingBucket.count }} <small>/ {{ validCount }} 个有效样本</small></span>
    </div>
    <div v-else class="stars-lead stars-lead--empty"><strong>暂无有效 Stars 数值</strong><span>未收录的数据不会按 0 计入。</span></div>

    <div v-if="validCount" class="stars-stack" role="img" :aria-label="`Stars 档位 100% 堆叠条，有效样本 ${validCount} 个`">
      <span
        v-for="bucket in buckets"
        :key="bucket.key"
        class="stars-stack-segment"
        :class="{ 'is-dimmed': selectedBucket && selectedBucket !== bucket.key }"
        :style="{ width: `${bucket.percent}%`, backgroundColor: bucket.color }"
        :title="`${bucket.label}: ${bucket.count} 个仓库，占有效 Stars 的 ${bucket.percent.toFixed(1)}%`"
      />
    </div>
    <div v-if="validCount" class="stars-legend" role="group" aria-label="选择 Stars 档位筛选仓库">
      <button v-for="bucket in buckets" :key="bucket.key" type="button" class="stars-legend-item" :class="{ 'is-selected': selectedBucket === bucket.key, 'is-dimmed': selectedBucket && selectedBucket !== bucket.key }" :aria-pressed="selectedBucket === bucket.key" @click="toggleBucket(bucket.key)">
        <i :style="{ backgroundColor: bucket.color }" />
        <span>{{ bucket.label }}</span>
        <strong class="mono">{{ bucket.count }}</strong>
        <small class="mono">{{ bucket.percent.toFixed(1) }}%</small>
      </button>
    </div>

    <div v-if="validCount" class="stars-dot-section">
      <div class="stars-dot-heading"><span>每个点代表一个仓库</span><span>0 与缺失分开处理</span></div>
      <G2Chart :spec="spec" label="每个仓库的 Stars 对数点阵图，点的纵向位置仅用于避免重叠" :height="132" @select="selectPoint" />
    </div>
    <div v-else class="chart-empty">当前组合没有有效 Stars 样本</div>

    <p class="chart-note">百分比分母为 {{ validCount }} 个有效 Stars 样本；缺失 {{ total - validCount }} 个<span v-if="invalidCount">，无效值 {{ invalidCount }} 个</span>。点阵纵向位置仅用于排布，没有指标含义。</p>
  </UiPanel>
</template>

<style scoped>
.chart-panel { min-width: 0; }
.chart-scope { margin-top: 8px; color: var(--primary-ink); font-size: 10px; }
.stars-lead { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; margin: 16px 0 13px; }
.stars-lead > div { display: grid; gap: 3px; }
.stars-lead-label { color: var(--muted); font-size: 10px; }
.stars-lead strong { color: var(--ink); font-size: 17px; font-weight: 650; letter-spacing: -.02em; }
.stars-lead strong span { color: var(--primary-ink); font-size: 14px; font-variant-numeric: tabular-nums; }
.stars-lead-count { color: var(--ink); font-size: 15px; font-weight: 650; }
.stars-lead-count small { color: var(--muted); font-size: 10px; font-weight: 400; }
.stars-lead--empty { min-height: 55px; align-items: center; }
.stars-lead--empty strong { font-size: 13px; }
.stars-lead--empty > span { color: var(--muted); font-size: 10px; }
.stars-stack { display: flex; width: 100%; height: 17px; overflow: hidden; border-radius: 999px; background: var(--surface-soft); }
.stars-stack-segment { display: block; height: 100%; min-width: 0; transition: opacity 150ms ease; }
.stars-stack-segment.is-dimmed { opacity: .28; }
.stars-legend { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 3px 6px; margin-top: 10px; }
.stars-legend-item { display: grid; grid-template-columns: 7px minmax(0, 1fr) auto; align-items: center; gap: 5px; min-width: 0; padding: 5px 4px; border: 1px solid transparent; border-radius: 6px; color: var(--ink); background: transparent; text-align: left; cursor: pointer; }
.stars-legend-item:hover, .stars-legend-item:focus-visible { background: var(--surface-soft); }
.stars-legend-item.is-selected { border-color: color-mix(in srgb, var(--primary) 35%, var(--line)); background: var(--primary-soft); }
.stars-legend-item.is-dimmed { opacity: .55; }
.stars-legend-item i { width: 7px; height: 7px; border-radius: 50%; }
.stars-legend-item span, .stars-legend-item strong, .stars-legend-item small { overflow: hidden; font-size: 9.5px; text-overflow: ellipsis; white-space: nowrap; }
.stars-legend-item strong { font-weight: 600; }
.stars-legend-item small { grid-column: 2 / -1; justify-self: end; color: var(--muted); }
.stars-dot-section { margin-top: 12px; padding-top: 9px; border-top: 1px solid var(--line); }
.stars-dot-heading { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 0; color: var(--muted); font-size: 9.5px; }
.chart-note { margin: 8px 0 0; color: var(--muted); font-size: 10px; line-height: 1.5; }
.chart-empty { display: grid; min-height: 130px; place-items: center; color: var(--muted); font-size: 11px; }
@media (max-width: 600px) { .stars-lead { align-items: flex-start; flex-direction: column; gap: 5px; } .stars-legend { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (prefers-reduced-motion: reduce) { .stars-stack-segment { transition: none; } }
</style>
