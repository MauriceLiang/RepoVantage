<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle } from 'reka-ui'
import { RefreshCw, Trash2 } from 'lucide-vue-next'
import GdBadge from '@/components/ui/GdBadge.vue'
import GdButton from '@/components/ui/GdButton.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useDataSource } from '@/composables/useDataSource'
import type { TaskItem, TaskStatus } from '@/services/types'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const router = useRouter()
const source = useDataSource()
const { data, loading, error, reload } = useAsyncData(() => source.listTasks())
const tasks = ref<TaskItem[]>([])
const retrying = ref<string | null>(null)
const pendingAction = ref<{ kind: 'delete'; task: TaskItem } | { kind: 'clear' } | null>(null)
const actionError = ref('')
const mutating = ref(false)
const dialogTrigger = ref<HTMLElement | null>(null)
let pollTimer: number | undefined

const statusMeta: Record<TaskStatus, { text: string; variant: 'default' | 'warn' | 'plain' }> = {
  queued: { text: '排队中', variant: 'plain' },
  running: { text: '正在采集', variant: 'default' },
  analyzing: { text: '正在分析', variant: 'default' },
  done: { text: '已完成', variant: 'default' },
  partial: { text: '部分完成', variant: 'warn' },
  failed: { text: '失败', variant: 'warn' },
  cancelled: { text: '已取消', variant: 'plain' },
}
const moduleLabel: Record<string, string> = {
  profile: '仓库概况', commits: 'Commit 采集', issues: 'Issue 采集', pulls: 'PR 采集', releases: 'Release 采集', collect_repository: '仓库采集',
}
const counts = ref({ running: 0, queued: 0, partial: 0, failed: 0 })
const filter = ref('all')
const filterOptions = [
  { value: 'all', label: '全部任务' }, { value: 'active', label: '进行中' },
  { value: 'failed', label: '失败或部分完成' }, { value: 'done', label: '已完成' },
]
const filteredTasks = computed(() => tasks.value.filter((task) => {
  if (filter.value === 'active') return ['queued', 'running', 'analyzing'].includes(task.status)
  if (filter.value === 'failed') return task.status === 'failed' || task.status === 'partial'
  if (filter.value === 'done') return task.status === 'done'
  return true
}))
const confirmationTitle = computed(() => pendingAction.value?.kind === 'clear' ? '清除已结束任务？' : '删除任务？')
const confirmationDescription = computed(() => pendingAction.value?.kind === 'clear'
  ? '将清除全部已完成、部分完成、失败和已取消任务。排队或运行中的任务会保留，仓库、采集结果和分析数据不会受影响。'
  : `将删除「${pendingAction.value?.kind === 'delete' ? pendingAction.value.task.repository : ''}」的任务记录。仓库、采集结果和分析数据会保留。`)

function sync(value: TaskItem[]) {
  tasks.value = value.map((task) => ({ ...task }))
  counts.value = {
    running: tasks.value.filter((task) => task.status === 'running' || task.status === 'analyzing').length,
    queued: tasks.value.filter((task) => task.status === 'queued').length,
    partial: tasks.value.filter((task) => task.status === 'partial').length,
    failed: tasks.value.filter((task) => task.status === 'failed').length,
  }
}

function canDeleteTask(task: TaskItem): boolean {
  return task.status !== 'queued' && task.status !== 'running' && task.status !== 'analyzing'
}

function rememberDialogTrigger() {
  dialogTrigger.value = document.activeElement instanceof HTMLElement ? document.activeElement : null
  actionError.value = ''
}

function askDelete(task: TaskItem) {
  if (!canDeleteTask(task)) return
  rememberDialogTrigger()
  pendingAction.value = { kind: 'delete', task }
}

function askClear() {
  rememberDialogTrigger()
  pendingAction.value = { kind: 'clear' }
}

function closeConfirmation() {
  if (mutating.value) return
  pendingAction.value = null
  actionError.value = ''
}

