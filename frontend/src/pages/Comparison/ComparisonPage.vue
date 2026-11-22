<script setup lang="ts">
import { Download, Plus, TriangleAlert, X } from 'lucide-vue-next'
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import ComparisonChart from '@/components/charts/ComparisonChart.vue'
import RepositoryComparisonRadar from '@/components/charts/RepositoryComparisonRadar.vue'
import GdBadge from '@/components/ui/GdBadge.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCoverageNote from '@/components/ui/GdCoverageNote.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useDataSource } from '@/composables/useDataSource'
import { downloadBlob } from '@/lib/download'
import type { ActivityTrendPrediction, ComparisonBundle, ComparisonMode, MaintenancePattern, RecentActivityChange, SelectionMetric, SelectionRequest, SelectionResult, TimeWindow } from '@/services/types'
import { normalizeMetrics } from '@/lib/chartAnalytics'
import { maintenanceReason } from '@/lib/maintenanceSummary'
import { useAnalysisStore } from '@/stores/analysis'
import { useUiStore } from '@/stores/ui'
import GdSegmented from '@/components/ui/GdSegmented.vue'
import UiPageHeader from '@/components/ui/UiPageHeader.vue'
import UiPanel from '@/components/ui/UiPanel.vue'
import CompactWeightEditor from './components/CompactWeightEditor.vue'
import CompactRankingTable from './components/CompactRankingTable.vue'
import { presetWeights, rebalanceWeight, selectionMetrics, type WeightPreset } from './weightMath'

const ui = useUiStore()
const analysis = useAnalysisStore()
const source = useDataSource()
const exporting = ref(false)
const comparisonMode = ref<ComparisonMode>('same_period')
const windowOptions = [30, 90, 180].map((value) => ({ value, label: `${value} 天` }))
const setWindow = (value: string | number) => analysis.setWindow(value as TimeWindow)
const comparisonModeOptions = [
  { value: 'same_period', label: '同期对比', hint: '按真实观察窗口交集重算；交集至少达到所选范围的 80%，Commit 仅取共同完整 UTC 周。' },
  { value: 'individual_periods', label: '各自窗口', hint: '分别使用各仓库自身完整周和可用指标，时间范围可能不同。' },
]
const comparisonModeDescription = computed(() => comparisonMode.value === 'same_period'
  ? '按所有仓库真实观察窗口的交集重算；至少覆盖所选窗口的 80%。Commit 只比较共同完整 UTC 周，Release 使用近 365 天并单独检查覆盖。'
  : '分别展示各仓库自身完整自然周与可用指标；窗口不同时适合比较各自活跃度和处理节奏，不代表同期排名。')
function setComparisonMode(value: string | number) {
  if (value === 'same_period' || value === 'individual_periods') comparisonMode.value = value
}

const { data, loading, error } = useAsyncData(
  () => analysis.compareIds.length >= 2
    ? source.getComparison(analysis.compareIds, analysis.timeWindow, comparisonMode.value)
    : Promise.resolve({ window: { start: '—', end: '—' }, requestedWindowDays: analysis.timeWindow, mode: comparisonMode.value, comparisonBasis: { scope: comparisonMode.value === 'same_period' ? 'shared_observation' : 'repository_windows', requestedWindowDays: analysis.timeWindow, sharedWindow: null, effectiveDays: null, minimumCoverageRatio: comparisonMode.value === 'same_period' ? 0.8 : null, minimumEffectiveDays: comparisonMode.value === 'same_period' ? analysis.timeWindow * 0.8 : null, status: comparisonMode.value === 'same_period' ? 'not_comparable' : 'separate_windows', reasonCode: null, reason: null }, entries: [], notes: [] } as ComparisonBundle),
  () => [analysis.compareIds.join(','), comparisonMode.value, analysis.timeWindow],
)

