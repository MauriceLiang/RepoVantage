<script setup lang="ts">
import { computed, ref } from 'vue'
import type { PushBucketKey, PushPoint } from '@/lib/overviewChartData'

const props = defineProps<{
  points: PushPoint[]
  total: number
  active30Count: number
  active30Rate: number
  missingCount: number
  invalidCount: number
  futureCount: number
  filteredCount: number
  selectedBucket: PushBucketKey | null
  selectedRepositoryId: string | null
  filteredIds: string[]
}>()
const emit = defineEmits<{ toggleBucket: [key: PushBucketKey]; selectRepository: [id: string] }>()
const expanded = ref(false)

const bucketLabels: Array<{ key: PushBucketKey; label: string }> = [
  { key: '7d', label: '近 7 天' }, { key: '30d', label: '8–30 天' }, { key: '90d', label: '31–90 天' },
  { key: '365d', label: '91–365 天' }, { key: 'older', label: '超过 1 年' }, { key: 'missing', label: '无日期' }, { key: 'future', label: '时间异常' },
]
const filteredSet = computed(() => new Set(props.filteredIds))
const datedPoints = computed(() => props.points.filter((point) => point.ageDays !== null && point.bucketKey !== 'future'))
const missingPoints = computed(() => props.points.filter((point) => point.bucketKey === 'missing'))
const futurePoints = computed(() => props.points.filter((point) => point.bucketKey === 'future'))
const visiblePoints = computed(() => {
  const limit = props.points.length <= 20 ? props.points.length : 15
  return expanded.value ? datedPoints.value : datedPoints.value.slice(0, limit)
})
const remainingCount = computed(() => Math.max(0, datedPoints.value.length - visiblePoints.value.length))
const bucketCounts = computed(() => Object.fromEntries(bucketLabels.map(({ key }) => [key, props.points.filter((point) => point.bucketKey === key).length])) as Record<PushBucketKey, number>)
const ticks = [0, 7, 30, 90, 365]

function tickPosition(day: number) { return `${day / 365 * 100}%` }
function pointPosition(point: PushPoint) { return `${Math.max(0, Math.min(365, point.ageDays ?? 0)) / 365 * 100}%` }
function ageLabel(point: PushPoint) {
  if (point.ageDays === null) return '日期无效'
  if (point.ageDays < 1) return `${Math.max(0, Math.round(point.ageDays * 24))} 小时前`
  return `${point.ageDays.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 天前`
}
function preciseDate(value: string | null) {
  if (!value) return '无 Push 日期'
  const timestamp = Date.parse(value)
  if (!Number.isFinite(timestamp)) return `无法解析日期：${value}`
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'UTC', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(timestamp) + ' UTC'
}
function bucketLabel(key: PushBucketKey) { return bucketLabels.find((bucket) => bucket.key === key)?.label ?? key }
</script>

