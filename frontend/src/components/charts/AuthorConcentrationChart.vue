<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { G2Spec } from '@antv/g2'
import { summarizeAuthorDistribution, type AuthorDistributionBucket } from '@/lib/authorConcentration'
import type { AuthorContribution } from '@/services/types'
import G2Chart from './G2Chart.vue'

const props = defineProps<{
  authors: AuthorContribution[]
  distribution: AuthorDistributionBucket[] | null
  totalCommits: number
  unidentifiedCommitCount: number | null
}>()
const emit = defineEmits<{ 'select-author': [author: string] }>()
const chartRegion = ref<HTMLDivElement | null>(null)
const chartRegionSize = ref({ width: 0, height: 0 })
let chartRegionObserver: ResizeObserver | null = null

const distribution = computed(() => {
  if (props.distribution === null || props.unidentifiedCommitCount === null) return null
  const buckets = [...props.distribution].sort((a, b) => a.commits - b.commits)
  const knownCommits = buckets.reduce((sum, bucket) => sum + bucket.commits * bucket.authors, 0)
  if (knownCommits + props.unidentifiedCommitCount !== props.totalCommits) return null
  return buckets
})

const stats = computed(() => distribution.value ? summarizeAuthorDistribution(distribution.value) : null)
const chartHeight = computed(() => Math.max(170, Math.min(360, chartRegionSize.value.height - 32, chartRegionSize.value.width * 0.82)))

onMounted(() => {
  if (!chartRegion.value) return
  const updateSize = (width: number, height: number) => {
    chartRegionSize.value = { width: Math.round(width), height: Math.round(height) }
  }
  updateSize(chartRegion.value.clientWidth, chartRegion.value.clientHeight)
  chartRegionObserver = new ResizeObserver(([entry]) => {
    updateSize(entry.contentRect.width, entry.contentRect.height)
  })
  chartRegionObserver.observe(chartRegion.value)
})

onBeforeUnmount(() => chartRegionObserver?.disconnect())

const spec = computed<G2Spec>(() => {
  const points = stats.value?.points.map((point) => ({ x: point.value[0], y: point.value[1], authors: point.authors, commits: point.commits })) ?? []
  return {
    type: 'view', scale: { x: { domain: [0, 100] }, y: { domain: [0, 100] } },
    axis: { x: { title: '累计作者 %' }, y: { title: '累计提交 %', gridLineDash: [3, 3] } },
    children: [
      { type: 'line', data: [{ x: 0, y: 0 }, { x: 100, y: 100 }], encode: { x: 'x', y: 'y' }, style: { stroke: '#77848e', lineDash: [4, 3], lineWidth: 1 } },
      { type: 'line', data: points, encode: { x: 'x', y: 'y' }, style: { stroke: '#2e8fcb', lineWidth: 2.5 } },
    ],
    interaction: { tooltip: { shared: true } },
    tooltip: { items: [{ field: 'authors', name: '累计作者' }, { field: 'commits', name: '累计提交' }] },
  }
})
</script>

<template>
  <div class="grid h-full min-h-0 grid-cols-[minmax(0,1fr)_minmax(138px,38%)] gap-3" data-testid="author-concentration">
    <div ref="chartRegion" class="flex min-h-0 min-w-0 flex-col">
      <div class="flex items-center justify-between gap-2 text-[11px]">
        <span class="font-medium">洛伦兹曲线</span>
        <span class="text-muted">可识别作者</span>
      </div>
      <G2Chart v-if="stats" :spec="spec" label="作者贡献洛伦兹曲线；虚线为均等参考" :height="chartHeight" />
      <div v-else class="flex min-h-0 flex-1 items-center justify-center rounded-md bg-soft px-3 text-center text-[11px] leading-relaxed text-muted">
        {{ distribution === null ? '作者分布不可用，请刷新或重启后端。' : '没有可识别作者的提交，无法计算集中度。' }}
      </div>
      <div v-if="stats" class="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted">
        <span><i class="mr-1 inline-block w-3 border-t-2 border-dashed border-muted align-middle" />均等参考</span>
        <span><i class="mr-1 inline-block w-3 border-t-2 border-[#2e8fcb] align-middle" />实际分布</span>
      </div>
    </div>

    <div class="flex min-h-0 min-w-0 flex-col">
      <div v-if="stats" class="grid grid-cols-2 gap-2 border-b border-line pb-2">
        <div>
          <div class="text-[10px] text-muted" title="根据可识别作者的提交次数计算，不衡量代码量或贡献质量">基尼系数</div>
          <div class="font-mono text-[19px] font-semibold leading-tight">{{ stats.gini.toFixed(2) }}</div>
          <div class="text-[10px] text-muted">越接近 1 越集中</div>
        </div>
        <div>
          <div class="text-[10px] text-muted">贡献一半提交</div>
          <div class="font-mono text-[19px] font-semibold leading-tight">{{ stats.contributors }} <span class="text-[11px] font-normal">位</span></div>
          <div class="text-[10px] text-muted">共 {{ stats.authors }} 位可识别作者</div>
        </div>
      </div>
      <div class="flex items-center justify-between py-2 text-[10.5px] text-muted"><span>提交数排行</span><span>次</span></div>
      <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1" role="region" aria-label="提交数排行，可滚动查看全部作者" tabindex="0">
        <button v-for="(author, index) in authors" :key="`${author.author}-${index}`" type="button" class="flex w-full items-center gap-2 rounded px-1 py-1 text-left text-[11px] hover:bg-soft focus-visible:bg-soft" :title="`搜索 ${author.author} 的 Commit`" @click="emit('select-author', author.author)">
          <span class="w-4 shrink-0 font-mono text-[10px] text-muted">{{ index + 1 }}</span>
          <span class="min-w-0 flex-1 truncate">{{ author.author }}<span v-if="author.isBot" class="ml-1 text-[9px] text-muted">Bot</span></span>
          <span class="shrink-0 font-mono">{{ author.commits }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
