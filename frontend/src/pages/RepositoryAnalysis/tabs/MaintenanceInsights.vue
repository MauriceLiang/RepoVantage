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
const observationWindowLabel = computed(() => {
  if (pattern.value?.coverage.commits === 'partial'
      && typeof patternEvidence.value.commit_observed_weeks === 'number') {
    return `观察到 ${patternEvidence.value.commit_observed_weeks} 周，Commit 完整覆盖 ${patternEvidence.value.commit_complete_weeks ?? 0} 周`
  }
  return pattern.value?.windowWeeks
    ? `最近 ${pattern.value.windowWeeks} 个完整 UTC 周`
    : '尚无完整观察周'
})

function isActive(status: TaskStatus | undefined): boolean {
  return Boolean(status && activeStatuses.has(status))
}

function formatCount(value: number | null | undefined): string {
  return value == null ? '—' : value.toLocaleString('zh-CN')
}

function formatWeeklyMean(value: number | null): string {
  return value == null ? '—' : value.toLocaleString('zh-CN', { maximumFractionDigits: 1 })
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
      <div class="min-w-0">
        <p class="m-0 text-[16px] font-semibold">{{ summary.headline }}</p>
        <p class="mb-0 mt-1 text-[11px] leading-relaxed text-muted">{{ summary.activityLine }}</p>
      </div>
      <p v-if="evaluationError" class="mb-0 mt-2 text-[11px] text-warnfg" role="alert">读取失败：{{ evaluationError }} <button class="underline" @click="reloadEvaluation">重试</button></p>
      <p v-else-if="evaluationLoading" class="mb-0 mt-2 text-[11px] text-muted" aria-live="polite">正在读取维护信号…</p>
    </GdCard>

    <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
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
        <template v-if="evaluation && evaluation.recentActivityChange.status !== 'insufficient_data'">
          <p class="mb-0 mt-1 text-[15px] font-semibold leading-snug">{{ evaluation.recentActivityChange.trend }} · {{ formatWeeklyMean(evaluation.recentActivityChange.recentWeeklyMean) }} vs {{ formatWeeklyMean(evaluation.recentActivityChange.previousWeeklyMean) }} Commit/周</p>
          <p class="mb-0 mt-1 text-[10.5px] leading-relaxed text-muted">完整周均 · 最近 {{ evaluation.recentActivityChange.recentCompleteWeeks }}/4 周 vs 此前 {{ evaluation.recentActivityChange.previousCompleteWeeks }}/4 周<template v-if="evaluation.recentActivityChange.incompleteWeekStarts.length"> · 已排除 {{ evaluation.recentActivityChange.incompleteWeekStarts.length }} 个不完整周</template></p>
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

    </div>

  </section>
</template>
