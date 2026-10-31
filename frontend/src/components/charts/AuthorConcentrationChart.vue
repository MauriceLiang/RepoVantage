<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import { summarizeAuthorDistribution, type AuthorDistributionBucket } from '@/lib/authorConcentration'
import type { AuthorContribution } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { fontFamily, MONO, chartTheme } from './theme'

const props = defineProps<{
  authors: AuthorContribution[]
  distribution: AuthorDistributionBucket[] | null
  totalCommits: number
  unidentifiedCommitCount: number | null
}>()
const emit = defineEmits<{ 'select-author': [author: string] }>()
const ui = useUiStore()

const distribution = computed(() => {
  if (props.distribution === null || props.unidentifiedCommitCount === null) return null
  const buckets = [...props.distribution].sort((a, b) => a.commits - b.commits)
  const knownCommits = buckets.reduce((sum, bucket) => sum + bucket.commits * bucket.authors, 0)
  if (knownCommits + props.unidentifiedCommitCount !== props.totalCommits) return null
  return buckets
})

const stats = computed(() => distribution.value ? summarizeAuthorDistribution(distribution.value) : null)

const option = computed<EChartsOption>(() => {
  const t = chartTheme(ui.isDark)
  return {
    animation: false,
    grid: { left: 39, right: 14, top: 27, bottom: 37 },
    tooltip: {
      trigger: 'item', backgroundColor: t.panel, borderColor: t.border, borderWidth: 1, padding: [9, 11],
      textStyle: { color: t.ink, fontSize: 11, fontFamily },
      extraCssText: `border-radius:8px;box-shadow:${t.dark ? '0 8px 24px rgba(0,0,0,.5)' : '0 6px 18px rgba(0,0,0,.12)'};`,
      formatter: (params: unknown) => {
        const point = (params as { data?: { authors: number; commits: number; value: number[] } }).data
        if (!point || !stats.value) return ''
        return `<div>累计作者：<b>${point.authors} / ${stats.value.authors}</b>（${point.value[0].toFixed(1)}%）</div><div>累计提交：<b>${point.commits} / ${stats.value.commits}</b>（${point.value[1].toFixed(1)}%）</div>`
      },
    },
    xAxis: {
      type: 'value', min: 0, max: 100, interval: 50, name: '累计作者 %', nameLocation: 'middle', nameGap: 24,
      nameTextStyle: { color: t.muted, fontSize: 10, fontFamily },
      axisLine: { lineStyle: { color: t.border } }, axisTick: { show: false },
      axisLabel: { color: t.muted, fontSize: 9, fontFamily: MONO, formatter: '{value}%' },
      splitLine: { lineStyle: { color: t.grid } },
    },
    yAxis: {
      type: 'value', min: 0, max: 100, interval: 50, name: '累计提交 %',
      nameTextStyle: { color: t.muted, fontSize: 10, fontFamily },
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: t.muted, fontSize: 9, fontFamily: MONO, formatter: '{value}%' },
      splitLine: { lineStyle: { color: t.grid } },
    },
    series: [
      { name: '均等参考', type: 'line', data: [[0, 0], [100, 100]], silent: true, symbol: 'none', z: 4, lineStyle: { color: t.muted, type: 'dashed', width: 1 } },
      {
        name: '实际分布', type: 'line', data: stats.value?.points ?? [], symbol: 'circle', symbolSize: 5, z: 3,
        lineStyle: { color: t.series[3], width: 2.5 }, itemStyle: { color: t.series[3], borderColor: t.panel, borderWidth: 1 },
      },
    ],
  }
})
</script>

<template>
  <div class="grid h-full min-h-0 grid-cols-[minmax(0,1fr)_minmax(138px,38%)] gap-3" data-testid="author-concentration">
    <div class="flex min-h-0 min-w-0 flex-col">
      <div class="flex items-center justify-between gap-2 text-[11px]">
        <span class="font-medium">洛伦兹曲线</span>
        <span class="text-muted">可识别作者</span>
      </div>
      <EChart v-if="stats" :option="option" :height="205" />
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
      <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <button v-for="(author, index) in authors" :key="`${author.author}-${index}`" type="button" class="flex w-full items-center gap-2 rounded px-1 py-1 text-left text-[11px] hover:bg-soft focus-visible:bg-soft" :title="`搜索 ${author.author} 的 Commit`" @click="emit('select-author', author.author)">
          <span class="w-4 shrink-0 font-mono text-[10px] text-muted">{{ index + 1 }}</span>
          <span class="min-w-0 flex-1 truncate">{{ author.author }}<span v-if="author.isBot" class="ml-1 text-[9px] text-muted">Bot</span></span>
          <span class="shrink-0 font-mono">{{ author.commits }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