const canCompare = computed(() => analysis.compareIds.length >= 2)
const entries = computed(() => data.value?.entries ?? [])
const { data: maintenanceRows, loading: maintenanceRowsLoading } = useAsyncData(
  () => Promise.all(analysis.compareIds.map(async (id) => {
    try {
      return { id, evaluation: await source.getEvaluation(id), error: null }
    } catch (cause) {
      return { id, evaluation: null, error: cause instanceof Error ? cause.message : '维护分析读取失败' }
    }
  })),
  () => analysis.compareIds.join(','),
)
const comparisonEntry = (id: string) => entries.value.find((entry) => entry.id === id)
const { data: scoringComparison, loading: scoringComparisonLoading, error: scoringComparisonError } = useAsyncData(
  () => comparisonMode.value === 'same_period' || analysis.compareIds.length < 2
    ? Promise.resolve(null)
    : source.getComparison(analysis.compareIds, analysis.timeWindow, 'same_period'),
  () => [analysis.compareIds.join(','), analysis.timeWindow, comparisonMode.value],
)
const selectionBasisEntries = computed(() => comparisonMode.value === 'same_period' ? entries.value : scoringComparison.value?.entries ?? [])
const selectionBasisLoading = computed(() => comparisonMode.value === 'same_period' ? loading.value : scoringComparisonLoading.value)
const selectionBasisError = computed(() => comparisonMode.value === 'same_period' ? error.value : scoringComparisonError.value)
const comparisonBasis = computed(() => data.value?.comparisonBasis)
const comparisonNotes = computed(() => (data.value?.notes ?? []).filter((note) => !entries.value.some((entry) => entry.windowReason && note === `${entry.label}：${entry.windowReason}`)))
const short = (label: string) => label.split('/')[1]
const formatCount = (value: number | null | undefined) => value === null || value === undefined
  ? '—'
  : value.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
const maintenancePatternValue = (pattern: MaintenancePattern) => pattern.method === 'machine_learning' && pattern.status === 'available'
  ? pattern.displayName ?? pattern.patternName ?? '模式未分类'
  : pattern.coverage.commits === 'partial' ? 'Commit 覆盖不完整'
    : pattern.status === 'temporarily_unavailable' ? '数据暂不可用'
      : pattern.reasonCode === 'not_collected' ? '尚未采集' : '仅显示事实'
const maintenancePatternDetail = (pattern: MaintenancePattern) => {
  const evidence = pattern.evidence
  const total = evidence.commit_total_12w ?? evidence.commit_total_window ?? evidence.commit_observed_partial_lower_bound
  const activeWeeks = evidence.commit_active_weeks_12w ?? evidence.active_weeks_12w ?? evidence.commit_active_weeks_in_complete_weeks
  if (total === undefined) return pattern.reasonCode ? maintenanceReason(pattern.reasonCode) : '等待可用 Commit 数据'
  return `${pattern.coverage.commits === 'partial' ? '至少 ' : ''}${formatCount(total)} 次 Commit${activeWeeks === undefined ? '' : ` · 活跃 ${formatCount(activeWeeks)}/${pattern.windowWeeks || 12} 周`}`
}
const maintenanceChangeValue = (change: RecentActivityChange) => change.status === 'available'
  ? `${change.trend ?? '变化已统计'} · ${formatCount(change.recent4wCommits)} vs ${formatCount(change.previous4wCommits)} 次 Commit`
  : '暂不可判定'
const maintenanceChangeDetail = (change: RecentActivityChange) => change.status === 'available'
  ? '最近 4 周 vs 此前 4 周'
  : maintenanceReason(change.reasonCode ?? change.status)
const maintenanceForecastValue = (trend: ActivityTrendPrediction) => trend.status === 'available' && trend.method === 'machine_learning' && trend.trend
  ? trend.trend : '暂不可用'