<template>
  <UiPanel as="article" class="chart-panel push-panel" aria-labelledby="overview-push-title">
    <div class="panel-heading">
      <div><h2 id="overview-push-title" class="panel-title">最近 Push 活跃度</h2><p class="panel-description">展示每个仓库最近一次 Push 快照，不代表 Push 次数</p></div>
      <span class="chart-sample mono">{{ total }} 个仓库</span>
    </div>
    <div class="push-summary">
      <div class="push-rate"><strong>{{ active30Rate.toFixed(1) }}%</strong><span>近 30 天活跃率</span></div>
      <p><b>{{ active30Count }} / {{ total }}</b> 个仓库有最近 Push；无日期和未来时间仍计入总分母。</p>
    </div>
    <div class="push-filter-row" role="group" aria-label="按最近 Push 时间分组筛选">
      <button v-for="bucket in bucketLabels" :key="bucket.key" type="button" class="push-filter-chip" :class="{ 'is-selected': selectedBucket === bucket.key, 'is-dimmed': selectedBucket && selectedBucket !== bucket.key }" :aria-pressed="selectedBucket === bucket.key" @click="emit('toggleBucket', bucket.key)">
        <span>{{ bucket.label }}</span><strong class="mono">{{ bucketCounts[bucket.key] }}</strong>
      </button>
    </div>
    <div v-if="filteredCount !== total" class="chart-scope">当前筛选 {{ filteredCount }} / {{ total }} 个仓库</div>
    <div class="push-timeline" role="group" aria-label="各仓库最近 Push 时间点，距今 0 到 365 天；更早的日期停在 365 天刻度">
      <div class="push-axis-row">
        <span class="push-axis-caption">仓库</span>
        <div class="push-axis"><span v-for="tick in ticks" :key="tick" :style="{ left: tickPosition(tick) }">{{ tick === 365 ? '365+' : tick }}<small>天</small></span></div>
        <span class="push-axis-caption push-axis-caption--end">最近 Push（UTC）</span>
      </div>
      <div v-if="visiblePoints.length" class="push-time-list" role="list" aria-label="有有效 Push 日期的仓库">
        <button v-for="point in visiblePoints" :key="point.repositoryId" type="button" role="listitem" class="push-time-row" :class="{ 'is-selected': selectedRepositoryId === point.repositoryId, 'is-dimmed': !filteredSet.has(point.repositoryId) }" :aria-label="`${point.fullName}，${preciseDate(point.pushedAt)}，${ageLabel(point)}，${bucketLabel(point.bucketKey)}`" :title="`${point.fullName} · ${preciseDate(point.pushedAt)} · ${ageLabel(point)} · ${bucketLabel(point.bucketKey)}`" @click="emit('selectRepository', point.repositoryId)">
          <span class="push-repo-name">{{ point.fullName }}</span>
          <span class="push-track"><i class="push-guide" :style="{ left: tickPosition(7) }" /><i class="push-guide" :style="{ left: tickPosition(30) }" /><i class="push-guide" :style="{ left: tickPosition(90) }" /><i class="push-guide" :style="{ left: tickPosition(365) }" /><i class="push-lollipop-stem" :style="{ width: pointPosition(point), backgroundColor: point.bucketKey === '7d' ? 'var(--green)' : 'var(--primary)' }" /><i class="push-lollipop-dot" :style="{ left: pointPosition(point), backgroundColor: point.bucketKey === '7d' ? 'var(--green)' : 'var(--primary)' }" /></span>
          <span class="push-date"><strong>{{ ageLabel(point) }}</strong><small>{{ preciseDate(point.pushedAt) }}</small></span>
        </button>
      </div>
      <p v-else class="push-empty">当前筛选没有可绘制的 Push 时间点。</p>
      <button v-if="remainingCount > 0" type="button" class="show-more" @click="expanded = true">查看更多 {{ remainingCount }} 个仓库</button>
      <button v-else-if="expanded && datedPoints.length > 15" type="button" class="show-more" @click="expanded = false">收起列表</button>
    </div>
    <div v-if="missingPoints.length || futurePoints.length" class="push-exceptions">
      <section v-if="missingPoints.length" class="push-exception-group">
        <h3>无有效日期 <span>{{ missingPoints.length }}</span><small v-if="invalidCount">（含 {{ invalidCount }} 条格式无效）</small></h3>
        <div class="exception-repos"><button v-for="point in missingPoints.slice(0, 8)" :key="point.repositoryId" type="button" :class="{ 'is-selected': selectedRepositoryId === point.repositoryId }" @click="emit('selectRepository', point.repositoryId)">{{ point.fullName }}</button><span v-if="missingPoints.length > 8">另有 {{ missingPoints.length - 8 }} 个</span></div>
      </section>
      <section v-if="futurePoints.length" class="push-exception-group push-exception-group--warning">
        <h3>时间异常（未来日期） <span>{{ futurePoints.length }}</span></h3>
        <div class="exception-repos"><button v-for="point in futurePoints.slice(0, 8)" :key="point.repositoryId" type="button" :title="preciseDate(point.pushedAt)" :class="{ 'is-selected': selectedRepositoryId === point.repositoryId }" @click="emit('selectRepository', point.repositoryId)">{{ point.fullName }}</button><span v-if="futurePoints.length > 8">另有 {{ futurePoints.length - 8 }} 个</span></div>
      </section>
    </div>
    <p class="chart-note">最近 30 天活跃率 = {{ active30Count }} / {{ total }}；时间统一按本次页面计算时刻和 UTC 时间戳统计。{{ futureCount ? `未来日期 ${futureCount} 个单独提示，不计为活跃。` : '' }}{{ missingCount ? `无日期 ${missingCount} 个不落在 0 天位置。` : '' }}</p>
  </UiPanel>
</template>

