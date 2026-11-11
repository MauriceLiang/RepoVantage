<script setup lang="ts">
import { Download, Plus, TriangleAlert, X } from 'lucide-vue-next'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import ComparisonDurationChart from '@/components/charts/ComparisonDurationChart.vue'
import ComparisonChart from '@/components/charts/ComparisonChart.vue'
import GdBadge from '@/components/ui/GdBadge.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import GdCoverageNote from '@/components/ui/GdCoverageNote.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useDataSource } from '@/composables/useDataSource'
import { downloadBlob } from '@/lib/download'
import type { ActivityTrendPrediction, ComparisonBundle, ComparisonMode, MaintenancePattern, RecentActivityChange, SelectionFeedback, SelectionMetric, SelectionRequest, SelectionResult, TimeWindow } from '@/services/types'
import { useAnalysisStore } from '@/stores/analysis'
import { useUiStore } from '@/stores/ui'
import GdSegmented from '@/components/ui/GdSegmented.vue'

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
const durationItems = computed(() => entries.value.map((entry) => ({
  label: entry.label,
  issueP50: entry.issueP50,
  issueSample: entry.issueSample,
  prP50: entry.prP50,
  prSample: entry.prSample,
})))
const missingReason = (quality: string) => ({
  partial: '覆盖不完整',
  insufficient_samples: '样本不足',
  missing: '未采集',
  failed: '采集失败',
}[quality] ?? (comparisonMode.value === 'same_period' ? '观察窗口不一致' : '当前口径不可比'))
const issueMissing = computed(() => entries.value.filter((e) => e.issueP50 === null).map((e) => `${short(e.label)}：${e.windowAvailable ? missingReason(e.issueQuality) : '范围未覆盖'}`))
const prMissing = computed(() => entries.value.filter((e) => e.prP50 === null).map((e) => `${short(e.label)}：${e.windowAvailable ? missingReason(e.prQuality) : '范围未覆盖'}`))
const basisWindowLabel = computed(() => comparisonBasis.value?.sharedWindow
  ? `${comparisonBasis.value.sharedWindow.start.replace('T', ' ').replace('Z', ' UTC')} — ${comparisonBasis.value.sharedWindow.end.replace('T', ' ').replace('Z', ' UTC')}`
  : '无共同窗口')
const comparisonEmptyMessage = computed(() => comparisonBasis.value?.status === 'not_comparable'
  ? comparisonBasis.value.reason ?? '没有达到同期比较要求。'
  : '共同窗口内没有可用的完整 UTC Commit 周。可切换到「各自窗口」查看各仓库自身活动。')
const totalCommits = (entry: (typeof entries.value)[number]) => entry.points.length && entry.points.every((point) => point.value !== null)
  ? entry.points.reduce((sum, point) => sum + (point.value ?? 0), 0).toLocaleString('en-US')
  : '—'
const entryWindow = (entry: (typeof entries.value)[number]) => entry.windowStart && entry.windowEnd
  ? `${entry.windowStart} 至 ${entry.windowEnd}`
  : '—'

