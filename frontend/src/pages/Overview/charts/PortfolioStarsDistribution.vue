<script setup lang="ts">
import { computed } from 'vue'
import type { StarsBucketDatum } from '@/lib/overviewChartData'

const props = defineProps<{
  buckets: StarsBucketDatum[]
  total: number
  validCount: number
  invalidCount: number
  selectedBucket: string | null
  filteredCount: number
}>()
const emit = defineEmits<{
  toggleBucket: [key: string]
}>()

const leadingBucket = computed(() => [...props.buckets].filter((bucket) => bucket.count > 0).sort((left, right) => right.count - left.count || left.min - right.min)[0] ?? null)

function toggleBucket(key: string) {
  emit('toggleBucket', key)
}
</script>

<template>
  <UiPanel as="article" class="chart-panel stars-panel" aria-labelledby="overview-stars-title">
    <div class="panel-heading">
      <div><h2 id="overview-stars-title" class="panel-title">Stars 关注度分层</h2><p class="panel-description">按 Stars 区间展示仓库数与有效样本占比</p></div>
      <span class="chart-sample mono">n={{ validCount }} / {{ total }}</span>
    </div>
    <div v-if="filteredCount !== total" class="chart-scope">当前筛选 {{ filteredCount }} / {{ total }}</div>
    <div v-if="leadingBucket" class="stars-lead">
      <div><span class="stars-lead-label">最大档位</span><strong>{{ leadingBucket.label }} <span>· {{ leadingBucket.percent.toFixed(1) }}%</span></strong></div>
      <span class="stars-lead-count mono">{{ leadingBucket.count }} <small>/ {{ validCount }} 个有效样本</small></span>
    </div>
    <div v-else class="stars-lead stars-lead--empty"><strong>暂无有效 Stars 数值</strong><span>未收录的数据不会按 0 计入。</span></div>

    <div v-if="validCount" class="stars-legend" role="group" aria-label="选择 Stars 档位筛选仓库">
      <button v-for="bucket in buckets" :key="bucket.key" type="button" class="stars-legend-item" :class="{ 'is-selected': selectedBucket === bucket.key, 'is-dimmed': selectedBucket && selectedBucket !== bucket.key }" :aria-pressed="selectedBucket === bucket.key" :title="`${bucket.label}: ${bucket.count} 个仓库，占有效 Stars 的 ${bucket.percent.toFixed(1)}%`" @click="toggleBucket(bucket.key)">
        <i :style="{ backgroundColor: bucket.color }" />
        <span>{{ bucket.label }}</span>
        <span class="stars-legend-track" aria-hidden="true"><i :style="{ width: `${bucket.percent}%`, backgroundColor: bucket.color }" /></span>
        <strong class="mono">{{ bucket.count }}</strong>
        <small class="mono">{{ bucket.percent.toFixed(1) }}%</small>
      </button>
    </div>

    <div v-if="!validCount" class="chart-empty">当前组合没有有效 Stars 样本</div>

    <p class="chart-note">百分比分母为 {{ validCount }} 个有效 Stars 样本；缺失 {{ total - validCount }} 个<span v-if="invalidCount">，无效值 {{ invalidCount }} 个</span>。</p>
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
.stars-legend { display: grid; gap: 4px; margin-top: 10px; }
.stars-legend-item { display: grid; grid-template-columns: 7px minmax(58px, 82px) minmax(0, 1fr) auto 40px; align-items: center; gap: 8px; min-width: 0; min-height: 25px; padding: 3px 5px; border: 1px solid transparent; border-radius: 6px; color: var(--ink); background: transparent; text-align: left; cursor: pointer; }
.stars-legend-item:hover, .stars-legend-item:focus-visible { background: var(--surface-soft); }
.stars-legend-item.is-selected { border-color: color-mix(in srgb, var(--primary) 35%, var(--line)); background: var(--primary-soft); }
.stars-legend-item.is-dimmed { opacity: .55; }
.stars-legend-item i { width: 7px; height: 7px; border-radius: 50%; }
.stars-legend-item > span:not(.stars-legend-track), .stars-legend-item strong, .stars-legend-item small { overflow: hidden; font-size: 9.5px; text-overflow: ellipsis; white-space: nowrap; }
.stars-legend-track { height: 4px; overflow: hidden; border-radius: 999px; background: var(--surface-soft); }
.stars-legend-track i { display: block; height: 100%; min-width: 0; border-radius: inherit; }
.stars-legend-item strong { font-weight: 600; }
.stars-legend-item small { justify-self: end; color: var(--muted); }
.chart-note { margin: 8px 0 0; color: var(--muted); font-size: 10px; line-height: 1.5; }
.chart-empty { display: grid; min-height: 130px; place-items: center; color: var(--muted); font-size: 11px; }
@media (max-width: 600px) { .stars-lead { align-items: flex-start; flex-direction: column; gap: 5px; } .stars-legend-item { grid-template-columns: 7px 58px minmax(0, 1fr) auto 37px; gap: 5px; } }
</style>