const maintenanceForecastDetail = (trend: ActivityTrendPrediction) => trend.status === 'available' && trend.method === 'machine_learning'
  ? 'M2 模型预测，可能存在误差'
  : maintenanceReason(trend.reasonCode ?? trend.status)
const maintenanceSnapshot = (evaluation: { researchSample: { sampleRole: 'train' | 'test'; dataAsOf: string | null } | null; maintenancePattern: MaintenancePattern }) => {
  if (evaluation.researchSample) {
    const role = evaluation.researchSample.sampleRole === 'train' ? '训练组' : '测试组'
    const asOf = evaluation.researchSample.dataAsOf?.slice(0, 10)
    return asOf ? `历史样本 · ${role} · 截至 ${asOf}` : `历史样本 · ${role}`
  }
  return evaluation.maintenancePattern.asOf ? `截至 ${evaluation.maintenancePattern.asOf.slice(0, 10)} UTC` : ''
}
const radarAxes = [
  { key: 'commitsWeekly', label: '每周 Commit', direction: 'higher' as const },
  { key: 'issueP50Days', label: 'Issue P50', direction: 'lower' as const },
  { key: 'prP50Days', label: 'PR P50', direction: 'lower' as const },
  { key: 'releaseIntervalDays', label: 'Release 间隔', direction: 'lower' as const },
  { key: 'activeWeekRatio', label: '有效周占比', direction: 'higher' as const },
]
const comparisonRadarRows = computed(() => {
  const raw = selectionBasisEntries.value.map((entry) => {
    const validWeeks = entry.points.flatMap((point) => point.value !== null ? [point.value] : [])
    return {
      repository: entry.label,
      color: entry.color,
      commitsWeekly: validWeeks.length ? validWeeks.reduce((sum, value) => sum + value, 0) / validWeeks.length : null,
      issueP50Days: entry.issueP50,
      prP50Days: entry.prP50,
      releaseIntervalDays: entry.releaseMedianDays,
      activeWeekRatio: entry.points.length && validWeeks.length ? validWeeks.length / entry.points.length * 100 : null,
      commitWeekSamples: validWeeks.length,
      issueSamples: entry.issueSample,
      prSamples: entry.prSample,
      coverage: entry.coverage.label,
    }
  })
  return normalizeMetrics(raw, radarAxes.map((axis) => ({ key: axis.key, direction: axis.direction })))
})
const basisWindowLabel = computed(() => comparisonBasis.value?.sharedWindow
  ? `${comparisonBasis.value.sharedWindow.start.replace('T', ' ').replace('Z', ' UTC')} — ${comparisonBasis.value.sharedWindow.end.replace('T', ' ').replace('Z', ' UTC')}`
  : '无共同窗口')
const comparisonEmptyMessage = computed(() => comparisonBasis.value?.status === 'not_comparable'
  ? comparisonBasis.value.reason ?? '没有达到同期比较要求。'
  : '共同窗口内没有可用的完整 UTC Commit 周。可切换到「各自窗口」查看各仓库自身活动。')
