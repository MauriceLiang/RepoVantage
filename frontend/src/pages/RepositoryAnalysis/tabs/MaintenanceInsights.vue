<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useDataSource } from '@/composables/useDataSource'
import { buildMaintenanceSummary, maintenanceReason } from '@/lib/maintenanceSummary'
import type { RepositorySummary, TaskItem, TaskStatus } from '@/services/types'

const props = defineProps<{ repositoryId: string; repository: RepositorySummary | null }>()
const source = useDataSource()
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
  return '只依据采集时默认分支最近 12 个完整 UTC 周的 Commit；不能代表 PR、Issue、总体社区活跃度或代码质量。'
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
  <section class="flex flex-col gap-3" data-testid="maintenance-analysis">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h3 class="m-0 text-[15.5px] font-semibold">近期维护分析</h3>
        <p class="mb-0 mt-0.5 text-[11px] text-muted">{{ observationWindowLabel }} · 默认分支 · UTC</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <GdButton size="sm" variant="outline" :loading="maintenanceBusy" :disabled="!canStartCollection" @click="collectMaintenance(12)">
          {{ pattern?.status === 'available' || hasPatternEvidence ? '刷新维护分析' : '采集维护分析' }}
        </GdButton>
        <GdButton v-if="canExtendMaintenance" size="sm" variant="outline" :loading="maintenanceBusy" :disabled="!canStartCollection" @click="collectMaintenance(24)">扩展到 24 周</GdButton>
      </div>
    </header>

    <p v-if="tasksError" class="m-0 rounded-md bg-warnbg px-3 py-2 text-[11px] text-warnfg" role="alert">
      无法读取维护采集任务状态，暂时禁用采集。<button class="ml-1 underline" @click="reloadTasks">重新读取任务</button>
    </p>
    <p v-else-if="tasksLoading" class="m-0 text-[11px] text-muted" aria-live="polite">正在读取任务状态…</p>
    <p v-if="!tasksError && !tasksLoading && currentTask && isActive(currentTask.status)" class="m-0 flex flex-wrap items-center gap-x-2 rounded-md border border-line bg-panel px-3 py-2 text-[11px]" role="status" aria-live="polite" data-testid="maintenance-task-state">
      <span class="font-medium">{{ taskStatusText[currentTask.status] }}</span>
      <span class="text-muted">{{ currentTask.stage }}</span>
      <RouterLink to="/tasks" class="gd-link">查看任务</RouterLink>
    </p>
    <p v-else-if="!tasksError && !tasksLoading && submittedTaskId" class="m-0 text-[11px] text-muted" role="status" aria-live="polite" data-testid="maintenance-task-state">
      采集任务已提交，正在同步状态。<RouterLink to="/tasks" class="gd-link">查看任务</RouterLink>
    </p>
    <p v-if="maintenanceCached" class="m-0 text-[11px] text-muted">已复用完整缓存，没有重复读取 Commit 分页。</p>
    <p v-if="maintenanceError" class="m-0 text-[11px] text-warnfg" role="alert">{{ maintenanceError }}</p>

    <GdCard padding="sm" :gap="false" data-testid="analysis-summary">
      <div class="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
        <div class="min-w-0 flex-1">
          <p class="m-0 text-[16px] font-semibold">{{ summary.headline }}</p>
          <p class="mb-0 mt-1 text-[11px] leading-relaxed text-muted">{{ summary.activityLine }}</p>
        </div>
        <p class="m-0 max-w-xl text-[11px] leading-relaxed text-muted">{{ summary.anomalyLine }}</p>
      </div>
      <p v-if="evaluationError" class="mb-0 mt-2 text-[11px] text-warnfg" role="alert">读取失败：{{ evaluationError }} <button class="underline" @click="reloadEvaluation">重试</button></p>
      <p v-else-if="evaluationLoading" class="mb-0 mt-2 text-[11px] text-muted" aria-live="polite">正在读取维护信号…</p>
    </GdCard>

    <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <article class="min-w-0 rounded-md border border-line bg-panel px-3 py-2.5" data-testid="maintenance-pattern">
        <h4 class="m-0 text-[11px] font-medium text-muted">近期维护模式 <span class="font-normal">· M1</span></h4>
        <p class="mb-0 mt-1 text-[15px] font-semibold leading-snug">
          {{ machineLearningPattern ? pattern?.displayName ?? pattern?.patternName : pattern?.coverage.commits === 'partial' ? '覆盖不完整' : '暂不可用' }}
        </p>
        <p v-if="pattern && hasPatternEvidence" class="mb-0 mt-1 text-[10.5px] leading-relaxed text-muted">
          Commit {{ formatCount(patternEvidence.commit_total_12w ?? patternEvidence.commit_total_window ?? patternEvidence.commit_observed_partial_lower_bound) }} 次
          <template v-if="activeWeeks !== undefined"> · 活跃 {{ activeWeeks }}/12 周</template>
        </p>
        <p v-else class="mb-0 mt-1 text-[10.5px] leading-relaxed text-muted">{{ pattern ? maintenanceReason(pattern.reasonCode) : '尚未采集模式证据' }}</p>
      </article>

      <article class="min-w-0 rounded-md border border-line bg-panel px-3 py-2.5" data-testid="recent-actual-change">
        <h4 class="m-0 text-[11px] font-medium text-muted">最近 4 周实际变化</h4>
        <template v-if="evaluation?.recentActivityChange.status === 'available'">
          <p class="mb-0 mt-1 text-[15px] font-semibold leading-snug">{{ evaluation.recentActivityChange.trend }} · {{ formatCount(evaluation.recentActivityChange.recent4wCommits) }} vs {{ formatCount(evaluation.recentActivityChange.previous4wCommits) }}</p>
          <p class="mb-0 mt-1 text-[10.5px] leading-relaxed text-muted">Commit · 近期 vs 此前</p>
        </template>
        <p v-else class="mb-0 mt-1 text-[10.5px] leading-relaxed text-muted">{{ evaluation ? maintenanceReason(evaluation.recentActivityChange.reasonCode ?? evaluation.recentActivityChange.status) : '尚未采集事实窗口' }}</p>
      </article>

      <article class="min-w-0 rounded-md border border-line bg-panel px-3 py-2.5" data-testid="activity-estimates">
        <h4 class="m-0 text-[11px] font-medium text-muted">未来 4 周趋势 <span class="font-normal">· M2</span></h4>
        <template v-if="evaluation?.activityTrend.status === 'available' && evaluation.activityTrend.method === 'machine_learning' && evaluation.activityTrend.trend">
          <p class="mb-0 mt-1 text-[15px] font-semibold leading-snug">{{ formatTrend(evaluation.activityTrend.trend) }}</p>
          <p class="mb-0 mt-1 text-[10.5px] leading-relaxed text-muted">模型预测，存在误差</p>
        </template>
        <p v-else class="mb-0 mt-1 text-[10.5px] leading-relaxed text-muted">{{ evaluation ? maintenanceReason(evaluation.activityTrend.reasonCode ?? evaluation.activityTrend.status) : '尚未生成预测' }}</p>
      </article>

      <article class="min-w-0 rounded-md border border-line bg-panel px-3 py-2.5" data-testid="activity-anomalies">
        <h4 class="m-0 text-[11px] font-medium text-muted">近期活动异常 <span class="font-normal">· M3</span></h4>
        <template v-if="evaluation?.activityAnomaly.status === 'baseline_only' && evaluation.activityAnomaly.method === 'statistical_baseline'">
          <p class="mb-0 mt-1 text-[15px] font-semibold leading-snug">{{ evaluation.activityAnomaly.suspected ? `疑似${evaluation.activityAnomaly.weeks[0]?.direction === 'up' ? '增加' : evaluation.activityAnomaly.weeks[0]?.direction === 'down' ? '减少' : '偏离'}` : '未见明显异常' }}</p>
          <p v-if="evaluation.activityAnomaly.suspected && evaluation.activityAnomaly.weeks[0]" class="mb-0 mt-1 text-[10.5px] leading-relaxed text-muted">{{ evaluation.activityAnomaly.weeks[0].weekStart }} · {{ evaluation.activityAnomaly.weeks[0].commitCount }} Commit</p>
        </template>
        <p v-else class="mb-0 mt-1 text-[10.5px] leading-relaxed text-muted">{{ evaluation ? maintenanceReason(evaluation.activityAnomaly.reasonCode ?? evaluation.activityAnomaly.status) : '尚未生成异常提示' }}</p>
      </article>
    </div>

    <details class="rounded-md border border-line bg-panel px-3 py-2 text-[11px]" data-testid="analysis-provenance">
      <summary class="cursor-pointer font-medium">数据范围与模型说明</summary>
      <div v-if="evaluation" class="mt-2 space-y-1.5 leading-relaxed text-muted">
        <p v-if="evaluation.researchSample" class="m-0" data-testid="course-research-sample">
          课程研究样本 · {{ evaluation.researchSample.datasetVersion }} · {{ evaluation.researchSample.sampleRole === 'train' ? '训练组' : '测试组' }} · 资料快照截至 {{ evaluation.researchSample.dataAsOf ?? '未知' }}；活动窗口 {{ evaluation.researchSample.observationStart ?? '—' }} 至 {{ evaluation.researchSample.observationEndExclusive ?? '—' }}。{{ evaluation.researchSample.sampleRole === 'train' ? '模型应用于训练组，不代表独立测试证明。' : '模型应用于测试组；历史回测指标以训练报告固定时点结果为准。' }}在线采集优先于历史快照。
        </p>
        <p class="m-0">观察窗口：{{ observationWindowLabel }}；{{ analysisWindow }}</p>
        <p class="m-0">Commit 来源：采集时默认分支 · 覆盖{{ commitCoverageLabel }}；同期 PR 创建覆盖{{ prCoverageLabel }}（独立统计）。</p>
        <p class="m-0">M1 模型 {{ pattern?.modelVersion ?? '—' }} · Commit 窗口 {{ formatUtc(pattern?.historyStart) }} 至 {{ formatUtc(pattern?.asOf) }}；采集完成于 {{ analysisCollectionTime }}；来源运行 {{ pattern?.sourceRunId ?? '—' }}。</p>
        <p v-if="evaluation.recentActivityChange.status === 'available'" class="m-0">实际变化窗口：此前 {{ formatUtc(evaluation.recentActivityChange.previousWindowStart) }} 至 {{ formatUtc(evaluation.recentActivityChange.previousWindowEndExclusive) }}；最近 {{ formatUtc(evaluation.recentActivityChange.recentWindowStart) }} 至 {{ formatUtc(evaluation.recentActivityChange.recentWindowEndExclusive) }}。变化 {{ formatCount(evaluation.recentActivityChange.changeCount) }} 次；显著阈值 {{ evaluation.recentActivityChange.threshold ?? '—' }}。{{ evaluation.recentActivityChange.notes.join(' ') }}</p>
        <p class="m-0">M2 模型 {{ evaluation.activityTrend.modelVersion ?? '—' }} · 预测窗口 {{ formatForecastDate(evaluation.activityTrend.evidence.forecast_start_utc) }} 至 {{ formatForecastDate(evaluation.activityTrend.evidence.forecast_end_exclusive_utc) }}。{{ evaluation.activityTrend.notes.join(' ') }}不预测精确 Commit 数量或成功概率。</p>
        <ul v-if="evaluation.activityAnomaly.weeks.length" class="m-0 space-y-1 pl-4">
          <li v-for="week in evaluation.activityAnomaly.weeks" :key="week.weekStart">{{ week.weekStart }} UTC 周 · {{ week.commitCount }} Commit · {{ week.direction === 'up' ? '高于' : week.direction === 'down' ? '低于' : '处于' }}历史基线 · robust Z {{ week.robustZ.toFixed(2) }}</li>
        </ul>
        <p class="m-0">{{ patternScopeNote }} {{ summary.anomalyLine }}“疑似异常”仅供核查，不代表维护失败或经标签验证的模型结果。</p>
        <p v-for="limitation in evaluation.limitations" :key="limitation" class="m-0">{{ limitation }}</p>
        <p v-for="limitation in pattern?.limitations ?? []" :key="limitation" class="m-0">{{ limitation }}</p>
        <p v-if="tasksError" class="m-0 text-warnfg">任务状态暂不可用：{{ tasksError }}</p>
      </div>
      <p v-else class="mb-0 mt-2 leading-relaxed text-muted">分析结果使用最近 12 个完整 UTC 周；覆盖不足时不按零补齐，也不生成模型推断。</p>
    </details>
  </section>
</template>