const scenario = ref('')
const candidateGroup = ref('')
const candidatesConfirmed = ref(false)
const languages = ref('')
const licenses = ref('')
const weights = reactive<Record<SelectionMetric, number>>({ commits_weekly_mean: 1, issue_median_hours: 0, pr_median_hours: 0, release_interval_days: 0 })
const selectionMetrics: { key: SelectionMetric; label: string }[] = [
  { key: 'commits_weekly_mean', label: '每周 Commit（越多越高）' },
  { key: 'issue_median_hours', label: 'Issue 关闭耗时（越短越高）' },
  { key: 'pr_median_hours', label: 'PR 合并耗时（越短越高）' },
  { key: 'release_interval_days', label: 'Release 间隔（越短越高）' },
]
const selectionLabel = (key: string) => selectionMetrics.find((metric) => metric.key === key)?.label ?? key
const splitFilter = (value: string) => value.split(/[,，]/).map((item) => item.trim()).filter(Boolean)
const selectionInput = computed<SelectionRequest>(() => ({
  repositoryIds: [...analysis.compareIds], scenario: scenario.value.trim(), candidateGroup: candidateGroup.value.trim(), candidatesConfirmed: candidatesConfirmed.value,
  windowDays: analysis.timeWindow, allowedLanguages: splitFilter(languages.value), allowedLicenses: splitFilter(licenses.value),
  weights: { ...weights },
}))
const selectionKey = computed(() => JSON.stringify(selectionInput.value))
const selectionResult = ref<SelectionResult | null>(null)
const selectionLoading = ref(false)
const selectionError = ref<string | null>(null)
const feedback = ref<SelectionFeedback[]>([])
const feedbackChoice = ref('')
const feedbackKind = ref<SelectionFeedback['choiceKind'] | ''>('')
const feedbackReason = ref('')
const feedbackConsent = ref(false)
const feedbackBusy = ref(false)
const feedbackMessage = ref<string | null>(null)
let selectionRequestId = 0
watch(() => [analysis.compareIds.join(','), scenario.value, candidateGroup.value], () => { candidatesConfirmed.value = false })
watch(selectionKey, () => {
  selectionRequestId++; selectionResult.value = null; selectionError.value = null; selectionLoading.value = false
  feedbackChoice.value = ''; feedbackKind.value = ''; feedbackReason.value = ''; feedbackConsent.value = false; feedbackMessage.value = null
})

async function loadFeedback() {
  try { feedback.value = await source.listSelectionFeedback() }
  catch (cause) { feedbackMessage.value = cause instanceof Error ? cause.message : '无法读取本机反馈' }
}
onMounted(loadFeedback)

async function saveFeedback() {
  if (feedbackBusy.value) return
  if (!selectionResult.value || !feedbackChoice.value || !feedbackKind.value || !feedbackConsent.value) {
    feedbackMessage.value = '请选择候选、反馈类型并勾选同意后再保存。'; return
  }
  feedbackBusy.value = true
  feedbackMessage.value = null
  try {
    const saved = await source.saveSelectionFeedback(selectionInput.value, selectionResult.value.resultSignature, feedbackChoice.value, feedbackKind.value, feedbackReason.value)
    feedback.value = [saved, ...feedback.value]
    feedbackConsent.value = false
    feedbackMessage.value = '已保存到本机，待人工复核。'
  } catch (cause) { feedbackMessage.value = cause instanceof Error ? cause.message : '保存反馈失败' }
  finally { feedbackBusy.value = false }
}

async function removeFeedback(id: string) {
  if (feedbackBusy.value) return
  feedbackBusy.value = true
  feedbackMessage.value = null
  try { await source.deleteSelectionFeedback(id); feedback.value = feedback.value.filter((item) => item.id !== id); feedbackMessage.value = '已删除本机反馈。' }
  catch (cause) { feedbackMessage.value = cause instanceof Error ? cause.message : '删除反馈失败' }
  finally { feedbackBusy.value = false }
}

async function generateSelection() {
  const input = selectionInput.value
  if (!input.scenario || !input.candidateGroup) { selectionError.value = '请填写使用场景和确认可替代的候选类别。'; return }
  if (!input.candidatesConfirmed) { selectionError.value = '请确认所有候选适用于同一类需求。'; return }
  if (Object.values(input.weights).some((value) => !Number.isFinite(value) || value < 0) || !Object.values(input.weights).some((value) => value > 0)) {
    selectionError.value = '指标权重须为非负数，且至少一个权重大于零。'; return
  }
  const current = ++selectionRequestId
  selectionLoading.value = true
  selectionError.value = null
  try {
    const result = await source.getSelection(input)
    if (current === selectionRequestId) selectionResult.value = result
  } catch (cause) {
    if (current === selectionRequestId) selectionError.value = cause instanceof Error ? cause.message : '生成比较失败'
  } finally {
    if (current === selectionRequestId) selectionLoading.value = false
  }
}

