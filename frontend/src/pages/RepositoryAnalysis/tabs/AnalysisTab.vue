<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import GdEmptyState from '@/components/ui/GdEmptyState.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useDataSource } from '@/composables/useDataSource'
import { buildMaintenanceSummary, maintenanceReason } from '@/lib/maintenanceSummary'
import type { RepositorySummary, TaskItem, TaskStatus } from '@/services/types'
import { useAnalysisStore } from '@/stores/analysis'
import { useUiStore } from '@/stores/ui'

const props = defineProps<{ repositoryId: string; repository: RepositorySummary | null }>()
const source = useDataSource()
const router = useRouter()
const analysisStore = useAnalysisStore()
const ui = useUiStore()
const { data: evaluation, loading: evaluationLoading, error: evaluationError, reload: reloadEvaluation } = useAsyncData(
  () => source.getEvaluation(props.repositoryId),
  () => props.repositoryId,
)
const { data: taskData, loading: tasksLoading, error: tasksError, reload: reloadTasks } = useAsyncData(
  () => source.listTasks(),
  () => props.repositoryId,
)

const maintenanceBusy = ref(false)
const maintenanceError = ref<string | null>(null)
const maintenanceCached = ref(false)
const submittedTaskId = ref<string | null>(null)
let pollTimer: number | undefined

const taskStatusText: Record<TaskStatus, string> = {
  queued: '排队中', running: '正在采集', analyzing: '正在分析', done: '已完成', partial: '部分完成', failed: '失败', cancelled: '已取消',
}
const activeStatuses = new Set<TaskStatus>(['queued', 'running', 'analyzing'])
const repositoryNumericId = computed(() => Number(props.repositoryId))
const repositoryName = computed(() => props.repository?.fullName ?? `仓库 #${props.repositoryId}`)
const repositoryTasks = computed(() => (taskData.value ?? []).filter((task: TaskItem) =>
  task.repositoryId === repositoryNumericId.value && task.scopeKind === 'maintenance'))
const activeTask = computed(() => repositoryTasks.value.find((task) => activeStatuses.has(task.status)) ?? null)
const currentTask = computed(() => {
  if (submittedTaskId.value) {
    const submitted = repositoryTasks.value.find((task) => task.id === submittedTaskId.value)
    if (submitted) return submitted
  }
  return activeTask.value
})
const collectionInProgress = computed(() => maintenanceBusy.value
  || submittedTaskId.value !== null
  || Boolean(activeTask.value))
const canStartCollection = computed(() => !collectionInProgress.value && !tasksLoading.value && !tasksError.value)
const summary = computed(() => buildMaintenanceSummary(evaluation.value, evaluationError.value))
const pattern = computed(() => evaluation.value?.maintenancePattern ?? null)
const patternEvidence = computed(() => pattern.value?.evidence ?? {})
const hasPatternEvidence = computed(() => Object.keys(patternEvidence.value).length > 0)
const machineLearningPattern = computed(() => pattern.value?.status === 'available'
  && pattern.value.method === 'machine_learning'
  && Boolean(pattern.value.displayName ?? pattern.value.patternName))
