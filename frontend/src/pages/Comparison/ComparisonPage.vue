<script setup lang="ts">
import { Download, Plus, TriangleAlert, X } from 'lucide-vue-next'
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import ComparisonChart from '@/components/charts/ComparisonChart.vue'
import ComparisonScoreChart from '@/components/charts/ComparisonScoreChart.vue'
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
const utcRange = (start: string | null, end: string | null) => start && end
  ? `${start.slice(0, 10)} 至 ${end.slice(0, 10)} UTC`
  : '时间范围不可用'
const maintenancePatternLabel = (pattern: MaintenancePattern) => pattern.method === 'machine_learning'
  ? pattern.displayName ?? pattern.patternName ?? '模式未分类'
  : pattern.coverage.commits === 'partial' ? '模式暂不可用（Commit 覆盖不完整）' : '仅显示事实'
const actualChangeLabel = (change: RecentActivityChange) => change.status === 'available'
  ? `${change.trend} · 最近 ${change.recent4wCommits} vs 此前 ${change.previous4wCommits} Commit · 此前 ${utcRange(change.previousWindowStart, change.previousWindowEndExclusive)} · 最近 ${utcRange(change.recentWindowStart, change.recentWindowEndExclusive)}`
  : `无法判定（${change.reasonCode ?? change.status}）；缺失数据不补零`
const forecastLabel = (trend: ActivityTrendPrediction) => trend.method === 'machine_learning' && trend.status === 'available'
  ? `预测 ${trend.trend} · ${utcRange(typeof trend.evidence.forecast_start_utc === 'string' ? trend.evidence.forecast_start_utc : null, typeof trend.evidence.forecast_end_exclusive_utc === 'string' ? trend.evidence.forecast_end_exclusive_utc : null)} · ${trend.modelVersion ?? ''}`
  : `暂不提供未来预测（${trend.reasonCode ?? trend.status}）`