function restoreDialogFocus(event: Event) {
  if (dialogTrigger.value?.isConnected && !dialogTrigger.value.matches(':disabled')) {
    event.preventDefault()
    dialogTrigger.value.focus()
  }
  dialogTrigger.value = null
}

async function confirmAction() {
  const action = pendingAction.value
  if (!action || mutating.value) return
  mutating.value = true
  actionError.value = ''
  try {
    if (action.kind === 'delete') {
      await source.deleteTask(action.task.id)
      pendingAction.value = null
      ui.toast('任务记录已删除')
    } else {
      const deletedCount = await source.clearTaskHistory()
      pendingAction.value = null
      ui.toast(deletedCount ? `已清除 ${deletedCount} 条已结束任务记录` : '没有可清除的已结束任务')
    }
    await reload()
  } catch (cause) {
    actionError.value = cause instanceof Error ? cause.message : '删除任务失败'
  } finally {
    mutating.value = false
  }
}

watch(data, (value) => { if (value) sync(value) }, { immediate: true })
onMounted(() => {
  pollTimer = window.setInterval(() => {
    if (tasks.value.some((task) => task.status === 'queued' || task.status === 'running' || task.status === 'analyzing')) void reload()
  }, 3000)
})
onBeforeUnmount(() => { if (pollTimer !== undefined) window.clearInterval(pollTimer) })

async function refresh() {
  await reload()
}

async function retry(task: TaskItem) {
  retrying.value = task.id
  try {
    await source.retryTask(task.id)
    ui.toast(`已重新排队：${task.repository}`, 'warning')
    await reload()
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '重试任务失败', 'error')
  } finally {
    retrying.value = null
  }
}

function view(task: TaskItem) {
  if (task.taskType === 'dataset_import') void router.push('/repositories')
  else if (task.repositoryId) void router.push(`/repositories/${task.repositoryId}/overview`)
}

function percent(task: TaskItem): number | null {
  const value = task.progressPercent
  if ((task.progressKind !== 'stages' && task.progressKind !== 'records') || typeof value !== 'number' || !Number.isFinite(value)) return null
  return Math.min(100, Math.max(0, value))
}

function displayedPercent(task: TaskItem): number | null {
  const active = task.status === 'running' || task.status === 'analyzing'
  if (active && task.taskType === 'repository_collection' && task.progressMotion === 'bounce') return null
  const current = percent(task)
  return active && task.taskType === 'repository_collection' && task.progressMotion === 'forward'
    ? current ?? 0
    : current
}

function showIndeterminate(task: TaskItem): boolean {
  const active = task.status === 'running' || task.status === 'analyzing'
  if (!active) return false
  if (task.taskType === 'repository_collection' && task.progressMotion === 'forward') return false
  if (task.taskType === 'repository_collection' && task.progressMotion === 'bounce') return true
  return task.progressKind === 'indeterminate'
}

function taskScopeLabel(task: TaskItem): string {
  if (task.scopeKind === 'window') return `完整窗口${task.windowDays ? ` · ${task.windowDays} 天` : ''}`
  if (task.scopeKind === 'quick') return `快速采集${task.windowDays ? ` · ${task.windowDays} 天` : ''}`
  if (task.scopeKind === 'incremental') return '增量同步'
  if (task.scopeKind === 'backfill') return '历史回填'
  if (task.scopeKind === 'maintenance') return '52 周维护活动'
  return ''
}