const canExtendMaintenance = computed(() => {
  const createdAt = props.repository?.createdAt
  if (!createdAt || !pattern.value || pattern.value.windowWeeks >= 24) return false
  const ageWeeks = Math.floor((Date.now() - new Date(createdAt).getTime()) / (7 * 86400000))
  return ageWeeks >= 12 && (pattern.value.windowWeeks < 12 || (patternEvidence.value.commit_total_12w ?? 0) < 3)
})
const activeWeeks = computed(() => patternEvidence.value.commit_active_weeks_12w)
const activeWeekRatio = computed(() => typeof activeWeeks.value === 'number' ? Math.round(activeWeeks.value / 12 * 100) : null)
const commitCoverageLabel = computed(() => coverageLabel(pattern.value?.coverage.commits))
const prCoverageLabel = computed(() => coverageLabel(pattern.value?.coverage.pull_requests_created))
const observationWindowLabel = computed(() => {
  if (pattern.value?.coverage.commits === 'partial'
      && typeof patternEvidence.value.commit_observed_weeks === 'number') {
    return `观察到 ${patternEvidence.value.commit_observed_weeks} 周，Commit 完整覆盖 ${patternEvidence.value.commit_complete_weeks ?? 0} 周`
  }
  return pattern.value?.windowWeeks
    ? `最近 ${pattern.value.windowWeeks} 个完整 UTC 周`
    : '尚无完整观察周'
})
const analysisCollectionTime = computed(() => formatUtc(pattern.value?.collectedAt ?? null))
const analysisWindow = computed(() => {
  if (pattern.value?.windowWeeks && pattern.value.windowWeeks >= 24) {
    return '已扩展至 24 周背景；M1/M2 仍依据最近 12 周特征推理。'
  }
  if (pattern.value?.windowWeeks && pattern.value.windowWeeks < 12) {
    return '当前不足 12 个完整 UTC 周，不生成 M1/M2；仅展示已观察事实。'
  }
  return '模型使用最近 12 个完整 UTC 周；按需扩展的 24 周仅作事实背景。'
})
const patternScopeNote = computed(() => {
  if (pattern.value?.coverage.commits === 'partial') {
    return 'Commit 覆盖不完整，本页只展示明确标注的已观察下限和完整周事实；M1/M2/M3 不基于缺失周推理。'
  }
  if (pattern.value?.windowWeeks && pattern.value.windowWeeks < 12) {
    return `当前仅观察到 ${pattern.value.windowWeeks} 个完整 UTC 周，未达到 M1 的 12 周输入要求；下方只显示事实统计。`
  }
  return '只依据采集时默认分支最近 12 个完整 UTC 周的 Commit；不代表 PR、Issue、总体社区活跃度或代码质量。'
})

function isActive(status: TaskStatus | undefined): boolean {
  return Boolean(status && activeStatuses.has(status))
}

function coverageLabel(value: string | undefined): string {
  if (value === 'complete') return '完整'
  if (value === 'partial') return '部分覆盖'
  if (value === 'partial_or_unavailable') return '部分覆盖或不可用'
  if (value === 'not_collected') return '未采集'
  if (value === 'missing') return '缺少数据'
  return '状态未知'
}

function formatUtc(value: string | null | undefined): string {
  return value ? `${value.slice(0, 16).replace('T', ' ')} UTC` : '—'
}

function formatCount(value: number | null | undefined): string {
  return value == null ? '—' : value.toLocaleString('zh-CN')
}

function formatForecastDate(value: number | string | undefined): string {
  return typeof value === 'string' ? formatUtc(value) : '—'
}

function formatTrend(value: string | null | undefined): string {
  if (value === 'up') return '上升'
  if (value === 'stable') return '基本稳定'
  if (value === 'down') return '下降'
  return value ?? '无法判定'
}

async function collectMaintenance(lookbackWeeks: 12 | 24 = 12) {
  if (!canStartCollection.value) return
  maintenanceBusy.value = true
  maintenanceError.value = null
  maintenanceCached.value = false
  try {
    const result = await source.collectMaintenance(props.repositoryId, lookbackWeeks)
    submittedTaskId.value = result.taskId
    maintenanceCached.value = result.reused
    if (result.reused) {
      submittedTaskId.value = null
      await Promise.all([reloadEvaluation(), reloadTasks()])
    } else {
      await reloadTasks()
    }
  } catch (cause) {
    maintenanceError.value = cause instanceof Error ? cause.message : '无法创建维护活动采集任务'
  } finally {
    maintenanceBusy.value = false
  }
}