const maintenancePrLabel = (pattern: MaintenancePattern) => pattern.coverage.pull_requests_created === 'complete'
  ? `PR 创建量 ${pattern.evidence.pr_created_total_12w ?? '—'}（独立统计）`
  : 'PR 覆盖不完整（独立统计）'
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
const manualWeights = reactive<Record<SelectionMetric, number>>({ ...weights })
const manualWeightInputOpen = ref(false)
type WeightPreset = 'balanced' | 'activity' | 'collaboration' | 'release' | 'custom'
const weightPreset = ref<WeightPreset>('balanced')
const selectionMetrics: { key: SelectionMetric; label: string; color: string; direction: string }[] = [
  { key: 'commits_weekly_mean', label: '每周 Commit', color: '#E2683C', direction: '越多越好' },
  { key: 'issue_median_hours', label: 'Issue 关闭耗时', color: '#CE3F7C', direction: '越短越好' },
  { key: 'pr_median_hours', label: 'PR 合并耗时', color: '#2E8FCB', direction: '越短越好' },
  { key: 'release_interval_days', label: 'Release 间隔', color: '#E5A03A', direction: '越短越好' },
]
const selectionLabel = (key: string) => selectionMetrics.find((metric) => metric.key === key)?.label ?? key
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
const availableMetricCount = computed(() => selectionMetrics.filter((metric) => metricReadiness.value[metric.key].comparableForAll).length)
const totalWeight = computed(() => selectionMetrics.reduce((sum, metric) => sum + weights[metric.key], 0))
const manualWeightTotal = computed(() => selectionMetrics.reduce((sum, metric) => {
  const value = Number(manualWeights[metric.key])
  return Number.isFinite(value) ? sum + value : Number.NaN
}, 0))
const manualWeightsValid = computed(() => selectionMetrics.every((metric) => {
  const value = Number(manualWeights[metric.key])
  return Number.isFinite(value) && value >= 0 && value <= 100
}) && Math.abs(manualWeightTotal.value - 100) < 0.005)
const activeWeightCount = computed(() => selectionMetrics.filter((metric) => weights[metric.key] > 0).length)
const weightShare = (key: SelectionMetric) => totalWeight.value > 0 ? weights[key] / totalWeight.value * 100 : 0
const formatWeight = (value: number) => value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
const weightGradient = computed(() => {
  if (totalWeight.value <= 0) return 'conic-gradient(var(--gd-track) 0% 100%)'
  let current = 0
  const stops = selectionMetrics.filter((metric) => weights[metric.key] > 0).map((metric) => {
    const next = current + weightShare(metric.key)
    const stop = `${metric.color} ${current.toFixed(3)}% ${next.toFixed(3)}%`
    current = next
    return stop
  })
  return `conic-gradient(from -90deg, ${stops.join(', ')})`
})
const weightsInitializedFor = ref('')
watch(
  () => [analysis.compareIds.join(','), selectionBasisEntries.value.map((entry) => entry.id).join(','), selectionBasisLoading.value] as const,
  ([compareKey, loadedIds, isLoading]) => {
    if (!compareKey || isLoading || !weightsReady.value || weightsInitializedFor.value === compareKey) return
    const loadedSet = new Set(loadedIds.split(',').filter(Boolean))
    if (!compareKey.split(',').every((id) => loadedSet.has(id))) return
    selectionMetrics.forEach((metric) => { weights[metric.key] = 0 })
    const initialMetrics = selectionMetrics
    const equalShare = initialMetrics.length ? 100 / initialMetrics.length : 0
    initialMetrics.forEach((metric, index) => {
      weights[metric.key] = index === initialMetrics.length - 1 ? 100 - equalShare * index : equalShare
    })
    syncManualWeights()
    weightsInitializedFor.value = compareKey
    weightPreset.value = 'balanced'
  },
  { immediate: true },
)
const weightPresetOptions: { key: Exclude<WeightPreset, 'custom'>; label: string }[] = [
  { key: 'balanced', label: '均衡' },
  { key: 'activity', label: '开发活跃' },
  { key: 'collaboration', label: '协作效率' },
  { key: 'release', label: '发布节奏' },
]
function applyWeightPreset(preset: Exclude<WeightPreset, 'custom'>) {
  if (!weightsReady.value) return
  weightPreset.value = preset
  selectionMetrics.forEach((metric) => { weights[metric.key] = 0 })
  if (preset === 'balanced') selectionMetrics.forEach((metric) => { weights[metric.key] = 5 })
  else if (preset === 'activity') weights.commits_weekly_mean = 10
  else if (preset === 'collaboration') {
    weights.issue_median_hours = 5
    weights.pr_median_hours = 5
  } else weights.release_interval_days = 10
  normalizeConfiguredWeights()
  syncManualWeights()
}
function normalizeConfiguredWeights() {
  const configured = selectionMetrics.filter((metric) => weights[metric.key] > 0)
  const total = configured.reduce((sum, metric) => sum + weights[metric.key], 0)
  let assigned = 0
  configured.forEach((metric, index) => {
    const share = index === configured.length - 1 ? 100 - assigned : weights[metric.key] / total * 100
    weights[metric.key] = share
    assigned += share
  })
}
function syncManualWeights() {
  selectionMetrics.forEach((metric) => { manualWeights[metric.key] = weights[metric.key] })
}
function updateMetricWeight(key: SelectionMetric, event: Event) {
  const requestedWeight = Math.max(0, Math.min(100, Number((event.target as HTMLInputElement).value)))
  const siblings = selectionMetrics.filter((metric) => metric.key !== key)
  weights[key] = requestedWeight
  if (!siblings.length) {
    weights[key] = 100
  } else {
    const remaining = 100 - requestedWeight
    const siblingTotal = siblings.reduce((sum, metric) => sum + weights[metric.key], 0)
    let assigned = 0
    siblings.forEach((metric, index) => {
      const proportion = siblingTotal > 0 ? weights[metric.key] / siblingTotal : 1 / siblings.length
      const share = index === siblings.length - 1 ? remaining - assigned : remaining * proportion
      weights[metric.key] = share
      assigned += share
    })
  }
  weightPreset.value = 'custom'
  syncManualWeights()
}
function toggleManualWeightInput() {
  if (!manualWeightInputOpen.value) syncManualWeights()
  manualWeightInputOpen.value = !manualWeightInputOpen.value
}
function applyManualWeights() {
  if (!manualWeightsValid.value) return
  selectionMetrics.forEach((metric) => { weights[metric.key] = Number(manualWeights[metric.key]) })
  const lastMetric = selectionMetrics[selectionMetrics.length - 1]
  if (lastMetric) {
    weights[lastMetric.key] = 100 - selectionMetrics.slice(0, -1).reduce((sum, metric) => sum + weights[metric.key], 0)
  }
  weightPreset.value = 'custom'
  syncManualWeights()
  manualWeightInputOpen.value = false
}
const scorePercent = (score: number) => Math.max(0, Math.min(100, score))
const selectionResult = ref<SelectionResult | null>(null)
const selectionLoading = ref(false)
const selectionError = ref<string | null>(null)
const selectionContextKey = computed(() => JSON.stringify({ repositoryIds: analysis.compareIds, windowDays: analysis.timeWindow }))
const selectionResultContextKey = ref('')
const selectionResultInputKey = ref('')
const selectionResultIsStale = computed(() => !!selectionResult.value && selectionResultInputKey.value !== selectionKey.value)
const selectionScoreRows = computed(() => {
  const result = selectionResult.value
  if (!result || result.status !== 'available') return []
  return result.ranking.map((row, index) => ({
    id: row.id,
    name: row.name,
    score: row.score,
    rank: index + 1,
    color: selectionBasisEntries.value.find((entry) => entry.id === row.id)?.color ?? '#73808a',
  }))
})
let selectionRequestId = 0
let selectionTimer: ReturnType<typeof setTimeout> | null = null
watch(selectionKey, () => {
  selectionRequestId++
  if (selectionResultContextKey.value !== selectionContextKey.value) {
    selectionResult.value = null
    selectionResultContextKey.value = ''
    selectionResultInputKey.value = ''
  }
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
  const current = ++selectionRequestId
  selectionLoading.value = true
  selectionError.value = null
  try {
    const result = await source.getSelection(input)
    if (current === selectionRequestId) {
      selectionResult.value = result
      selectionResultContextKey.value = selectionContextKey.value
      selectionResultInputKey.value = selectionKey.value
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

    <UiPanel as="section" data-testid="selection-report">
      <section class="space-y-3">
        <header class="flex flex-wrap items-start justify-between gap-3">
          <div class="space-y-1">
            <h3 class="m-0 text-[15.5px] font-semibold">权重与综合分</h3>
            <p class="m-0 text-[12px] leading-relaxed text-muted">拖动指标权重，系统会按已采集数据计算当前所选仓库的相对得分。</p>
          </div>
        </header>

        <div class="grid min-w-0 gap-4 rounded-lg border border-line bg-soft/20 p-3 sm:p-4 lg:grid-cols-[190px_minmax(0,1fr)]">
          <div class="flex flex-col items-center justify-center gap-2">
            <div class="relative size-36 rounded-full p-[13px]" :style="{ background: weightGradient }" role="img" :aria-label="`当前权重分布，${activeWeightCount} 项指标参与`" data-testid="weight-donut">
              <div class="flex size-full flex-col items-center justify-center rounded-full bg-panel text-center">
                <strong class="text-[22px] leading-none">{{ activeWeightCount }}</strong>
                <span class="mt-1 text-[11px] text-muted">项指标参与</span>
                <span class="mt-1 font-mono text-[10px] text-muted">总权重 {{ formatWeight(totalWeight) }}%</span>
              </div>
            </div>
            <p class="m-0 text-center text-[10.5px] text-muted">环图表示归一化后的权重占比</p>
          </div>

          <div class="min-w-0 space-y-3">
            <div class="flex flex-wrap items-center gap-2" role="group" aria-label="权重预设">
              <button v-for="preset in weightPresetOptions" :key="preset.key" type="button" :disabled="!weightsReady" :aria-pressed="weightPreset === preset.key" class="rounded-md border px-2.5 py-1.5 text-[11.5px] transition-colors motion-reduce:transition-none disabled:cursor-not-allowed disabled:opacity-45" :class="weightPreset === preset.key ? 'border-[var(--gd-primary-button)] bg-soft font-semibold text-ink' : 'border-line bg-panel text-muted hover:text-ink'" @click="applyWeightPreset(preset.key)">{{ preset.label }}</button>
              <span v-if="weightPreset === 'custom'" class="text-[11px] text-muted">自定义</span>
              <button type="button" class="rounded-md border border-line bg-panel px-2.5 py-1.5 text-[11.5px] text-muted hover:text-ink disabled:cursor-not-allowed disabled:opacity-45" :disabled="!weightsReady" :aria-expanded="manualWeightInputOpen" data-testid="manual-weight-toggle" @click="toggleManualWeightInput">{{ manualWeightInputOpen ? '收起手动输入' : '手动输入' }}</button>
            </div>

            <div v-if="manualWeightInputOpen" class="space-y-3 rounded-md border border-line bg-panel p-3" data-testid="manual-weight-editor">
              <div class="flex flex-wrap items-center justify-between gap-2 text-[11px]">
                <p class="m-0 text-muted">填写各项百分比，权重合计必须为 100%。</p>
                <span class="font-mono text-ink">当前合计 {{ formatWeight(manualWeightTotal) }}%</span>
              </div>
              <div class="grid min-w-0 gap-2 sm:grid-cols-2 xl:grid-cols-4">
                <label v-for="metric in selectionMetrics" :key="metric.key" class="min-w-0 space-y-1 text-[10.5px] text-muted" :data-testid="`manual-weight-field-${metric.key}`">
                  <span>{{ metric.label }}</span>
                  <span class="flex items-center gap-2">
                    <input v-model.number="manualWeights[metric.key]" type="number" min="0" max="100" step="any" :aria-label="`${metric.label}百分比权重`" :disabled="!weightsReady" class="block w-full min-w-0 rounded-md border border-line bg-panel px-2 py-1.5 text-[12px] text-ink disabled:cursor-not-allowed disabled:opacity-50" :data-testid="`manual-weight-input-${metric.key}`" />
                    <span>%</span>
                  </span>
                </label>
              </div>
              <div class="flex flex-wrap items-center justify-between gap-2">
                <span class="text-[10.5px]" :class="manualWeightsValid ? 'text-muted' : 'text-warnfg'" role="status" aria-live="polite">{{ manualWeightsValid ? '权重合计为 100%，可以应用。' : '请调整输入值，使权重合计为 100%。' }}</span>
                <button type="button" class="rounded-md bg-[var(--gd-primary-button)] px-3 py-1.5 text-[11px] font-medium text-white disabled:cursor-not-allowed disabled:opacity-45" :disabled="!weightsReady || !manualWeightsValid" data-testid="apply-manual-weights" @click="applyManualWeights">应用权重</button>
              </div>
            </div>

            <fieldset class="m-0 grid min-w-0 gap-2 border-0 p-0 lg:grid-cols-2 xl:grid-cols-4">
              <legend class="sr-only">拖动每项指标的权重</legend>
              <label v-for="metric in selectionMetrics" :key="metric.key" class="block min-w-0 rounded-md border border-line bg-panel px-3 py-2" :data-testid="`weight-metric-${metric.key}`">
                <span class="flex min-w-0 items-center justify-between gap-2">
                  <span class="flex min-w-0 items-center gap-2 text-[12px] font-medium text-ink">
                    <i class="size-2.5 shrink-0 rounded-full" :style="{ background: metric.color }" aria-hidden="true" />
                    <span class="truncate">{{ metric.label }}</span>
                    <span class="shrink-0 text-[10px] font-normal text-muted">{{ metric.direction }}</span>
                  </span>
                  <span class="shrink-0 font-mono text-[11px] text-ink">{{ formatWeight(weightShare(metric.key)) }}%</span>
                </span>
                <span class="mt-1.5 flex items-center gap-3">
                  <input :value="weights[metric.key]" :aria-label="`${metric.label}权重`" :aria-valuetext="`${formatWeight(weights[metric.key])}% 权重`" :disabled="!weightsReady" type="range" min="0" max="100" step="any" class="h-2 min-w-0 flex-1 cursor-pointer disabled:cursor-not-allowed" :style="{ accentColor: metric.color }" @input="updateMetricWeight(metric.key, $event)" />
                  <span class="w-12 shrink-0 text-right font-mono text-[10.5px] text-muted">{{ formatWeight(weights[metric.key]) }}/100</span>
                </span>
                <span class="mt-1 flex flex-wrap items-center justify-between gap-x-3 gap-y-0.5 text-[10px] text-muted">
                  <span>{{ weightsReady ? metricReadiness[metric.key].ready : '—' }}/{{ metricReadiness[metric.key].total }} 仓库有可用数据</span>
                  <span v-if="!weightsReady">等待数据</span>
                  <span v-else-if="metricReadiness[metric.key].ready === 0">暂无可计算数据</span>
                  <span v-else-if="metricReadiness[metric.key].ready < metricReadiness[metric.key].total">{{ metricReadiness[metric.key].total - metricReadiness[metric.key].ready }} 个仓库无有效值，按中性 50 分计</span>
                  <span v-else-if="metricReadiness[metric.key].partial">含部分覆盖样本，按已观察数据计分</span>
                  <span v-else>所选仓库均可比</span>
                </span>
              </label>
            </fieldset>
          </div>
        </div>

        <div class="flex flex-wrap items-center justify-between gap-2 rounded-md bg-soft/40 px-3 py-2 text-[11px] leading-relaxed text-muted">
          <span>四项权重始终合计 100%；拖动一项后其余三项按现有比例分摊。无有效值的单项按中性 50 分计入并明确标注，不作为实际表现事实；部分覆盖按已观察数据计分。调整只重算本地数据。</span>
          <span v-if="selectionBasisLoading" role="status" aria-live="polite">正在读取同期数据…</span>
          <span v-else-if="selectionLoading" role="status" aria-live="polite">正在更新综合分…</span>
          <span v-else-if="selectionResult?.status === 'available'" role="status" aria-live="polite">已按当前权重自动计算</span>
          <span v-else-if="availableMetricCount === 0">当前没有实测指标，综合分按中性基准显示</span>
          <span v-else-if="totalWeight === 0">为可用指标分配权重，合计须为 100%</span>
          <span v-else>权重变化后自动更新</span>
        </div>
        <p v-if="selectionBasisError" class="m-0 text-[12px] text-warnfg" role="alert">无法读取综合分所需的同期数据：{{ selectionBasisError }}</p>
        <p v-if="selectionError" class="m-0 text-[12px] text-warnfg" role="alert">综合分更新失败：{{ selectionError }}</p>

        <details class="rounded-md border border-line px-3 py-2" data-testid="selection-scoring-explanation">
          <summary class="cursor-pointer text-[11.5px] font-medium">评分口径与限制</summary>
          <div class="mt-2 space-y-1.5">
            <p class="m-0 text-[11px] leading-relaxed text-muted">每项有数据的指标在当前所选仓库中归一化为 0–100：Commit 使用 log(1+x) 缓和极大值，耗时指标越短分越高；同项数值相同则都记 50 分。综合分为四项分数按用户权重加权后的结果。</p>
            <p class="m-0 text-[11px] leading-relaxed text-muted">综合分优先使用 {{ analysis.timeWindow }} 天同期窗口，窗口不重合时使用各仓库自身窗口；Release 使用近 365 天窗口。缺少有效样本时按中性 50 分计入，不作为实际表现；部分覆盖按已观察样本计算。</p>
          </div>
        </details>

        <div v-if="selectionResult || selectionLoading" class="space-y-3 border-t border-line pt-4 text-[12px]" :aria-busy="selectionLoading" data-testid="selection-result">
          <div v-if="selectionLoading" key="ranking-loading" class="space-y-3" role="status" aria-live="polite" aria-label="正在按当前权重更新综合排名">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h4 class="m-0 text-[13px] font-semibold">综合排名</h4>
                <p class="mb-0 mt-1 text-[10.5px] text-muted">正在按当前权重重新计算…</p>
              </div>
              <span class="h-5 w-16 animate-pulse rounded bg-track/60 motion-reduce:animate-none" aria-hidden="true" />
            </div>
            <div class="grid min-w-0 gap-3 lg:grid-cols-2 2xl:grid-cols-3">
              <div v-for="repositoryId in analysis.compareIds" :key="repositoryId" class="space-y-3 rounded-lg border border-line p-3" aria-hidden="true">
                <div class="flex items-center gap-2.5">
                  <span class="size-7 shrink-0 animate-pulse rounded-full bg-track/70 motion-reduce:animate-none" />
                  <span class="h-4 w-44 max-w-[55%] animate-pulse rounded bg-track/70 motion-reduce:animate-none" />
                  <span class="ml-auto h-7 w-16 animate-pulse rounded bg-track/70 motion-reduce:animate-none" />
                </div>
                <div class="h-2 animate-pulse rounded-full bg-track/70 motion-reduce:animate-none" />
                <div class="grid min-w-0 gap-2 sm:grid-cols-2 2xl:grid-cols-4">
                  <div v-for="metric in selectionMetrics" :key="metric.key" class="h-[58px] animate-pulse rounded-md bg-track/50 motion-reduce:animate-none" />
                </div>
              </div>
            </div>
          </div>
          <div v-else-if="selectionResult" key="ranking-result" class="space-y-3" aria-live="polite">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h4 class="m-0 text-[13px] font-semibold">综合排名</h4>
              <p v-if="selectionResult.sharedWindow" class="mb-0 mt-1 text-[10.5px] text-muted">共同窗口：{{ selectionResult.sharedWindow.start.slice(0, 10) }} 至 {{ selectionResult.sharedWindow.end.slice(0, 10) }} UTC</p>
              <p v-else class="mb-0 mt-1 text-[10.5px] text-muted">按各仓库自身可用窗口计分，时间范围不同，不代表同期表现。</p>
            </div>
            <GdBadge v-if="selectionResultIsStale" variant="warn">上次结果</GdBadge>
            <GdBadge v-else :variant="selectionResult.status === 'available' ? 'default' : 'warn'">{{ selectionResult.status === 'available' ? '可比较' : '筛选未通过' }}</GdBadge>
          </div>
          <ComparisonScoreChart v-if="selectionScoreRows.length" :rows="selectionScoreRows" :height="Math.min(200, Math.max(160, selectionScoreRows.length * 36))" />
          <p v-if="selectionResult.status !== 'available'" class="m-0 rounded-md bg-warnbg px-3 py-2.5 leading-relaxed text-warnfg">当前所选仓库中符合语言或许可证条件的不足两个，请调整筛选条件。</p>
          <div class="grid min-w-0 gap-3 lg:grid-cols-2 2xl:grid-cols-3">
          <div v-for="(row, index) in selectionResult.ranking" :key="row.id" class="space-y-2.5 rounded-lg border border-line p-3" :data-testid="`selection-score-${row.id}`">
            <div class="flex min-w-0 flex-wrap items-start justify-between gap-3">
              <div class="flex min-w-0 items-start gap-2.5">
                <span class="flex size-7 shrink-0 items-center justify-center rounded-full bg-soft font-mono text-[11px] font-semibold">{{ index + 1 }}</span>
                <div class="min-w-0">
                  <h5 class="m-0 break-all text-[13px] font-semibold">{{ row.name }}</h5>
                  <p class="mb-0 mt-1 text-[10.5px] text-muted">{{ row.evidence.length }} 项指标参与 · 所选仓库中的相对分</p>
                </div>
              </div>
              <div class="shrink-0 text-right">
                <strong class="font-mono text-[23px] leading-none">{{ row.score.toFixed(1) }}</strong>
                <span class="ml-1 text-[11px] text-muted">/100</span>
              </div>
            </div>
            <div class="h-2 overflow-hidden rounded-full bg-track" role="progressbar" :aria-label="`${row.name} 综合分`" :aria-valuenow="scorePercent(row.score)" aria-valuemin="0" aria-valuemax="100">
              <div class="h-full rounded-full bg-[var(--gd-primary-button)] transition-[width] duration-300 motion-reduce:transition-none" :style="{ width: `${scorePercent(row.score)}%` }" />
            </div>
            <div class="grid min-w-0 gap-2 sm:grid-cols-2 2xl:grid-cols-4">
              <div v-for="item in row.evidence" :key="item.metric" class="min-w-0 rounded-md bg-soft/35 px-2.5 py-2">
                <p class="m-0 flex min-w-0 items-center justify-between gap-2 text-[10.5px] text-muted">
                  <span class="truncate">{{ selectionLabel(item.metric) }}{{ item.missingPolicy === 'neutral_50' ? ' · 无有效样本' : item.quality === 'partial' ? ' · 部分覆盖' : '' }}</span>
                  <span class="shrink-0 font-mono">权重 {{ formatWeight(item.weight * 100) }}%</span>
                </p>
                <p class="mb-0 mt-1 break-words font-mono text-[12px] font-medium text-ink">{{ item.value === null ? '中性 50 分（无样本）' : `${item.value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} ${item.unit}` }}</p>
                <p class="mb-0 mt-1 text-[10px] text-muted">单项 {{ (item.normalized * 100).toFixed(0) }} 分 · 贡献 {{ item.contribution.toFixed(1) }} 分</p>
              </div>
            </div>
          </div>
          </div>
          <div v-if="selectionResult.excluded.length" class="space-y-1 rounded-md bg-warnbg px-3 py-2.5 text-[11px] text-warnfg" data-testid="selection-excluded">
            <p class="m-0 font-medium">未参与排名</p>
            <p v-for="item in selectionResult.excluded" :key="item.id" class="m-0 break-words">{{ item.name }}：{{ item.reasons.join('；') }}</p>
          </div>
          <details v-if="selectionResult.maintenance.repositories.length" class="rounded-md border border-line px-3 py-2.5" data-testid="selection-maintenance">
            <summary class="cursor-pointer text-[11.5px] font-medium">近期维护行为与预测证据（不参与综合分）</summary>
            <p v-if="selectionResult.maintenance.dataAsOf" class="mb-2 mt-2 text-[10.5px] text-muted">课程仓库资料来自历史快照，截至 {{ selectionResult.maintenance.dataAsOf }}。</p>
            <div v-for="item in selectionResult.maintenance.repositories" :key="item.id" class="space-y-1 border-t border-line py-2 text-[10.5px] leading-relaxed text-muted">
              <p class="m-0 font-medium text-ink">{{ item.name }}<GdBadge v-if="item.sampleRole" class="ml-2" variant="plain">{{ item.sampleRole === 'train' ? '训练组' : '测试组' }}</GdBadge> · {{ maintenancePatternLabel(item.pattern) }}</p>
              <template v-if="Object.keys(item.pattern.evidence).length">
                <p v-if="item.pattern.coverage.commits === 'partial'" class="m-0">Commit 覆盖不完整：已观察到 {{ item.pattern.evidence.commit_observed_partial_lower_bound ?? '—' }} 次（下限）；分页 {{ item.pattern.evidence.commit_pages_fetched ?? '—' }}/{{ item.pattern.evidence.commit_page_budget ?? '—' }} 页，请求估算 {{ item.pattern.evidence.github_request_estimate ?? '—' }} 次。</p>
                <p v-else class="m-0">默认分支 Commit {{ item.pattern.evidence.commit_total_12w ?? item.pattern.evidence.commit_total_window ?? '—' }} · {{ item.pattern.windowWeeks }} 个完整周。</p>
                <p class="m-0">{{ maintenancePrLabel(item.pattern) }}<span v-if="item.pattern.evidence.commit_total_12w === 0 && item.pattern.coverage.pull_requests_created === 'complete' && (item.pattern.evidence.pr_created_total_12w ?? 0) > 0">；0 Commit 不表示没有 PR 或社区协作活动</span></p>
                <p class="m-0">最近 4 周实际变化：{{ actualChangeLabel(item.recentActivityChange) }}。</p>
                <p class="m-0">未来 4 周活动趋势预测：{{ forecastLabel(item.activityTrend) }}。</p>
              </template>
              <template v-else>
                <p class="m-0">Commit 事实证据不足（{{ item.pattern.reasonCode ?? '未采集' }}）。</p>
                <p class="m-0">最近 4 周实际变化：{{ actualChangeLabel(item.recentActivityChange) }}。</p>
                <p class="m-0">未来 4 周活动趋势预测：{{ forecastLabel(item.activityTrend) }}。</p>
              </template>
            </div>
          </details>
          </div>
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
