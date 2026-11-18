<script setup lang="ts">
import { CalendarDays, Database, Download, ExternalLink, Info, RefreshCw, Scale, Code2, Trash2 } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import type { Coverage, RepositorySummary, TimeWindow } from '@/services/types'
import GdBadge from '@/components/ui/GdBadge.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdIconButton from '@/components/ui/GdIconButton.vue'
import GdSegmented from '@/components/ui/GdSegmented.vue'
import { useDataSource } from '@/composables/useDataSource'
import { downloadBlob } from '@/lib/download'
import { useAnalysisStore } from '@/stores/analysis'
import { useUiStore } from '@/stores/ui'

const props = defineProps<{ repository: RepositorySummary; coverage: Coverage; collectedAt: string | null; windowStart: string | null; windowEnd: string | null; refreshing?: boolean; clearing?: boolean }>()
const analysis = useAnalysisStore()
const ui = useUiStore()
const source = useDataSource()
const exporting = ref(false)
const statusMeta = {
  ready: { text: '已完成', variant: 'default' as const },
  partial: { text: '部分数据', variant: 'warn' as const },
  running: { text: '采集中', variant: 'plain' as const },
  idle: { text: '尚未分析', variant: 'plain' as const },
  failed: { text: '采集失败', variant: 'warn' as const },
}
const windowOptions = [
  { value: 30, label: '30 天', hint: '查看最近 30 天；范围缺失时可按所选范围采集' },
  { value: 90, label: '90 天', hint: '查看最近 90 天；范围缺失时可按所选范围采集' },
  { value: 180, label: '180 天', hint: '查看最近 180 天；可能需要更长时间采集' },
]
const emit = defineEmits<{ refresh: []; clear: [] }>()
const setWindow = (value: string | number) => analysis.setWindow(value as TimeWindow)
const refreshDescription = '按页数预算采集所选时长；达到上限时会标记为部分覆盖。'
const refreshLabel = computed(() => `开始采集 · ${analysis.timeWindow} 天`)

async function exportCsv() {
  exporting.value = true
  try {
    downloadBlob(await source.exportInsights(props.repository.id, analysis.timeWindow), `${props.repository.id}-insights.csv`)
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '导出分析结果失败', 'error')
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <div class="flex flex-wrap items-start justify-between gap-6">
    <div class="min-w-0">
      <h1 class="flex flex-wrap items-center gap-2.5 text-[25px] font-semibold leading-tight tracking-[-0.2px]">
        {{ repository.fullName }}
        <a :href="repository.htmlUrl" target="_blank" rel="noreferrer" :aria-label="`在 GitHub 打开 ${repository.fullName}`"><ExternalLink :size="15" class="text-muted" /></a>
        <GdBadge :variant="statusMeta[repository.status].variant">{{ statusMeta[repository.status].text }}</GdBadge>
      </h1>
      <p class="mt-2 max-w-[720px] leading-relaxed text-muted">{{ repository.description ?? '暂无公开简介' }}</p>
      <div class="mt-3 flex flex-wrap items-center gap-3 text-[12.5px] text-muted">
        <span v-if="repository.language" class="flex items-center gap-1.5"><Code2 :size="13" /> {{ repository.language }}</span>
        <span v-if="repository.license" class="flex items-center gap-1.5"><Scale :size="13" /> {{ repository.license }} 许可</span>
        <span class="flex items-center gap-1.5" data-testid="analysis-window-summary"><CalendarDays :size="13" /> {{ analysis.timeWindow }} 天 · {{ windowStart ?? '—' }} — {{ windowEnd ?? '—' }}</span>
        <span class="flex items-center gap-1.5"><Database :size="13" /> 分析于 {{ collectedAt ?? '—' }}</span>
        <span class="flex items-center gap-1.5" :class="coverage.state !== 'complete' ? 'font-medium text-warnfg' : ''">
          <span class="size-1.5 rounded-full" :class="coverage.state === 'complete' ? 'bg-ink/60' : 'bg-warnfg'" />
          {{ coverage.label }}{{ coverage.detail ? ` · ${coverage.detail}` : '' }}
        </span>
        <button class="gd-link text-[12.5px]" @click="ui.openDrawer('definitions', { metric: 'M01' })"><Info :size="13" /> 数据与口径</button>
      </div>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <GdSegmented :model-value="analysis.timeWindow" :options="windowOptions" aria-label="分析时间范围" data-testid="analysis-window" @update:model-value="setWindow" />
      <GdButton class="repo-toolbar-action repo-toolbar-action--primary" data-testid="collect-repository" :disabled="refreshing || clearing" :title="refreshDescription" @click="emit('refresh')"><RefreshCw :size="14" /> {{ refreshing ? '排队中…' : refreshLabel }}</GdButton>
      <GdIconButton label="导出聚合 CSV" :disabled="exporting" @click="exportCsv"><Download :size="16" /></GdIconButton>
      <GdButton variant="danger" size="sm" :loading="clearing" :disabled="refreshing" @click="emit('clear')"><Trash2 :size="13" />清除仓库数据</GdButton>
    </div>
  </div>
</template>

<style scoped>
.repo-toolbar-action { height:32px !important; }
.repo-toolbar-action--primary,
.repo-toolbar-action--primary:hover { box-shadow:none !important; }
</style>