function taskDetail(task: TaskItem): string {
  if (task.taskType === 'dataset_import') {
    if (task.processedRecords !== null && task.processedRecords !== undefined && task.totalRecords !== null && task.totalRecords !== undefined) {
      return `${task.processedRecords.toLocaleString('en-US')} / ${task.totalRecords.toLocaleString('en-US')} 条记录${task.currentFile ? ` · ${task.currentFile}` : ''}`
    }
    if (task.status === 'done' && task.result) {
      const imported = Number(task.result.imported_count ?? 0)
      const events = Number(task.result.event_count ?? 0)
      const skipped = Number(task.result.skipped_count ?? 0)
      return `新增 ${imported.toLocaleString('en-US')} 个仓库 · 活动记录 ${events.toLocaleString('en-US')} 条 · 跳过 ${skipped.toLocaleString('en-US')} 条${task.version ? ` · ${task.version}` : ''}`
    }
    return task.version ? `数据集导入 · ${task.version}` : '数据集导入'
  }
  const scopeLabel = taskScopeLabel(task)
  const windowDates = task.windowStart && task.windowEnd
    ? `${task.windowStart.slice(0, 10)} 至 ${task.windowEnd.slice(0, 10)}`
    : ''
  const active = task.modules?.find((module) => module.status === 'running')
  if (active) return `${scopeLabel ? `${scopeLabel} · ` : ''}${windowDates ? `${windowDates} · ` : ''}${active.pagesFetched} 页 · ${active.observedItems.toLocaleString('en-US')} 条${active.pageCap ? ` / ${active.pageCap} 页预算` : ''}`
  if (task.resumeAfter) return `${scopeLabel ? `${scopeLabel} · ` : ''}${windowDates ? `${windowDates} · ` : ''}限流暂停 · 预计 ${new Date(task.resumeAfter).toLocaleString() } 恢复`
  if ((task.scopeKind === 'quick' || task.scopeKind === 'window') && windowDates) return `${scopeLabel} · ${windowDates}`
  if (task.scopeKind === 'incremental' && task.windowStart && task.windowEnd) return `增量同步 · 重叠区间 ${task.windowStart.slice(0, 10)} 至 ${task.windowEnd.slice(0, 10)}`
  if (task.scopeKind === 'backfill' && task.windowStart && task.windowEnd) return `历史回填 · ${task.windowStart.slice(0, 10)} 至 ${task.windowEnd.slice(0, 10)}`
  if (scopeLabel) return `${scopeLabel}${windowDates ? ` · ${windowDates}` : ''}`
  const latest = task.modules?.filter((module) => module.pagesFetched > 0).at(-1)
  return latest ? `已采集 ${latest.pagesFetched} 页 · ${latest.observedItems.toLocaleString('en-US')} 条` : ''
}
</script>