const weights = reactive<Record<SelectionMetric, number>>({ commits_weekly_mean: 0, issue_median_hours: 0, pr_median_hours: 0, release_interval_days: 0 })
const weightPreset = ref<WeightPreset>('balanced')
const selectionInput = computed<SelectionRequest>(() => ({
  repositoryIds: [...analysis.compareIds], scenario: '自定义权重对比', candidateGroup: '当前所选仓库', candidatesConfirmed: true,
  windowDays: analysis.timeWindow, allowedLanguages: [], allowedLicenses: [],
  weights: Object.fromEntries(selectionMetrics.map((metric) => [metric.key, weights[metric.key] / 10])) as Record<SelectionMetric, number>,
}))
const selectionKey = computed(() => JSON.stringify(selectionInput.value))
const weightsReady = computed(() => {
  const selected = analysis.compareIds
  return !selectionBasisLoading.value && selected.length >= 2 && selected.every((id) => selectionBasisEntries.value.some((entry) => entry.id === id))
})
const metricReadiness = computed(() => Object.fromEntries(selectionMetrics.map((metric) => {
  const ready = selectionBasisEntries.value.filter((entry) => {
    if (!entry.windowAvailable) return false
    if (metric.key === 'commits_weekly_mean') return entry.coverage.state === 'complete' && entry.points.length > 0 && entry.points.every((point) => point.value !== null)
    if (metric.key === 'issue_median_hours') return entry.issueP50 !== null && ['ready', 'partial'].includes(entry.issueQuality) && entry.issueSample >= 1
    if (metric.key === 'pr_median_hours') return entry.prP50 !== null && ['ready', 'partial'].includes(entry.prQuality) && entry.prSample >= 1
    return entry.releaseMedianDays !== null && ['ready', 'partial'].includes(entry.releaseQuality)
  }).length
  const partial = selectionBasisEntries.value.filter((entry) =>
    metric.key === 'issue_median_hours' ? entry.issueP50 !== null && entry.issueQuality === 'partial'
      : metric.key === 'pr_median_hours' ? entry.prP50 !== null && entry.prQuality === 'partial'
        : metric.key === 'release_interval_days' && entry.releaseMedianDays !== null && entry.releaseQuality === 'partial',
  ).length
  const total = analysis.compareIds.length
  return [metric.key, { ready, total, partial, comparableForAll: total > 0 && ready === total }]
})) as Record<SelectionMetric, { ready: number; total: number; partial: number; comparableForAll: boolean }>)
const totalWeight = computed(() => selectionMetrics.reduce((sum, metric) => sum + weights[metric.key], 0))
const weightsInitializedFor = ref('')
watch(
  () => [analysis.compareIds.join(','), selectionBasisEntries.value.map((entry) => entry.id).join(','), selectionBasisLoading.value] as const,
  ([compareKey, loadedIds, isLoading]) => {
    if (!compareKey || isLoading || !weightsReady.value || weightsInitializedFor.value === compareKey) return
    const loadedSet = new Set(loadedIds.split(',').filter(Boolean))
    if (!compareKey.split(',').every((id) => loadedSet.has(id))) return
    Object.assign(weights, presetWeights('balanced'))
    weightsInitializedFor.value = compareKey
    weightPreset.value = 'balanced'
  },
  { immediate: true },
)
function applyWeightPreset(preset: Exclude<WeightPreset, 'custom'>) {
  if (!weightsReady.value) return
  weightPreset.value = preset
  Object.assign(weights, presetWeights(preset))
}
function updateMetricWeight(payload: { metric: SelectionMetric; value: number }) {
  Object.assign(weights, rebalanceWeight(weights, payload.metric, payload.value))
  weightPreset.value = 'custom'
}
const selectionResult = ref<SelectionResult | null>(null)
const selectionLoading = ref(false)
const selectionError = ref<string | null>(null)
const selectionContextKey = computed(() => JSON.stringify({ repositoryIds: [...analysis.compareIds], windowDays: analysis.timeWindow }))
const selectionResultInputKey = ref('')
const selectionResultIsStale = computed(() => !!selectionResult.value && selectionResultInputKey.value !== selectionKey.value)
const expandedRepositoryId = ref<string | null>(null)
function toggleEvidence(repositoryId: string) {
  expandedRepositoryId.value = expandedRepositoryId.value === repositoryId ? null : repositoryId
}
let selectionRequestId = 0
let selectionTimer: ReturnType<typeof setTimeout> | null = null
watch(selectionContextKey, () => {
  selectionRequestId++
  if (selectionTimer) clearTimeout(selectionTimer)
  selectionTimer = null
  selectionResult.value = null
  selectionResultInputKey.value = ''
  expandedRepositoryId.value = null
  selectionError.value = null
  selectionLoading.value = false
}, { flush: 'sync' })
watch(selectionKey, () => {
  selectionRequestId++
  selectionError.value = null
  selectionLoading.value = false
  if (selectionTimer) clearTimeout(selectionTimer)
  selectionTimer = null
  if (!weightsReady.value || totalWeight.value <= 0) return
  selectionLoading.value = true
  selectionTimer = setTimeout(() => {
    selectionTimer = null
    void generateSelection()
  }, 350)
})