<style scoped>
.chart-panel { min-width: 0; }
.chart-sample { color: var(--muted); font-size: 10.5px; white-space: nowrap; }
.push-summary { display: flex; align-items: center; gap: 18px; margin: 14px 0 12px; padding-bottom: 12px; border-bottom: 1px solid var(--line); }
.push-rate { display: grid; flex: none; gap: 2px; }
.push-rate strong { color: var(--ink); font-size: 26px; font-variant-numeric: tabular-nums; line-height: 1; }
.push-rate span { color: var(--muted); font-size: 10px; }
.push-summary p { max-width: 460px; margin: 0; color: var(--muted); font-size: 10.5px; line-height: 1.5; }
.push-summary p b { color: var(--ink); font-variant-numeric: tabular-nums; }
.push-filter-row { display: flex; flex-wrap: wrap; gap: 5px; }
.push-filter-chip { display: inline-flex; align-items: center; gap: 6px; padding: 5px 7px; border: 1px solid var(--line); border-radius: 6px; color: var(--muted); background: transparent; font: inherit; font-size: 9.5px; cursor: pointer; }
.push-filter-chip strong { color: var(--ink); font-size: 9px; }
.push-filter-chip:hover { color: var(--ink); background: var(--surface-soft); }
.push-filter-chip.is-selected { border-color: color-mix(in srgb, var(--primary) 40%, var(--line)); color: var(--primary-ink); background: var(--primary-soft); }
.push-filter-chip.is-selected strong { color: var(--primary-ink); }
.push-filter-chip.is-dimmed { opacity: .55; }
.chart-scope { margin-top: 8px; color: var(--primary-ink); font-size: 10px; }
.push-timeline { margin-top: 14px; }
.push-axis-row, .push-time-row { display: grid; grid-template-columns: minmax(120px, 1fr) minmax(180px, 2.2fr) minmax(128px, 1.1fr); align-items: center; gap: 12px; }
.push-axis-row { padding: 0 7px 8px; color: var(--muted); font-size: 9.5px; }
.push-axis-caption--end { text-align: right; }
.push-axis { position: relative; height: 21px; border-bottom: 1px solid var(--line); }
.push-axis > span { position: absolute; bottom: 2px; transform: translateX(-50%); white-space: nowrap; font-variant-numeric: tabular-nums; }
.push-axis > span:first-child { transform: translateX(0); }
.push-axis > span:last-child { transform: translateX(-100%); }
.push-axis small { margin-left: 2px; font-size: 8px; }
.push-time-list { display: grid; max-height: 480px; overflow-y: auto; overscroll-behavior: contain; }
.push-time-row { width: 100%; min-height: 35px; padding: 5px 7px; border: 0; border-top: 1px solid var(--line); border-radius: 0; color: var(--ink); background: transparent; text-align: left; cursor: pointer; transition: background-color 130ms ease, opacity 130ms ease; }
.push-time-row:hover, .push-time-row:focus-visible { background: var(--surface-soft); }
.push-time-row.is-selected { background: var(--primary-soft); }
.push-time-row.is-dimmed { opacity: .44; }
.push-repo-name { overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.push-track { position: relative; height: 12px; }
.push-track::before { position: absolute; top: 5px; right: 0; left: 0; height: 1px; background: var(--line); content: ''; }
.push-guide { position: absolute; top: 1px; width: 1px; height: 10px; background: var(--line-strong, var(--muted)); opacity: .45; }
.push-lollipop-stem { position: absolute; top: 4px; right: auto; height: 3px; border-radius: 2px; opacity: .56; }
.push-lollipop-dot { position: absolute; top: 1px; width: 9px; height: 9px; border: 2px solid var(--surface); border-radius: 50%; box-shadow: 0 0 0 1px color-mix(in srgb, var(--ink) 12%, transparent); transform: translateX(-50%); }
.push-date { display: grid; justify-items: end; gap: 2px; min-width: 0; text-align: right; }
.push-date strong { font-size: 9.5px; font-weight: 550; white-space: nowrap; }
.push-date small { overflow: hidden; max-width: 100%; color: var(--muted); font-size: 8.5px; text-overflow: ellipsis; white-space: nowrap; }
.push-empty { display: grid; min-height: 90px; place-items: center; color: var(--muted); font-size: 11px; }
.show-more { display: block; margin: 8px auto 0; padding: 5px 8px; border: 1px solid var(--line); border-radius: 6px; color: var(--primary-ink); background: transparent; font: inherit; font-size: 10px; cursor: pointer; }
.show-more:hover { background: var(--primary-soft); }
.push-exceptions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 12px; }
.push-exception-group { min-width: 0; padding-top: 8px; border-top: 1px solid var(--line); }
.push-exception-group h3 { margin: 0 0 6px; color: var(--muted); font-size: 9.5px; font-weight: 600; }
.push-exception-group h3 span { margin-left: 4px; color: var(--ink); font-variant-numeric: tabular-nums; }
.push-exception-group h3 small { font-size: 9px; font-weight: 400; }
.push-exception-group--warning h3 { color: var(--amber, #ab6817); }
.exception-repos { display: flex; flex-wrap: wrap; gap: 4px; }
.exception-repos button { max-width: 180px; overflow: hidden; padding: 3px 5px; border: 1px solid var(--line); border-radius: 5px; color: var(--ink); background: var(--surface-soft); font: inherit; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
.exception-repos button:hover, .exception-repos button.is-selected { color: var(--primary-ink); background: var(--primary-soft); }
.exception-repos > span { color: var(--muted); font-size: 9px; align-self: center; }
.chart-note { margin: 10px 0 0; color: var(--muted); font-size: 10px; line-height: 1.5; }
@media (max-width: 600px) {
  .push-summary { align-items: flex-start; flex-direction: column; gap: 8px; }
  .push-axis-row, .push-time-row { min-width: 470px; grid-template-columns: minmax(98px, .9fr) minmax(190px, 1.5fr) minmax(125px, 1.1fr); gap: 8px; }
  .push-timeline { overflow-x: auto; }
  .push-time-list { max-height: 360px; }
  .push-exceptions { grid-template-columns: 1fr; }
}
@media (prefers-reduced-motion: reduce) { .push-time-row { transition: none; } }
</style>