function downloadSelection() {
  if (selectionResult.value?.reportMarkdown) downloadBlob(new Blob([selectionResult.value.reportMarkdown], { type: 'text/markdown;charset=utf-8' }), 'repovantage-selection.md')
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
  <div class="flex flex-col gap-[18px] px-4 pb-8 pt-5 sm:px-7 sm:pt-[22px]">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="m-0 text-[24px] font-semibold">项目比较</h1>
        <p class="mt-1.5 text-muted">选择时间口径后比较活跃度、处理耗时与发布节奏</p>
      </div>
      <div v-if="canCompare" class="flex flex-wrap items-center gap-2">
        <GdSegmented :model-value="analysis.timeWindow" :options="windowOptions" aria-label="比较时间范围" data-testid="comparison-window" @update:model-value="setWindow" />
        <GdSegmented :model-value="comparisonMode" :options="comparisonModeOptions" size="md" aria-label="选择对比方式" data-testid="comparison-mode" @update:model-value="setComparisonMode" />
        <GdButton variant="outline" :disabled="exporting || loading" data-testid="export-comparison" @click="exportComparison"><Download :size="14" /> {{ exporting ? '正在导出…' : '导出报告数据' }}</GdButton>
      </div>
    </div>

    <GdCard v-if="!canCompare">
      <h3 class="m-0 text-[15.5px] font-semibold">先选择 2–5 个仓库</h3>
      <p class="mt-1 text-[12px] text-muted">去仓库列表勾选至少两个仓库后，可以选择同期或各自窗口进行对比。</p>
      <RouterLink to="/repositories" class="gd-link mt-3 inline-flex text-[12px]"><Plus :size="12" /> 选择仓库</RouterLink>
    </GdCard>

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

    <GdCard>
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
    </GdCard>

    <GdCard>
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">Issue / PR 处理耗时对比</h3>
          <p class="mt-0.5 text-[12px] text-muted">哑铃线连接同一仓库的 Issue 与 PR P50 · 同一“天”刻度 · 点间距离表示耗时差</p>
        </div>
      </div>
      <ComparisonDurationChart :items="durationItems" :height="260" />
      <div class="flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-muted">
        <span v-for="entry in entries.filter((item) => item.issueP50 !== null || item.prP50 !== null)" :key="entry.id">
          {{ short(entry.label) }} · Issue n={{ entry.issueSample }} / PR n={{ entry.prSample }}
        </span>
        <span v-if="issueMissing.length" class="text-warnfg">Issue 缺失：{{ issueMissing.join(' / ') }}。</span>
        <span v-if="prMissing.length" class="text-warnfg">PR 缺失：{{ prMissing.join(' / ') }}。</span>
      </div>
    </GdCard>

    <GdCard>
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">综合对照表</h3>
          <p class="mt-0.5 text-[12px] text-muted">指标、单位、有效样本与采集时间</p>
        </div>
        <button class="gd-link text-[11.5px]" :disabled="exporting" @click="exportComparison">下载</button>
      </div>
      <div class="min-w-0 overflow-x-auto overscroll-x-contain">
      <table class="w-full min-w-[860px] border-collapse text-[12.5px]">
        <thead>
          <tr class="text-left text-[11.5px] text-muted">
            <th class="border-b border-line px-2.5 pb-2 font-medium">仓库</th>
            <th class="border-b border-line px-2.5 pb-2 font-medium">提交数</th>
            <th class="border-b border-line px-2.5 pb-2 font-medium">Issue P50</th>
            <th class="border-b border-line px-2.5 pb-2 font-medium">PR P50</th>
            <th class="border-b border-line px-2.5 pb-2 font-medium">发布间隔 P50</th>
            <th class="border-b border-line px-2.5 pb-2 font-medium">覆盖状态</th>
            <th class="border-b border-line px-2.5 pb-2 font-medium">观察窗口</th>
            <th class="border-b border-line px-2.5 pb-2 font-medium">采集时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="entry in entries" :key="entry.id" data-testid="comparison-row" :data-repository-id="entry.id" :data-window-available="entry.windowAvailable">
            <td class="border-b border-line px-2.5 py-2.5">{{ entry.label }}<GdBadge v-if="entry.sampleRole" class="ml-2" variant="plain">{{ entry.sampleRole === 'train' ? '训练组' : '测试组' }}</GdBadge><div v-if="entry.sourceKind === 'course_research_historical_snapshot'" class="mt-1 text-[10px] text-muted">课程研究历史快照</div></td>
            <td class="border-b border-line px-2.5 py-2.5 font-mono">{{ totalCommits(entry) }}</td>
            <td class="border-b border-line px-2.5 py-2.5 font-mono">{{ entry.issueP50 === null ? '—' : `${entry.issueP50} 天` }}</td>
            <td class="border-b border-line px-2.5 py-2.5 font-mono">{{ entry.prP50 === null ? '—' : `${entry.prP50} 天` }}</td>
            <td class="border-b border-line px-2.5 py-2.5 font-mono">{{ entry.releaseMedianDays === null ? '—' : `${entry.releaseMedianDays.toLocaleString('en-US', { maximumFractionDigits: 1 })} 天` }}</td>
            <td class="border-b border-line px-2.5 py-2.5">
              <GdBadge :variant="entry.coverage.state === 'complete' ? 'default' : 'warn'">{{ entry.windowAvailable ? entry.coverage.label : '范围未覆盖' }}</GdBadge>
            </td>
            <td class="border-b border-line px-2.5 py-2.5 font-mono text-muted">{{ entryWindow(entry) }}</td>
            <td class="border-b border-line px-2.5 py-2.5 font-mono text-muted">{{ entry.collectedAt }}</td>
          </tr>
        </tbody>
      </table>
      </div>
    </GdCard>
    <GdCard data-testid="selection-report">
      <div>
        <h3 class="m-0 text-[15.5px] font-semibold">按使用场景比较</h3>
        <p class="mt-1 text-[12px] text-muted">先确认候选可互相替代，再设置硬约束与权重。结果基于同期可用事实，是规则比较，不是成功概率。</p>
      </div>
      <form class="space-y-3" @submit.prevent="generateSelection">
        <div class="grid gap-3 md:grid-cols-2">
          <label class="space-y-1 text-[12px]">使用场景<input v-model="scenario" maxlength="500" required class="block w-full rounded-md border border-line bg-panel px-3 py-2 text-[13px]" placeholder="例如：构建内部 API 服务" /></label>
          <label class="space-y-1 text-[12px]">同类候选类别<input v-model="candidateGroup" maxlength="200" required class="block w-full rounded-md border border-line bg-panel px-3 py-2 text-[13px]" placeholder="例如：Python Web 框架" /></label>
          <label class="space-y-1 text-[12px]">允许的语言（可留空，逗号分隔）<input v-model="languages" class="block w-full rounded-md border border-line bg-panel px-3 py-2 text-[13px]" placeholder="Python, Go" /></label>
          <label class="space-y-1 text-[12px]">允许的许可证（可留空，逗号分隔）<input v-model="licenses" class="block w-full rounded-md border border-line bg-panel px-3 py-2 text-[13px]" placeholder="MIT, Apache-2.0" /></label>
        </div>
        <label class="flex items-start gap-2 text-[12px]"><input v-model="candidatesConfirmed" type="checkbox" class="mt-0.5" />我确认这些候选适用于上述同一类需求，可以互相比较。</label>
        <fieldset class="m-0 grid gap-2 rounded-md border border-line p-3 sm:grid-cols-2 lg:grid-cols-4">
          <legend class="px-1 text-[12px] font-medium">指标权重 · 0 表示不参与</legend>
          <label v-for="metric in selectionMetrics" :key="metric.key" class="space-y-1 text-[11px] text-muted">
            {{ metric.label }}<input v-model.number="weights[metric.key]" type="number" min="0" step="0.1" class="block w-full rounded-md border border-line bg-panel px-2 py-1.5 text-[12px] text-ink" />
          </label>
        </fieldset>
        <div class="flex flex-wrap items-center gap-2">
          <GdButton type="submit" :loading="selectionLoading">生成规则比较</GdButton>
          <GdButton v-if="selectionResult?.reportMarkdown" type="button" variant="outline" @click="downloadSelection">下载选型报告</GdButton>
          <span v-if="selectionError" class="text-[12px] text-warnfg" role="alert">{{ selectionError }}</span>
        </div>
      </form>
      <div v-if="selectionResult" class="space-y-3 text-[12px]" aria-live="polite" data-testid="selection-result">
        <p v-if="selectionResult.sharedWindow" class="m-0 text-muted">共同窗口：{{ selectionResult.sharedWindow.start }} 至 {{ selectionResult.sharedWindow.end }}</p>
        <p v-if="selectionResult.maintenance.dataAsOf" class="m-0 text-muted">课程仓库资料来自历史快照，截至 {{ selectionResult.maintenance.dataAsOf }}。</p>
        <div class="space-y-2 rounded-md border border-line p-3" data-testid="selection-maintenance">
          <p class="m-0 font-medium">近期默认分支提交模式、最近实际变化与未来预测</p>
          <p class="m-0 text-muted">M1 只使用默认分支 Commit；PR / Issue 是独立统计，不代表社区总体活跃度。最近实际变化与未来 M2 预测分别展示，ML 不参与规则得分。</p>
          <div v-for="item in selectionResult.maintenance.repositories" :key="item.id" class="space-y-1 border-t border-line pt-2 text-muted">
            <p class="m-0 font-medium text-ink">{{ item.name }}<GdBadge v-if="item.sampleRole" class="ml-2" variant="plain">{{ item.sampleRole === 'train' ? '训练组' : '测试组' }}</GdBadge> · {{ maintenancePatternLabel(item.pattern) }}</p>
            <template v-if="Object.keys(item.pattern.evidence).length">
              <p v-if="item.pattern.coverage.commits === 'partial'" class="m-0">Commit 覆盖不完整：已观察到 {{ item.pattern.evidence.commit_observed_partial_lower_bound ?? '—' }} 次（下限）；分页 {{ item.pattern.evidence.commit_pages_fetched ?? '—' }}/{{ item.pattern.evidence.commit_page_budget ?? '—' }} 页，请求估算 {{ item.pattern.evidence.github_request_estimate ?? '—' }} 次。</p>
              <p v-else class="m-0">默认分支 Commit {{ item.pattern.evidence.commit_total_12w ?? item.pattern.evidence.commit_total_window ?? '—' }} · {{ item.pattern.windowWeeks }} 个完整周。</p>
              <p class="m-0">{{ maintenancePrLabel(item.pattern) }}<span v-if="item.pattern.evidence.commit_total_12w === 0 && item.pattern.coverage.pull_requests_created === 'complete' && (item.pattern.evidence.pr_created_total_12w ?? 0) > 0">；0 Commit 不表示没有 PR 或社区协作活动</span></p>
              <p class="m-0">最近 4 周实际变化：{{ actualChangeLabel(item.recentActivityChange) }}。</p>
              <p class="m-0">未来 4 周活动趋势预测：{{ forecastLabel(item.activityTrend) }}。</p>
              <p class="m-0">异常提示：{{ item.activityAnomaly.method === 'statistical_baseline' ? `MAD 规则${item.activityAnomaly.suspected ? '疑似偏离，待核查' : '未标记'}` : `未运行（${item.activityAnomaly.reasonCode ?? item.activityAnomaly.status}）` }} · 窗口 {{ item.pattern.historyStart ?? '—' }} 至 {{ item.pattern.asOf ?? '—' }} · 来源 {{ item.pattern.sourceRunId ?? '—' }}</p>
            </template>
            <template v-else>
              <p class="m-0">Commit 事实证据不足（{{ item.pattern.reasonCode ?? '未采集' }}）。</p>
              <p class="m-0">最近 4 周实际变化：{{ actualChangeLabel(item.recentActivityChange) }}。</p>
              <p class="m-0">未来 4 周活动趋势预测：{{ forecastLabel(item.activityTrend) }}。</p>
            </template>
          </div>
        </div>
        <p v-if="selectionResult.status !== 'available'" class="m-0 text-warnfg">没有足够的可比较候选。</p>
        <div v-for="(row, index) in selectionResult.ranking" :key="row.id" class="rounded-md border border-line p-3">
          <div class="flex flex-wrap justify-between gap-2"><b>{{ index + 1 }}. {{ row.name }}</b><span>规则得分 {{ row.score.toFixed(3) }}</span></div>
          <ul class="mb-0 mt-2 space-y-1 pl-4 text-[11px] text-muted">
          <li v-for="item in row.evidence" :key="item.metric">{{ selectionLabel(item.metric) }}：{{ item.value.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) }} {{ item.unit }} · 贡献 {{ item.contribution.toFixed(3) }} · 样本 {{ item.validSamples }} 周 · {{ item.windowStart }} 至 {{ item.windowEnd }} · {{ item.sourceKind === 'course_research_historical_snapshot' ? '课程研究历史快照' : '在线事件分析' }} {{ item.sourceRunId }}</li>
          </ul>
        </div>
        <p v-for="item in selectionResult.excluded" :key="item.id" class="m-0 text-warnfg">{{ item.name }} 未评分：{{ item.reasons.join('；') }}</p>
        <p v-for="item in selectionResult.sensitivity" :key="item.criterion" class="m-0 text-muted">{{ selectionLabel(item.criterion) }} 权重增加 25% 后顺序：{{ item.repositoryIds.map((id) => selectionResult?.ranking.find((row) => row.id === id)?.name ?? id).join(' → ') }}</p>
        <p class="m-0 text-muted">{{ selectionResult.notes.join(' ') }}</p>
        <details v-if="selectionResult.reportMarkdown" class="rounded-md border border-line p-3" data-testid="selection-markdown-preview">
          <summary class="cursor-pointer font-medium">预览将下载的 Markdown 报告</summary>
          <pre class="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-words text-[11px] text-muted">{{ selectionResult.reportMarkdown }}</pre>
        </details>
      </div>
      <div v-if="selectionResult?.status === 'available'" class="space-y-3 rounded-md border border-line p-3" data-testid="selection-feedback-form">
        <h4 class="m-0 text-[13px] font-semibold">自愿记录本次选择</h4>
        <p class="m-0 text-[11px] text-muted">仅在本机保存场景、候选、比较依据、选择及理由，供后续研究和人工复核；不会自动用于训练。可在下方删除。</p>
        <div class="grid gap-3 sm:grid-cols-2">
          <label class="space-y-1 text-[12px]">选择候选
            <select v-model="feedbackChoice" class="block w-full rounded-md border border-line bg-panel px-3 py-2"><option value="">请选择</option><option v-for="row in selectionResult.ranking" :key="row.id" :value="row.id">{{ row.name }}</option></select>
          </label>
          <label class="space-y-1 text-[12px]">反馈类型
            <select v-model="feedbackKind" class="block w-full rounded-md border border-line bg-panel px-3 py-2"><option value="">请选择</option><option value="preference">当前偏好</option><option value="actual_choice">实际采用决定</option></select>
          </label>
        </div>
        <label class="block space-y-1 text-[12px]">理由（可选）<textarea v-model="feedbackReason" maxlength="500" rows="2" class="block w-full rounded-md border border-line bg-panel px-3 py-2" /></label>
        <label class="flex items-start gap-2 text-[12px]"><input v-model="feedbackConsent" type="checkbox" class="mt-0.5" />同意在本机保存上述反馈，供后续研究与人工复核。</label>
        <GdButton type="button" size="sm" :loading="feedbackBusy" :disabled="feedbackBusy" @click="saveFeedback">保存反馈</GdButton>
      </div>
      <div v-if="feedback.length" class="space-y-2 text-[12px]" data-testid="selection-feedback-list">
        <h4 class="m-0 text-[13px] font-semibold">已保存的本机反馈</h4>
        <div v-for="item in feedback" :key="item.id" class="flex flex-wrap items-center justify-between gap-2 rounded-md border border-line p-2">
          <span>{{ item.scenario }} · {{ item.chosenRepositoryName }} · {{ item.choiceKind === 'actual_choice' ? '实际采用决定' : '当前偏好' }} · 待复核</span>
          <GdButton type="button" variant="outline" size="sm" :disabled="feedbackBusy" @click="removeFeedback(item.id)">删除</GdButton>
        </div>
      </div>
      <p v-if="feedbackMessage" class="m-0 text-[12px] text-muted" role="status">{{ feedbackMessage }}</p>
    </GdCard>
    </template>
  </div>
</template>