onBeforeUnmount(() => { if (selectionTimer) clearTimeout(selectionTimer) })

async function generateSelection() {
  const input = selectionInput.value
  if (Object.values(input.weights).some((value) => !Number.isFinite(value) || value < 0 || value > 10) || !Object.values(input.weights).some((value) => value > 0)) {
    selectionError.value = '请至少给一个指标设置大于 0 的权重。'; return
  }
  const requestedContextKey = selectionContextKey.value
  const requestedInputKey = JSON.stringify(input)
  const current = ++selectionRequestId
  selectionLoading.value = true
  selectionError.value = null
  try {
    const result = await source.getSelection(input)
    if (current === selectionRequestId && requestedContextKey === selectionContextKey.value && requestedInputKey === selectionKey.value) {
      selectionResult.value = result
      selectionResultInputKey.value = requestedInputKey
      if (result.status !== 'available' || !result.ranking.some((row) => row.id === expandedRepositoryId.value)) expandedRepositoryId.value = null
    }
  } catch (cause) {
    if (current === selectionRequestId) selectionError.value = cause instanceof Error ? cause.message : '生成比较失败'
  } finally {
    if (current === selectionRequestId) selectionLoading.value = false
  }
}

async function exportComparison() {
  exporting.value = true
  try {
    downloadBlob(await source.exportComparison(analysis.compareIds, analysis.timeWindow, comparisonMode.value), 'repovantage-comparison.csv')
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '导出比较结果失败', 'error')
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <div class="stack app-page comparison-page">
    <UiPageHeader title="项目比较" description="选择真实时间口径后比较活跃度、处理耗时与发布节奏。">
      <template #actions><div v-if="canCompare" class="flex flex-wrap items-center gap-2">
        <GdSegmented :model-value="analysis.timeWindow" :options="windowOptions" aria-label="比较时间范围" data-testid="comparison-window" @update:model-value="setWindow" />
        <GdSegmented :model-value="comparisonMode" :options="comparisonModeOptions" size="md" aria-label="选择对比方式" data-testid="comparison-mode" @update:model-value="setComparisonMode" />
        <GdButton variant="outline" :disabled="exporting || loading" data-testid="export-comparison" @click="exportComparison"><Download :size="14" /> {{ exporting ? '正在导出…' : '导出报告数据' }}</GdButton>
      </div></template>
    </UiPageHeader>

    <UiPanel v-if="!canCompare" as="section">
      <h3 class="m-0 text-[15.5px] font-semibold">先选择 2–5 个仓库</h3>
      <p class="mt-1 text-[12px] text-muted">去仓库列表勾选至少两个仓库后，可以选择同期或各自窗口进行对比。</p>
      <RouterLink to="/repositories" class="gd-link mt-3 inline-flex text-[12px]"><Plus :size="12" /> 选择仓库</RouterLink>
    </UiPanel>

    <template v-else>

    <p class="-mt-2 text-[11.5px] text-muted" data-testid="comparison-description" :data-window-days="data?.requestedWindowDays" :data-mode="data?.mode" :aria-busy="loading">{{ analysis.timeWindow }} 天 · {{ comparisonModeDescription }}</p>

    <div v-if="comparisonMode === 'same_period' && comparisonBasis" class="rounded-md border border-line bg-panel px-3 py-2 text-[11.5px] leading-relaxed" data-testid="comparison-basis" :data-status="comparisonBasis.status" :data-reason-code="comparisonBasis.reasonCode ?? ''">
      <span class="font-medium">同期比较依据：</span>
      <template v-if="comparisonBasis.sharedWindow">
        {{ basisWindowLabel }} · 交集 {{ comparisonBasis.effectiveDays }} 天 / 最低 {{ comparisonBasis.minimumEffectiveDays }} 天。
      </template>
      <template v-else>未形成共同分析窗口。</template>
      <span v-if="comparisonBasis.reason" class="ml-1 text-warnfg">{{ comparisonBasis.reason }}</span>
    </div>

    <div v-for="entry in entries.filter((item) => !item.windowAvailable)" :key="entry.id" class="rounded-md bg-warnbg px-3 py-2 text-[12px] text-warnfg" data-testid="comparison-window-unavailable">
      {{ entry.label }}：{{ entry.windowReason ?? '所选范围未覆盖' }}
      <RouterLink :to="`/repositories/${entry.id}/overview`" class="gd-link ml-2">前往按所选范围采集</RouterLink>
    </div>

    <div class="flex flex-wrap gap-2">
      <span v-for="entry in entries" :key="entry.id" class="inline-flex items-center gap-1.5 rounded-md border border-line bg-panel px-2.5 py-1.5 text-[12px]">
        <i class="size-2 rounded-sm" :style="{ background: entry.color }" />
        {{ entry.label }}
        <button class="text-muted hover:text-ink" @click="analysis.toggleCompare(entry.id)"><X :size="12" /></button>
      </span>
      <RouterLink to="/repositories" class="inline-flex items-center gap-1 rounded-md border border-line bg-panel px-2.5 py-1.5 text-[12px] text-muted hover:text-ink">
        <Plus :size="12" /> 添加仓库
      </RouterLink>
    </div>

    <div v-if="error || comparisonNotes.length" class="flex items-start gap-2 rounded-md bg-warnbg px-3 py-2.5 text-[11.5px] leading-relaxed text-warnfg">
      <TriangleAlert :size="14" class="mt-0.5 shrink-0" />
      <span>{{ error ?? comparisonNotes.join(' ') }}</span>
    </div>

    <UiPanel as="section" tight data-testid="selection-report">
      <section class="space-y-2">
        <header class="flex flex-wrap items-start justify-between gap-3">
          <div class="space-y-1">
            <h3 class="m-0 text-[15.5px] font-semibold">权重与综合分</h3>
            <p class="m-0 text-[12px] leading-relaxed text-muted">比较所选仓库的相对分；调整权重后自动重新计算。</p>
          </div>
          <span class="text-[11px] text-muted">{{ analysis.compareIds.length }} 个仓库 · 4 项评价指标</span>
        </header>

        <CompactWeightEditor
          :metrics="selectionMetrics"
          :weights="weights"
          :readiness="metricReadiness"
          :enabled="weightsReady"
          :updating="selectionBasisLoading"
          :preset="weightPreset"
          @change-weight="updateMetricWeight"
          @select-preset="applyWeightPreset"
        />

        <p v-if="selectionBasisError" class="m-0 text-[11.5px] text-warnfg" role="alert">无法读取评分所需的比较数据：{{ selectionBasisError }}</p>
        <div v-if="selectionError" class="flex flex-wrap items-center justify-between gap-2 rounded-md bg-warnbg px-3 py-2 text-[11.5px] text-warnfg" role="alert">
          <span>综合分更新失败：{{ selectionError }}<span v-if="selectionResult">；页面保留上次成功结果。</span></span>
          <button type="button" class="rounded border border-line bg-panel px-2 py-1 font-medium text-ink hover:bg-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--gd-primary-button)]" :disabled="!weightsReady" data-testid="selection-retry" @click="generateSelection">重试</button>
        </div>

        <div v-if="selectionResult || selectionLoading" class="space-y-2 border-t border-line pt-2 text-[12px]" :aria-busy="selectionLoading" data-testid="selection-result">
          <CompactRankingTable
            :result="selectionResult"
            :metrics="selectionMetrics"
            :stale="selectionResultIsStale"
            :updating="selectionLoading"
            :expanded-repository-id="expandedRepositoryId"
            @toggle-details="toggleEvidence"
          >
          </CompactRankingTable>

        </div>

      </section>
    </UiPanel>
    <UiPanel as="section">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">开发活动对比</h3>
          <p class="mt-0.5 text-[12px] text-muted">每周提交数 · {{ analysis.timeWindow }} 天 · {{ data?.window.start }} 至 {{ data?.window.end }}{{ comparisonMode === 'individual_periods' ? ' · 各仓库独立窗口' : ' · 共同完整周' }}；Release 固定近 365 天</p>
        </div>
        <div class="flex flex-wrap items-center gap-3 text-[11px] text-muted">
          <span v-for="entry in entries" :key="entry.id" class="flex items-center gap-1">
            {{ short(entry.label) }}
            <GdCoverageNote :coverage="entry.coverage" compact />
          </span>
        </div>
      </div>
      <div v-if="loading" class="h-[280px] animate-pulse rounded bg-track/60" />
      <p v-if="error" class="py-8 text-center text-[12px] text-danger">比较数据加载失败：{{ error }}</p>
      <ComparisonChart v-else-if="entries.some((entry) => entry.points.length)" :entries="entries.map((e) => ({ label: e.label, color: e.color, points: e.points }))" :height="280" />
      <p v-else-if="!loading" class="py-8 text-center text-[12px] text-muted">{{ comparisonMode === 'same_period' ? comparisonEmptyMessage : '各仓库自身窗口内都没有可用的完整 Commit 周。' }}</p>
      <div class="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted">
        <span>单位：次 · SHA 去重 · 各仓库均为默认分支</span>
        <span>曲线在某周中断表示该仓库的采集到此结束，不用 0 补齐</span>
      </div>
    </UiPanel>

    <div class="grid min-w-0 items-stretch gap-4 xl:h-[clamp(560px,62vh,680px)] xl:grid-cols-2">
      <UiPanel as="section" class="flex min-h-0 flex-col" data-testid="comparison-diverse-charts">
        <div><h3 class="m-0 text-[15.5px] font-semibold">多维指标对照</h3><p class="mt-0.5 text-[12px] text-muted">展示所有已加入对比的仓库；每项指标按可用仓库各自归一到 0–100，耗时和发布间隔反向。缺失指标保留为空，不代表健康评分。</p></div>
        <div class="mt-3 flex min-h-0 flex-1 flex-col">
          <div v-if="comparisonRadarRows.length" class="min-w-0">
            <div class="mb-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1"><h4 class="m-0 text-[12px] font-semibold">仓库指标雷达图</h4><span class="text-[10.5px] text-muted">{{ comparisonRadarRows.length }} 个已选仓库 · 归一值 0–100</span></div>
            <RepositoryComparisonRadar :rows="comparisonRadarRows" :dimensions="radarAxes" />
            <p class="m-0 mt-1 text-[10.5px] leading-relaxed text-muted">点位轻微错开仅用于分辨仓库，连线仍按原值绘制；悬停查看原始值，缺失指标不补值。</p>
          </div>
          <p v-else class="m-0 flex-1 rounded-md bg-soft px-3 py-6 text-center text-[12px] text-muted">当前没有可展示的已选仓库。</p>
        </div>
      </UiPanel>

      <UiPanel as="section" class="flex min-h-0 max-h-[min(68vh,680px)] flex-col xl:h-full xl:max-h-full" data-testid="comparison-maintenance-analysis">
        <div class="shrink-0">
          <h3 class="m-0 text-[15.5px] font-semibold">各仓库近期维护分析</h3>
          <p class="mt-0.5 text-[12px] leading-relaxed text-muted">按仓库展示 M1 维护模式、最近 4 周实际变化和 M2 趋势预测；颜色与左侧雷达图一致。</p>
        </div>
        <div v-if="maintenanceRowsLoading" class="mt-3 min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain pr-1" role="status" aria-live="polite" aria-label="正在读取各仓库近期维护分析" tabindex="0">
          <div v-for="id in analysis.compareIds" :key="id" class="space-y-3 rounded-md border border-line p-3">
            <div class="h-4 w-2/5 animate-pulse rounded bg-track/60 motion-reduce:animate-none" />
            <div class="grid gap-2 sm:grid-cols-3"><div v-for="slot in 3" :key="slot" class="h-[76px] animate-pulse rounded bg-track/40 motion-reduce:animate-none" /></div>
          </div>
        </div>
        <div v-else-if="maintenanceRows?.length" class="mt-3 min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain pr-1" role="region" aria-label="各仓库近期维护分析列表" tabindex="0">
          <article v-for="item in maintenanceRows" :key="item.id" class="space-y-2 rounded-md border border-line p-3" :data-testid="`maintenance-summary-${item.id}`">
            <div class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
              <i v-if="comparisonEntry(item.id)" class="size-2.5 shrink-0 rounded-sm" :style="{ background: comparisonEntry(item.id)?.color }" />
              <h4 class="m-0 min-w-0 flex-1 break-all text-[12px] font-semibold">{{ comparisonEntry(item.id)?.label ?? item.id }}</h4>
              <GdBadge v-if="item.evaluation?.researchSample" variant="plain">历史样本</GdBadge>
              <span v-if="item.evaluation" class="text-[10px] text-muted">{{ maintenanceSnapshot(item.evaluation) }}</span>
            </div>
            <p v-if="item.error" class="m-0 rounded bg-warnbg px-2.5 py-2 text-[11px] text-warnfg">维护分析读取失败：{{ item.error }}</p>
            <div v-else-if="item.evaluation" class="grid min-w-0 gap-2 sm:grid-cols-3">
              <div class="min-w-0 rounded bg-soft/35 px-2.5 py-2">
                <p class="m-0 text-[10px] text-muted">维护模式 · M1</p>
                <p class="mb-0 mt-1 break-words text-[12px] font-semibold">{{ maintenancePatternValue(item.evaluation.maintenancePattern) }}</p>
                <p class="mb-0 mt-1 text-[10px] leading-relaxed text-muted">{{ maintenancePatternDetail(item.evaluation.maintenancePattern) }}</p>
              </div>
              <div class="min-w-0 rounded bg-soft/35 px-2.5 py-2">
                <p class="m-0 text-[10px] text-muted">最近 4 周实际变化</p>
                <p class="mb-0 mt-1 break-words text-[12px] font-semibold">{{ maintenanceChangeValue(item.evaluation.recentActivityChange) }}</p>
                <p class="mb-0 mt-1 text-[10px] leading-relaxed text-muted">{{ maintenanceChangeDetail(item.evaluation.recentActivityChange) }}</p>
              </div>
              <div class="min-w-0 rounded bg-soft/35 px-2.5 py-2">
                <p class="m-0 text-[10px] text-muted">未来 4 周趋势 · M2</p>
                <p class="mb-0 mt-1 break-words text-[12px] font-semibold">{{ maintenanceForecastValue(item.evaluation.activityTrend) }}</p>
                <p class="mb-0 mt-1 text-[10px] leading-relaxed text-muted">{{ maintenanceForecastDetail(item.evaluation.activityTrend) }}</p>
              </div>
            </div>
          </article>
        </div>
        <p v-else class="mt-3 flex-1 rounded-md bg-soft px-3 py-6 text-center text-[12px] text-muted">选择至少两个仓库后，这里会显示各仓库的近期维护分析。</p>
      </UiPanel>
    </div>
    </template>
  </div>
</template>