<template>
  <div class="stack app-page">
    <UiPageHeader title="任务中心" description="仓库采集由后端 Worker 执行；进度按采集阶段和接口页数预算估算，不代表历史覆盖率。">
      <template #actions><UiButton variant="quiet" :disabled="loading" @click="refresh"><RefreshCw :size="13" />刷新</UiButton></template>
    </UiPageHeader>

    <section class="kpi-grid" aria-label="任务状态统计">
      <UiMetricCard label="运行中" :value="counts.running" note="采集或分析中" />
      <UiMetricCard label="排队" :value="counts.queued" note="等待 Worker 处理" />
      <UiMetricCard label="部分完成" :value="counts.partial" note="可按需继续采集" />
      <UiMetricCard label="失败" :value="counts.failed" note="可查看原因并重试" />
    </section>

    <UiPanel as="section" class="task-panel">
      <div class="panel-heading">
      <div><h2 class="panel-title">任务记录</h2><p class="panel-description">新采集按阶段与分页进度计算；未知总页数时才估算。更新任务动态显示，百分比不代表历史覆盖率。</p></div>
        <div class="task-toolbar">
          <GdButton v-if="tasks.length" variant="ghost" class="task-destructive-action" aria-label="清除全部已结束任务" @click="askClear">
            <Trash2 :size="13" aria-hidden="true" />清除已结束
          </GdButton>
          <UiSelect v-model="filter" label="任务筛选" style="width:190px" :options="filterOptions" />
        </div>
      </div>
      <div v-if="error && !tasks.length" class="notice" role="alert">任务加载失败：{{ error }}</div>
      <div v-else-if="loading && !tasks.length" class="stack" aria-busy="true"><div v-for="i in 4" :key="i" class="gd-skeleton-shimmer h-16 rounded" /></div>
      <div v-else-if="!filteredTasks.length" class="empty-state">{{ tasks.length ? '当前筛选没有任务。' : '当前没有任务。可以从仓库页添加仓库。' }}</div>
      <template v-else>
        <p v-if="error" class="small error-text" role="status">刷新失败，仍显示上次获取的任务状态：{{ error }}</p>
        <div class="task-table-head"><span>任务 / 类型</span><span>进度</span><span>状态</span><span>更新时间</span><span>当前阶段</span><span>操作</span></div>
        <TransitionGroup tag="div" name="gd-motion-list" class="task-list">
          <article v-for="task in filteredTasks" :key="task.id" data-testid="task-row" :data-task-id="task.id" :data-scope-kind="task.scopeKind" :data-window-days="task.windowDays" class="task-row">
            <div class="task-identity">
              <strong>{{ task.repository }}</strong>
              <span class="small muted">{{ task.taskType === 'dataset_import' ? `数据集导入${task.version ? ` · ${task.version}` : ''}` : `${moduleLabel[task.module] ?? task.module}${taskScopeLabel(task) ? ` · ${taskScopeLabel(task)}` : ''}` }}<span v-if="task.isDemo"> · 演示任务</span></span>
              <span v-if="taskDetail(task)" class="small muted task-detail" :title="taskDetail(task)">{{ taskDetail(task) }}</span>
            </div>
            <div class="task-progress-cell">
              <div
                v-if="displayedPercent(task) !== null"
                class="task-progress"
                role="progressbar"
                :aria-label="`${task.repository} 任务进度`"
                aria-valuemin="0"
                aria-valuemax="100"
                :aria-valuenow="Math.round(displayedPercent(task)!)"
              ><span :style="{ width: `${displayedPercent(task)}%` }" /></div>
              <div
                v-else-if="showIndeterminate(task)"
                class="task-progress"
                role="progressbar"
                :aria-label="`${task.repository} 任务进度`"
                aria-valuetext="正在执行，进度动态显示"
              ><span class="indeterminate" /></div>
              <span v-else class="task-progress-placeholder" aria-hidden="true" />
              <span class="task-progress-value small muted mono">{{ displayedPercent(task) === null ? '—' : `${Math.round(displayedPercent(task)!)}%` }}</span>
            </div>
            <div><GdBadge :variant="statusMeta[task.status].variant">{{ task.taskType === 'dataset_import' && (task.status === 'running' || task.status === 'analyzing') ? '正在导入' : statusMeta[task.status].text }}</GdBadge></div>
            <time class="small muted">{{ task.updatedAt }}</time>
            <div class="task-stage">
              <span :title="task.stage">{{ task.error ?? task.stage }}</span>
            </div>
            <div class="task-actions">
              <GdButton v-if="task.status === 'failed' || task.status === 'partial'" variant="outline" size="sm" :disabled="retrying === task.id" @click="retry(task)">{{ retrying === task.id ? '排队中…' : '重试' }}</GdButton>
              <GdButton v-else variant="ghost" size="sm" @click="view(task)">{{ task.taskType === 'dataset_import' ? task.status === 'done' ? '查看结果' : '查看进度' : '查看仓库' }}</GdButton>
              <GdButton v-if="canDeleteTask(task)" variant="ghost" size="sm" class="task-delete-button" :disabled="mutating" :aria-label="`删除 ${task.repository} 任务`" title="删除任务" @click="askDelete(task)">
                <Trash2 :size="13" aria-hidden="true" /><span class="sr-only">删除任务</span>
              </GdButton>
            </div>
          </article>
        </TransitionGroup>
      </template>
    </UiPanel>

    <DialogRoot :open="pendingAction !== null" @update:open="(open) => !open && closeConfirmation()">
      <DialogPortal to=".app-layout">
        <DialogOverlay class="task-dialog-overlay" />
        <DialogContent class="task-confirm-dialog" @close-auto-focus="restoreDialogFocus">
          <DialogTitle class="task-dialog-title">{{ confirmationTitle }}</DialogTitle>
          <DialogDescription class="task-dialog-description">{{ confirmationDescription }}</DialogDescription>
          <p class="small muted task-dialog-note">此操作不可撤销。</p>
          <p v-if="actionError" class="small task-dialog-error" role="alert">{{ actionError }}</p>
          <div class="task-dialog-actions">
            <UiButton variant="quiet" :disabled="mutating" @click="closeConfirmation">取消</UiButton>
            <UiButton variant="danger" :loading="mutating" @click="confirmAction">
              <Trash2 :size="13" aria-hidden="true" />{{ pendingAction?.kind === 'clear' ? '清除任务' : '删除任务' }}
            </UiButton>
          </div>
        </DialogContent>
      </DialogPortal>
    </DialogRoot>
  </div>