function openComparison() {
  if (!analysisStore.compareIds.includes(props.repositoryId)) {
    if (analysisStore.compareIds.length >= 5) {
      ui.toast('最多可同时比较 5 个仓库，请先移除一个候选。', 'warning')
      return
    }
    analysisStore.toggleCompare(props.repositoryId)
  }
  void router.push('/compare')
}

watch(currentTask, (next, previous) => {
  if (isActive(previous?.status) && !isActive(next?.status)) {
    void reloadEvaluation()
    if (previous?.id === submittedTaskId.value) submittedTaskId.value = null
  }
})

onMounted(() => {
  pollTimer = window.setInterval(() => {
    if (activeTask.value || submittedTaskId.value) void reloadTasks()
  }, 3000)
})

onBeforeUnmount(() => {
  if (pollTimer !== undefined) window.clearInterval(pollTimer)
})
</script>

<template>
  <section class="flex flex-col gap-4" data-testid="maintenance-analysis">
    <header class="flex flex-wrap items-end justify-between gap-4">
      <div class="min-w-0">
        <h2 class="m-0 text-[21px] font-semibold">仓库分析</h2>
        <p class="mb-0 mt-1 text-[12px] text-muted">{{ repositoryName }} · 近期维护行为证据 · 最近 12 个完整 UTC 周</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <GdButton size="sm" variant="outline" :loading="maintenanceBusy" :disabled="!canStartCollection" @click="collectMaintenance(12)">
          {{ pattern?.status === 'available' || hasPatternEvidence ? '刷新最近 12 周' : '采集最近 12 周' }}
        </GdButton>
        <GdButton v-if="canExtendMaintenance" size="sm" variant="outline" :loading="maintenanceBusy" :disabled="!canStartCollection" @click="collectMaintenance(24)">按需扩展到 24 周</GdButton>
      </div>
    </header>

    <p v-if="tasksError" class="m-0 rounded-md bg-warnbg px-3 py-2 text-[12px] text-warnfg" role="alert">
      无法读取维护采集任务状态；为避免重复发起请求，暂时禁用采集。<button class="ml-1 underline" @click="reloadTasks">重新读取任务</button>
    </p>
    <p v-else-if="tasksLoading" class="m-0 text-[12px] text-muted" aria-live="polite">正在读取维护采集任务状态…</p>
    <p v-if="evaluation?.researchSample" class="m-0 rounded-md border border-line bg-panel px-3 py-2 text-[11px] leading-relaxed text-muted" data-testid="course-research-sample">
      课程研究样本 · {{ evaluation.researchSample.datasetVersion }} · {{ evaluation.researchSample.sampleRole === 'train' ? '训练组' : '测试组' }} · 资料快照截至 {{ evaluation.researchSample.dataAsOf ?? '未知' }}；活动观察窗口 {{ evaluation.researchSample.observationStart ?? '—' }} 至 {{ evaluation.researchSample.observationEndExclusive ?? '—' }}。
      {{ evaluation.researchSample.sampleRole === 'train' ? '本页模型结果是训练组仓库上的模型应用，不是独立测试证明。' : '本页模型结果是测试组仓库的后续应用；150/150 历史回测仍以训练报告中固定时点的指标为准。' }}更新的在线采集优先于历史快照。
    </p>
    <p v-if="!tasksError && !tasksLoading && currentTask && isActive(currentTask.status)" class="m-0 flex flex-wrap items-center gap-x-2 rounded-md border border-line bg-panel px-3 py-2 text-[12px]" role="status" aria-live="polite" data-testid="maintenance-task-state">
      <span class="font-medium">{{ taskStatusText[currentTask.status] }}</span>
      <span class="text-muted">{{ currentTask.stage }}</span>
      <RouterLink to="/tasks" class="gd-link">查看任务</RouterLink>
    </p>
    <p v-else-if="!tasksError && !tasksLoading && submittedTaskId" class="m-0 text-[12px] text-muted" role="status" aria-live="polite" data-testid="maintenance-task-state">
      采集任务已提交，正在同步状态。<RouterLink to="/tasks" class="gd-link">查看任务</RouterLink>
    </p>
    <p v-if="maintenanceCached" class="m-0 text-[12px] text-muted">已复用当前窗口的完整缓存，没有重复读取 Commit 分页。</p>
    <p v-if="maintenanceError" class="m-0 text-[12px] text-warnfg" role="alert">{{ maintenanceError }}</p>

    <GdCard data-testid="analysis-summary">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h3 class="m-0 text-[15.5px] font-semibold">近期维护行为摘要</h3>
        <span v-if="evaluation && !evaluationError" class="text-[11px] text-muted">{{ observationWindowLabel }} · Commit {{ commitCoverageLabel }}</span>
      </div>
      <div v-if="evaluationLoading" class="mt-3 space-y-2" aria-live="polite">
        <div class="h-5 w-2/3 animate-pulse rounded bg-track" />
        <div class="h-4 w-full animate-pulse rounded bg-track" />
      </div>
      <GdEmptyState v-else-if="evaluationError" class="mt-2" title="暂时无法读取近期分析" :description="evaluationError">
        <template #action><GdButton size="sm" class="mt-1" @click="reloadEvaluation">重试读取</GdButton></template>
      </GdEmptyState>
      <div v-else class="mt-3 space-y-2">
        <p class="m-0 text-[18px] font-semibold">{{ summary.headline }}</p>
        <p class="m-0 text-[12px] leading-relaxed text-muted">{{ summary.activityLine }}</p>
        <p class="m-0 text-[12px] leading-relaxed text-muted">{{ summary.anomalyLine }}</p>
        <p v-if="summary.status === 'waiting'" class="m-0 text-[12px] text-muted">开始 12 周采集后，系统会从同一份 evaluation 结果生成分析；不会进入页面就自动请求 GitHub。</p>
      </div>
      <p class="mb-0 mt-3 border-t border-line pt-3 text-[11px] leading-relaxed text-muted">这些结果仅提供近期维护行为参考；技术选型仍应结合功能适配、许可证与 Issue / PR 协作数据。</p>
    </GdCard>

    <div class="grid gap-4 xl:grid-cols-2">
      <GdCard data-testid="maintenance-pattern">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 class="m-0 text-[15.5px] font-semibold">近期默认分支提交模式</h3>
            <p class="mb-0 mt-1 text-[12px] text-muted">M1 · 近期行为分类</p>
          </div>
          <span v-if="machineLearningPattern && pattern?.modelVersion" class="text-[11px] text-muted">{{ pattern.modelVersion }}</span>
        </div>
        <p v-if="evaluationLoading" class="m-0 text-[12px] text-muted">正在读取模式证据…</p>
        <p v-else-if="evaluationError" class="m-0 text-[12px] text-warnfg">暂时无法读取：{{ evaluationError }}</p>
        <template v-else-if="pattern">
          <template v-if="hasPatternEvidence">
            <p class="m-0 text-[22px] font-semibold">{{ machineLearningPattern ? pattern.displayName ?? pattern.patternName : pattern.coverage.commits === 'partial' ? '模型暂不可用 · 覆盖不完整' : '模式模型暂不可用' }}</p>
            <div class="grid gap-x-4 gap-y-2 text-[12px] sm:grid-cols-2">
              <span v-if="pattern.coverage.commits === 'partial'">已观察 Commit 下限：{{ formatCount(patternEvidence.commit_observed_partial_lower_bound) }} 次</span>
              <span v-else-if="pattern.windowWeeks < 12">已观察完整周默认分支 Commit：{{ formatCount(patternEvidence.commit_total_window) }} 次 · {{ pattern.windowWeeks }} 周</span>
              <span v-else>最近 12 周默认分支 Commit：{{ formatCount(patternEvidence.commit_total_12w ?? patternEvidence.commit_total_window) }} 次</span>
              <span v-if="pattern.coverage.commits === 'partial'">完整周事实：{{ formatCount(patternEvidence.commits_in_complete_weeks) }} 次 / {{ formatCount(patternEvidence.commit_complete_weeks) }} 周</span>
              <span v-else-if="activeWeeks !== undefined">活跃周：{{ activeWeeks }} / 12{{ activeWeekRatio === null ? '' : ` · ${activeWeekRatio}%` }}</span>
              <span v-if="patternEvidence.commit_longest_zero_weeks_12w !== undefined">最长连续无 Commit：{{ patternEvidence.commit_longest_zero_weeks_12w }} 周</span>
              <span>同期 PR 创建覆盖：{{ prCoverageLabel }}<template v-if="pattern.coverage.pull_requests_created === 'complete' && typeof patternEvidence.pr_created_total_12w === 'number'"> · {{ formatCount(patternEvidence.pr_created_total_12w) }} 个</template></span>
              <span v-if="patternEvidence.commit_page_budget !== undefined">Commit 分页：{{ patternEvidence.commit_pages_fetched ?? '—' }} / {{ patternEvidence.commit_page_budget }} 页 · 请求估算 {{ patternEvidence.github_request_estimate ?? '—' }} 次</span>
            </div>
            <p v-if="pattern.coverage.commits === 'partial'" class="m-0 text-[12px] text-warnfg">{{ maintenanceReason(pattern.reasonCode) }}局部 Commit 不进入 M1、M2 或 M3 推理。</p>
            <p v-if="patternEvidence.commit_total_12w === 0 && pattern.coverage.pull_requests_created === 'complete' && (patternEvidence.pr_created_total_12w ?? 0) > 0" class="m-0 text-[12px] text-muted">12 周 Commit 为 0，但同期有 PR 创建记录；这不代表仓库没有协作活动。</p>
          </template>
          <p v-else class="m-0 text-[12px] text-muted">{{ maintenanceReason(pattern.reasonCode) }}</p>
          <p class="m-0 border-t border-line pt-3 text-[11px] leading-relaxed text-muted">{{ patternScopeNote }} <template v-if="pattern?.coverage.commits !== 'partial' && pattern.windowWeeks >= 12">不代表 PR、Issue、总体社区活跃度或代码质量。</template></p>
        </template>
        <p v-else class="m-0 text-[12px] text-muted">尚未采集模式证据。</p>
      </GdCard>

      <GdCard data-testid="recent-actual-change">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">最近 4 周实际变化</h3>
          <p class="mb-0 mt-1 text-[12px] text-muted">历史统计事实 · 不代表未来结果</p>
        </div>
        <p v-if="evaluationLoading" class="m-0 text-[12px] text-muted">正在读取历史事实…</p>
        <p v-else-if="evaluationError" class="m-0 text-[12px] text-warnfg">暂时无法读取：{{ evaluationError }}</p>
        <template v-else-if="evaluation">
          <template v-if="evaluation.recentActivityChange.status === 'available'">
            <p class="m-0 text-[20px] font-semibold">{{ evaluation.recentActivityChange.trend }} · {{ formatCount(evaluation.recentActivityChange.recent4wCommits) }} vs {{ formatCount(evaluation.recentActivityChange.previous4wCommits) }} Commit</p>
            <p class="m-0 text-[11px] text-muted">此前 {{ formatUtc(evaluation.recentActivityChange.previousWindowStart) }} 至 {{ formatUtc(evaluation.recentActivityChange.previousWindowEndExclusive) }}；最近 {{ formatUtc(evaluation.recentActivityChange.recentWindowStart) }} 至 {{ formatUtc(evaluation.recentActivityChange.recentWindowEndExclusive) }}。</p>
            <p class="m-0 text-[11px] text-muted">变化 {{ formatCount(evaluation.recentActivityChange.changeCount) }} 次；显著阈值 max(3, 此前 4 周总量 × 25%) = {{ evaluation.recentActivityChange.threshold ?? '—' }}。{{ evaluation.recentActivityChange.notes.join(' ') }}</p>
          </template>
          <p v-else class="m-0 text-[12px] text-muted">近期变化无法判定：{{ maintenanceReason(evaluation.recentActivityChange.reasonCode ?? evaluation.recentActivityChange.status) }} {{ evaluation.recentActivityChange.notes.join(' ') }}</p>
        </template>
        <p v-else class="m-0 text-[12px] text-muted">尚未采集最近 8 个完整 UTC 周，暂不显示事实比较。</p>
      </GdCard>

      <GdCard data-testid="activity-estimates">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">未来 4 周活动趋势预测</h3>
          <p class="mb-0 mt-1 text-[12px] text-muted">M2 · 机器学习分类，可能存在预测误差</p>
        </div>
        <p v-if="evaluationLoading" class="m-0 text-[12px] text-muted">正在读取趋势预测…</p>
        <p v-else-if="evaluationError" class="m-0 text-[12px] text-warnfg">暂时无法读取：{{ evaluationError }}</p>
        <template v-else-if="evaluation">
          <template v-if="evaluation.activityTrend.status === 'available' && evaluation.activityTrend.method === 'machine_learning' && evaluation.activityTrend.trend">
            <p class="m-0 text-[20px] font-semibold">预测：{{ formatTrend(evaluation.activityTrend.trend) }} <span v-if="evaluation.activityTrend.modelVersion" class="text-[11px] font-normal text-muted">· {{ evaluation.activityTrend.modelVersion }}</span></p>
            <p class="m-0 text-[11px] text-muted">预测窗口 {{ formatForecastDate(evaluation.activityTrend.evidence.forecast_start_utc) }} 至 {{ formatForecastDate(evaluation.activityTrend.evidence.forecast_end_exclusive_utc) }}。{{ evaluation.activityTrend.notes.join(' ') }}</p>
          </template>
          <p v-else class="m-0 text-[12px] text-muted">暂不提供未来预测：{{ maintenanceReason(evaluation.activityTrend.reasonCode ?? evaluation.activityTrend.status) }} {{ evaluation.activityTrend.notes.join(' ') }}</p>
          <p class="m-0 text-[11px] text-muted">不预测精确 Commit 数量或成功概率；模型仅使用最近 12 周特征。</p>
        </template>
        <p v-else class="m-0 text-[12px] text-muted">尚未生成未来趋势预测。</p>
      </GdCard>

      <GdCard data-testid="activity-anomalies">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">近期活动异常提示</h3>
          <p class="mb-0 mt-1 text-[12px] text-muted">M3 · MAD 统计规则</p>
        </div>
        <p v-if="evaluationLoading" class="m-0 text-[12px] text-muted">正在读取异常提示…</p>
        <p v-else-if="evaluationError" class="m-0 text-[12px] text-warnfg">暂时无法读取：{{ evaluationError }}</p>
        <template v-else-if="evaluation">
          <template v-if="evaluation.activityAnomaly.status === 'baseline_only' && evaluation.activityAnomaly.method === 'statistical_baseline'">
            <p v-if="evaluation.activityAnomaly.suspected" class="m-0 text-[18px] font-semibold">疑似异常{{ evaluation.activityAnomaly.weeks[0]?.direction === 'up' ? '增加' : evaluation.activityAnomaly.weeks[0]?.direction === 'down' ? '减少' : '偏离' }}</p>
            <p v-else class="m-0 text-[18px] font-semibold">未发现明显异常</p>
            <p v-if="evaluation.activityAnomaly.suspected && evaluation.activityAnomaly.weeks[0]" class="m-0 text-[12px]">{{ evaluation.activityAnomaly.weeks[0].weekStart }} UTC 周 · {{ evaluation.activityAnomaly.weeks[0].commitCount }} Commit · 相对历史基线偏离 {{ evaluation.activityAnomaly.weeks[0].robustZ.toFixed(2) }}</p>
            <details v-if="evaluation.activityAnomaly.weeks.length > 1" class="text-[11px] text-muted">
              <summary class="cursor-pointer">查看各周规则证据</summary>
              <ul class="mb-0 mt-2 space-y-1 pl-4">
                <li v-for="week in evaluation.activityAnomaly.weeks" :key="week.weekStart">{{ week.weekStart }} UTC 周 · {{ week.commitCount }} Commit · {{ week.direction === 'up' ? '高于' : week.direction === 'down' ? '低于' : '处于' }}历史基线 · robust Z {{ week.robustZ.toFixed(2) }}</li>
              </ul>
            </details>
          </template>
          <p v-else class="m-0 text-[12px] text-muted">暂无法判断：{{ maintenanceReason(evaluation.activityAnomaly.reasonCode ?? evaluation.maintenancePattern.reasonCode ?? evaluation.activityAnomaly.status) }}</p>
          <p class="m-0 text-[11px] text-muted">规则对比当前完整周与此前 11 个完整周；“疑似”仅供核查，不等同于维护失败或经标签验证的机器学习模型。</p>
        </template>
        <p v-else class="m-0 text-[12px] text-muted">尚未采集异常判断所需的完整周数据。</p>
      </GdCard>
    </div>

    <GdCard data-testid="selection-guidance">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div class="max-w-3xl">
          <h3 class="m-0 text-[15.5px] font-semibold">技术选型辅助结论</h3>
          <p class="mb-0 mt-1 text-[12px] leading-relaxed text-muted">{{ summary.headline }}。{{ summary.activityLine }} {{ summary.anomalyLine }}这些信息描述近期维护行为，不代表功能适配、代码质量或采用成功率；请结合许可证并查看 Issue / PR 协作数据。</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <GdButton size="sm" variant="outline" @click="openComparison">{{ analysisStore.compareIds.includes(repositoryId) ? '前往仓库对比' : '加入比较' }}</GdButton>
          <RouterLink :to="`/repositories/${repositoryId}/issues`" class="gd-link self-center text-[12px]">查看 Issue</RouterLink>
          <RouterLink :to="`/repositories/${repositoryId}/prs`" class="gd-link self-center text-[12px]">查看 PR</RouterLink>
        </div>
      </div>
    </GdCard>

    <details class="rounded-md border border-line bg-panel px-3 py-2 text-[12px]" data-testid="analysis-provenance">
      <summary class="cursor-pointer font-medium">数据来源、范围与适用性</summary>
      <div v-if="evaluation" class="mt-2 space-y-1.5 text-[11px] leading-relaxed text-muted">
        <p class="m-0">观察窗口：{{ observationWindowLabel }}；{{ analysisWindow }}</p>
        <p class="m-0">Commit 来源：采集时默认分支 · 覆盖{{ commitCoverageLabel }}；同期 PR 创建覆盖{{ prCoverageLabel }}（独立统计）。</p>
        <p class="m-0">Commit 窗口 {{ formatUtc(pattern?.historyStart) }} 至 {{ formatUtc(pattern?.asOf) }}；采集完成于 {{ analysisCollectionTime }}；来源运行 {{ pattern?.sourceRunId ?? '—' }}。</p>
        <p v-for="limitation in evaluation.limitations" :key="limitation" class="m-0">{{ limitation }}</p>
        <p v-for="limitation in pattern?.limitations ?? []" :key="limitation" class="m-0">{{ limitation }}</p>
      </div>
      <p v-else class="mb-0 mt-2 text-[11px] text-muted">evaluation 暂不可用；页面不会把缺失或未采集状态解释成真实零活动。</p>
      <p v-if="tasksError" class="mb-0 mt-2 text-[11px] text-warnfg">任务状态暂不可用：{{ tasksError }}</p>
    </details>
  </section>
</template>