</template>

<style scoped>
.task-panel { min-width:0; }
.task-table-head,.task-row { display:grid; grid-template-columns:minmax(220px,1.1fr) 228px 96px 108px minmax(160px,1fr) 108px; align-items:center; gap:14px; }
.task-table-head { padding:0 8px 10px; border-bottom:1px solid var(--line); color:var(--muted); font-size:11px; }
.task-row { padding:12px 8px; border-bottom:1px solid var(--line); }
.task-identity,.task-stage { display:grid; min-width:0; gap:4px; }
.task-identity strong,.task-detail,.task-stage>span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.task-progress-cell { display:grid; grid-template-columns:minmax(0,1fr) 42px; align-items:center; gap:10px; width:228px; min-width:0; }
.task-progress-value { text-align:right; }
.task-progress-placeholder { display:block; height:8px; }
.task-row>time,.task-row>.task-stage { justify-self:start; text-align:left; }
.task-toolbar,.task-actions { display:flex; align-items:center; justify-content:flex-end; gap:6px; }
.task-destructive-action,.task-delete-button { color:var(--red) !important; }
.task-destructive-action:hover:not(:disabled),.task-delete-button:hover:not(:disabled) { background:color-mix(in srgb,var(--red) 9%,var(--surface)); }
.task-progress { width:100%; min-width:0; height:8px; overflow:hidden; border-radius:999px; background:var(--track); box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--line) 75%,transparent); }
.task-progress>span { display:block; height:100%; border-radius:inherit; background:var(--primary); transition:width .3s ease; }
.task-progress .indeterminate { width:35%; animation:task-pulse 1.2s ease-in-out infinite alternate; }
.error-text { color:var(--red); }
.task-dialog-overlay { position:fixed; z-index:40; inset:0; background:rgb(0 0 0 / 32%); }
.task-confirm-dialog { position:fixed; z-index:50; inset:0; margin:auto; width:min(440px,calc(100% - 32px)); height:fit-content; max-height:calc(100dvh - 32px); overflow:auto; padding:20px; border:1px solid var(--line); border-radius:var(--radius); background:var(--surface); box-shadow:0 16px 50px rgb(22 29 35 / 20%); }
.task-dialog-title { margin:0 0 8px; font-size:17px; font-weight:650; }
.task-dialog-description,.task-dialog-note { margin:0; line-height:1.65; }
.task-dialog-note { margin-top:8px; }
.task-dialog-error { margin:10px 0 0; color:var(--red); }
.task-dialog-actions { display:flex; justify-content:flex-end; gap:8px; margin-top:20px; }
@keyframes task-pulse { from { transform:translateX(0); } to { transform:translateX(180%); } }
@media(max-width:1280px) { .task-table-head { display:none; } .task-row { grid-template-columns:minmax(0,1fr) auto; gap:8px 14px; } .task-identity { grid-column:1/-1; } .task-progress-cell { grid-column:1; grid-row:2; width:min(228px,100%); } .task-row>div:nth-child(3) { grid-column:2; grid-row:2; } .task-row>time { grid-column:1; grid-row:3; } .task-stage { grid-column:1/-1; grid-row:4; } .task-actions { grid-column:2; grid-row:3; } }
@media(max-width:600px) { .task-toolbar { flex-wrap:wrap; } .task-row { align-items:start; } .task-progress-cell { grid-template-columns:minmax(72px,1fr) 42px; width:min(228px,100%); } }
</style>
