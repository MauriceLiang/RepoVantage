<script setup lang="ts">
import { Activity, ArrowRight, Database, GitFork, RefreshCw, Search, Star } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAsyncData } from '@/composables/useAsyncData'
import { useDataSource } from '@/composables/useDataSource'
import { useOverviewChartFilters } from '@/composables/useOverviewChartFilters'
import { buildOverviewChartData } from '@/lib/overviewChartData'
import type { RepositoryDataStatus, RepositoryStatus, RepositorySummary, TaskItem } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import OverviewCharts from './OverviewCharts.vue'

const source = useDataSource()
const router = useRouter()
const ui = useUiStore()
const repositoryRequest = useAsyncData(() => source.listRepositories())
const taskRequest = useAsyncData(() => source.listTasks())
const repositories = computed(() => repositoryRequest.data.value ?? [])
const hasRepositoryData = computed(() => repositories.value.length > 0)
const loading = computed(() => repositoryRequest.loading.value || taskRequest.loading.value)
const repositoryError = computed(() => repositoryRequest.error.value)
const dataCoverageCount = computed(() => repositories.value.filter((repository) => repository.status === 'ready' || repository.status === 'partial').length)
const asOfMs = ref(Date.now())
watch(repositories, () => { asOfMs.value = Date.now() })
const chartData = computed(() => buildOverviewChartData({ repositories: repositories.value, asOfMs: asOfMs.value }))
const chartFilters = useOverviewChartFilters(repositories, asOfMs)
const chartFilterState = chartFilters.filterState
const selectedRepositoryId = chartFilters.selectedRepositoryId
const chartFilteredRepositories = chartFilters.filteredRepositories
const chartFilteredIds = computed(() => chartFilteredRepositories.value.map((repository) => repository.id))
const recentActivityCount = computed(() => chartData.value.active30Count)

const repositorySearch = ref('')
const statusFilter = ref('all')
const sortBy = ref('recent')
const currentPage = ref(1)
const pageSize = 10
const statusOptions = [
  { value: 'all', label: '全部状态' },
  { value: 'attention', label: '需要关注' },
  { value: 'outdated', label: '快照过期或缺失' },
  { value: 'ready', label: '采集完成' },
  { value: 'partial', label: '部分数据' },
  { value: 'running', label: '正在采集' },
  { value: 'idle', label: '待采集' },
  { value: 'failed', label: '采集失败' },
]
const sortOptions = [
  { value: 'recent', label: '最近有更新' },
  { value: 'stars', label: 'Stars 从高到低' },
  { value: 'name', label: '仓库名称' },
]

function needsAttention(repository: RepositorySummary) {
  return repository.status === 'failed'
    || repository.status === 'idle'
    || repository.status === 'partial'
    || repository.dataStatus === 'stale'
    || repository.dataStatus === 'missing'
}

const attentionCount = computed(() => repositories.value.filter(needsAttention).length)
const attentionRepositories = computed(() => [...repositories.value]
  .filter(needsAttention)
  .sort((left, right) => attentionPriority(left) - attentionPriority(right)
    || (dateValue(right.lastAnalyzedAt) ?? 0) - (dateValue(left.lastAnalyzedAt) ?? 0))
  .slice(0, 5))

const filteredRepositories = computed(() => {
  const query = repositorySearch.value.trim().toLocaleLowerCase()
  const filtered = repositories.value.filter((repository) => {
    if (!chartFilters.matchesRepository(repository)) return false
    const searchable = `${repository.fullName} ${repository.description ?? ''} ${repository.language ?? ''}`.toLocaleLowerCase()
    const matchesQuery = !query || searchable.includes(query)
    const matchesStatus = statusFilter.value === 'all'
      || (statusFilter.value === 'attention' && needsAttention(repository))
      || (statusFilter.value === 'outdated' && (repository.dataStatus === 'stale' || repository.dataStatus === 'missing'))
      || repository.status === statusFilter.value
    return matchesQuery && matchesStatus
  })
  return filtered.sort((left, right) => {
    if (sortBy.value === 'stars') return compareNullableDescending(left.stars, right.stars) || left.fullName.localeCompare(right.fullName)
    if (sortBy.value === 'name') return left.fullName.localeCompare(right.fullName)
    return compareNullableDescending(dateValue(left.pushedAt), dateValue(right.pushedAt)) || left.fullName.localeCompare(right.fullName)
  })
})
const pageCount = computed(() => Math.max(1, Math.ceil(filteredRepositories.value.length / pageSize)))
const pageRepositories = computed(() => filteredRepositories.value.slice((currentPage.value - 1) * pageSize, currentPage.value * pageSize))
const rangeStart = computed(() => filteredRepositories.value.length ? (currentPage.value - 1) * pageSize + 1 : 0)
const rangeEnd = computed(() => Math.min(currentPage.value * pageSize, filteredRepositories.value.length))
const selectedRepository = computed(() => repositories.value.find((repository) => repository.id === chartFilters.selectedRepositoryId.value) ?? null)
const selectedRepositoryOutsideList = computed(() => !!selectedRepository.value && !filteredRepositories.value.some((repository) => repository.id === selectedRepository.value?.id))

watch([repositorySearch, statusFilter, sortBy], () => { currentPage.value = 1 })
watch([chartFilters.selectedLanguageKeys, chartFilters.selectedStarsBucket, chartFilters.selectedPushBucket], () => { currentPage.value = 1 }, { deep: true })
watch(pageCount, (count) => { if (currentPage.value > count) currentPage.value = count })

function selectChartRepository(id: string) {
  chartFilters.selectedRepositoryId.value = chartFilters.selectedRepositoryId.value === id ? null : id
  const index = filteredRepositories.value.findIndex((repository) => repository.id === id)
  if (index >= 0) currentPage.value = Math.floor(index / pageSize) + 1
}

function clearSelectedRepository() {
  chartFilters.selectedRepositoryId.value = null
}

function clearChartFilters() {
  chartFilters.clearFilters()
  currentPage.value = 1
}

async function locateSelectedRepository() {
  const id = chartFilters.selectedRepositoryId.value
  if (!id) return
  chartFilters.clearFilters()
  chartFilters.selectedRepositoryId.value = id
  repositorySearch.value = ''
  statusFilter.value = 'all'
  await nextTick()
  const index = filteredRepositories.value.findIndex((repository) => repository.id === id)
  if (index < 0) return
  currentPage.value = Math.floor(index / pageSize) + 1
  await nextTick()
  const row = [...document.querySelectorAll<HTMLElement>('[data-repository-id]')].find((element) => element.dataset.repositoryId === id)
  row?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center' })
}

const activeTasks = computed(() => (taskRequest.data.value ?? []).filter((task) => ['queued', 'running', 'analyzing'].includes(task.status)))
const taskModuleLabel: Record<string, string> = {
  profile: '仓库概况', commits: 'Commit 采集', issues: 'Issue 采集', pulls: 'PR 采集', releases: 'Release 采集',
  collect_repository: '仓库采集', repository: '仓库分析',
}
const taskStatusLabel: Record<string, string> = { queued: '排队中', running: '执行中', analyzing: '分析中' }
const repositoryInput = ref('')
const addingRepository = ref(false)
const addError = ref('')
let pollTimer: number | undefined

function formatNumber(value: number | null | undefined) {
  return value === null || value === undefined ? '—' : value.toLocaleString('zh-CN', { maximumFractionDigits: 1 })
}

function dateValue(value: string | null | undefined): number | null {
  if (!value) return null
  const parsed = Date.parse(value.length === 10 ? `${value}T00:00:00Z` : value)
  return Number.isFinite(parsed) ? parsed : null
}

function compareNullableDescending(left: number | null | undefined, right: number | null | undefined) {
  if (left == null && right == null) return 0
  if (left == null) return 1
  if (right == null) return -1
  return right - left
}

function dateLabel(value: string | null | undefined) {
  if (!value) return '—'
  const timestamp = dateValue(value)
  if (timestamp === null) return value.slice(0, 10)
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'UTC', year: 'numeric', month: '2-digit', day: '2-digit' }).format(timestamp)
}

function statusInfo(value: RepositoryStatus) {
  const metadata: Record<RepositoryStatus, { label: string; tone: 'success' | 'warning' | 'danger' | 'neutral' | 'accent' }> = {
    ready: { label: '采集完成', tone: 'success' },
    partial: { label: '部分数据', tone: 'warning' },
    running: { label: '正在采集', tone: 'accent' },
    idle: { label: '待采集', tone: 'neutral' },
    failed: { label: '采集失败', tone: 'danger' },
  }
  return metadata[value]
}

function freshnessLabel(value: RepositoryDataStatus | undefined, lastAnalyzedAt: string | null) {
  if (value === 'fresh') return '快照新鲜'
  if (value === 'stale') return '快照过期'
  if (value === 'missing') return '暂无快照'
  return lastAnalyzedAt ? '最近采集' : '采集时间未知'
}

function attentionPriority(repository: RepositorySummary) {
  if (repository.status === 'failed') return 0
  if (repository.status === 'idle') return 1
  if (repository.dataStatus === 'stale' || repository.dataStatus === 'missing') return 2
  return 3
}

function attentionReason(repository: RepositorySummary) {
  if (repository.status === 'failed') return '最近一次采集失败'
  if (repository.status === 'idle') return '尚未开始采集'
  if (repository.dataStatus === 'stale') return '本地快照已过期'
  if (repository.dataStatus === 'missing') return '暂无本地快照'
  return '部分分析字段尚未覆盖'
}

function taskProgress(task: TaskItem): number | null {
  const active = task.status === 'running' || task.status === 'analyzing'
  if (active && task.taskType === 'repository_collection' && task.progressMotion === 'bounce') return null
  const value = task.progressPercent
  if (task.progressKind !== 'stages' || typeof value !== 'number' || !Number.isFinite(value)) {
    return active && task.taskType === 'repository_collection' && task.progressMotion === 'forward' ? 0 : null
  }
  return Math.max(0, Math.min(100, value))
}

function taskProgressIndeterminate(task: TaskItem): boolean {
  const active = task.status === 'running' || task.status === 'analyzing'
  if (!active) return false
  if (task.taskType === 'repository_collection' && task.progressMotion === 'forward') return false
  if (task.taskType === 'repository_collection' && task.progressMotion === 'bounce') return true
  return task.progressKind === 'indeterminate'
}

async function refresh() {
  await Promise.all([repositoryRequest.reload(), taskRequest.reload()])
}

async function addRepository() {
  const input = repositoryInput.value.trim()
  if (!input || addingRepository.value) return
  addingRepository.value = true
  addError.value = ''
  try {
    const result = await source.addRepository(input)
    repositoryInput.value = ''
    ui.toast(result.taskId ? '仓库已加入，180 天完整采集任务已排队' : '仓库已加入分析库', result.taskId ? 'warning' : 'success')
    await repositoryRequest.reload()
    void router.push(`/repositories/${result.repositoryId}/overview`)
  } catch (cause) {
    addError.value = cause instanceof Error ? cause.message : '添加仓库失败'
  } finally { addingRepository.value = false }
}

onMounted(() => {
  pollTimer = window.setInterval(() => { if (activeTasks.value.length) void taskRequest.reload() }, 3000)
})
onBeforeUnmount(() => { if (pollTimer !== undefined) window.clearInterval(pollTimer) })
</script>

<template>
  <div class="stack app-page">
    <UiPageHeader :title="hasRepositoryData ? '仓库概览' : '从一个仓库开始'" :description="hasRepositoryData ? `这里汇总你已加入的 ${formatNumber(repositories.length)} 个仓库，优先展示活跃度与本地数据状态。` : '添加要使用或比较的仓库，概览会展示这些仓库的真实快照。'">
      <template #actions>
        <UiButton variant="quiet" :disabled="loading" aria-label="刷新总览数据" @click="refresh"><RefreshCw :size="13" />刷新</UiButton>
        <UiButton variant="outline" @click="router.push('/repositories')">管理仓库 <ArrowRight :size="12" /></UiButton>
      </template>
    </UiPageHeader>

    <UiPanel as="section">
      <form class="toolbar add-repository-form" @submit.prevent="addRepository">
        <label class="search-field"><Database :size="14" /><UiInput v-model="repositoryInput" aria-label="添加 GitHub 仓库" placeholder="输入 owner/repo 或 GitHub 仓库链接" /></label>
        <UiButton variant="primary" type="submit" :loading="addingRepository" :disabled="addingRepository || !repositoryInput.trim()">{{ addingRepository ? '正在添加…' : '添加并分析' }}</UiButton>
        <RouterLink to="/tasks" class="small muted">查看任务</RouterLink>
      </form>
      <p v-if="addError" class="small" role="alert" style="margin:9px 0 0;color:var(--red)">{{ addError }}</p>
    </UiPanel>

    <div v-if="repositoryError" class="notice" role="alert">仓库数据加载失败：{{ repositoryError }}</div>
    <div v-else-if="loading && !repositories.length" class="kpi-grid" aria-label="正在加载总览" aria-busy="true">
      <div v-for="item in 4" :key="item" class="kpi"><span class="gd-skeleton-shimmer block h-3 w-20 rounded" /><span class="gd-skeleton-shimmer mt-3 block h-6 w-24 rounded" /></div>
    </div>
    <UiPanel v-else-if="!hasRepositoryData" as="section" class="onboarding-panel" aria-labelledby="onboarding-title">
      <div class="onboarding-heading">
        <div><h2 id="onboarding-title">从你正在使用或考虑采用的项目开始</h2><p>添加仓库后，这里会汇总项目活跃度、技术栈和本地数据状态。</p></div>
        <UiButton variant="outline" @click="router.push({ name: 'repositories', query: { scope: 'discover' } })">发现仓库 <ArrowRight :size="12" /></UiButton>
      </div>
      <ol class="onboarding-steps">
        <li><span>01</span><div><strong>添加仓库</strong><p>在上方输入 GitHub 地址，或在「发现」中搜索。</p></div></li>
        <li><span>02</span><div><strong>查看采集进度</strong><p>任务完成后，仓库清单会显示可用资料和活动时间。</p></div></li>
        <li><span>03</span><div><strong>比较项目</strong><p>从仓库清单进入项目分析，或在「我的仓库」中选择项目比较。</p></div></li>
      </ol>
    </UiPanel>
    <template v-else>
      <section class="kpi-grid" aria-label="仓库组合摘要">
        <UiMetricCard label="已加入仓库" :value="formatNumber(repositories.length)" note="当前组合中的全部项目" />
        <UiMetricCard label="近 30 天有 Push" :value="formatNumber(recentActivityCount)" note="按 GitHub 最近推送时间统计" />
        <UiMetricCard label="已有分析数据" :value="formatNumber(dataCoverageCount)" :note="`${formatNumber(dataCoverageCount)} / ${formatNumber(repositories.length)} 个仓库可查看分析`" />
        <UiMetricCard label="需要关注" :value="formatNumber(attentionCount)" note="失败、待采集、覆盖不全或快照过期" />
      </section>

      <OverviewCharts
        :data="chartData"
        :filters="chartFilterState"
        :filtered-ids="chartFilteredIds"
        :filtered-count="chartFilteredRepositories.length"
        @toggle-languages="chartFilters.toggleLanguages($event)"
        @toggle-stars-bucket="chartFilters.toggleStarsBucket($event)"
        @toggle-push-bucket="chartFilters.togglePushBucket($event)"
        @select-repository="selectChartRepository"
        @clear-selected-repository="clearSelectedRepository"
        @clear-filters="clearChartFilters"
      />

      <section class="portfolio-grid" aria-label="仓库组合详情">
        <UiPanel as="article" class="repository-panel">
          <div class="panel-heading repository-heading">
            <div><h2 class="panel-title">我的仓库</h2><p class="panel-description">逐项查看技术栈、受欢迎程度、最近活动和本地数据状态</p></div>
            <span class="repository-total mono">{{ formatNumber(filteredRepositories.length) }} / {{ formatNumber(repositories.length) }}</span>
          </div>

          <div class="repository-toolbar">
            <label class="search-field"><Search :size="14" /><UiInput v-model="repositorySearch" type="search" aria-label="搜索已加入的仓库" placeholder="搜索仓库名、语言或说明" /></label>
            <UiSelect v-model="statusFilter" label="按状态筛选" :options="statusOptions" class="repository-filter" />
            <UiSelect v-model="sortBy" label="排序仓库" :options="sortOptions" class="repository-sort" />
          </div>

          <div v-if="selectedRepositoryOutsideList && selectedRepository" class="selection-notice" role="status">
            <span>所选 {{ selectedRepository.fullName }} 被当前图表或列表条件隐藏。</span>
            <button type="button" @click="locateSelectedRepository">清除筛选并定位</button>
          </div>

          <div v-if="pageRepositories.length" class="repository-table-wrap" role="region" aria-label="已加入仓库清单" tabindex="0">
            <table class="portfolio-table">
              <thead><tr><th scope="col">仓库</th><th scope="col">主语言</th><th scope="col">Stars / Forks</th><th scope="col">最近 Push</th><th scope="col">本地数据</th></tr></thead>
              <tbody>
                <tr v-for="repository in pageRepositories" :key="repository.id" :data-repository-id="repository.id" :class="{ 'is-selected': selectedRepositoryId === repository.id }">
                  <td class="repository-name-cell">
                    <RouterLink :to="`/repositories/${repository.id}/overview`" class="repository-name">{{ repository.fullName }}</RouterLink>
                    <p class="repository-description" :title="repository.description ?? ''">{{ repository.description || '暂无仓库说明' }}</p>
                    <UiBadge v-if="repository.archived" class="archive-badge">已归档</UiBadge>
                  </td>
                  <td><span class="language-value">{{ repository.language || '未知语言' }}</span></td>
                  <td><div class="popularity-values"><span :title="`${formatNumber(repository.stars)} Stars`"><Star :size="12" />{{ formatNumber(repository.stars) }}</span><span :title="`${formatNumber(repository.forks)} Forks`"><GitFork :size="12" />{{ formatNumber(repository.forks) }}</span></div></td>
                  <td class="date-cell">{{ dateLabel(repository.pushedAt) }}</td>
                  <td>
                    <div class="repository-data-state"><UiBadge :tone="statusInfo(repository.status).tone">{{ statusInfo(repository.status).label }}</UiBadge></div>
                    <div class="repository-data-note"><span class="freshness-dot" :class="`freshness-dot--${repository.dataStatus ?? 'unknown'}`" />{{ freshnessLabel(repository.dataStatus, repository.lastAnalyzedAt) }}<span class="data-date">{{ repository.lastAnalyzedAt ? `· ${dateLabel(repository.lastAnalyzedAt)}` : '' }}</span></div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="repository-empty-state"><Search :size="18" /><span>没有符合条件的仓库</span><button type="button" @click="repositorySearch = ''; statusFilter = 'all'">清除筛选</button></div>

          <div class="repository-pagination">
            <span class="small muted">显示 {{ rangeStart }}–{{ rangeEnd }} / {{ formatNumber(filteredRepositories.length) }} 个仓库</span>
            <div class="pagination-actions">
              <button type="button" class="page-button" :disabled="currentPage <= 1" @click="currentPage -= 1">上一页</button>
              <span class="page-indicator mono">{{ currentPage }} / {{ pageCount }}</span>
              <button type="button" class="page-button" :disabled="currentPage >= pageCount" @click="currentPage += 1">下一页</button>
            </div>
          </div>
        </UiPanel>

        <aside class="portfolio-aside" aria-label="仓库状态摘要">
          <UiPanel as="section" class="aside-panel">
            <div class="panel-heading"><div><h2 class="panel-title">需要关注</h2><p class="panel-description">优先列出失败、过期或覆盖不全的项目</p></div><span class="aside-count">{{ attentionCount }}</span></div>
            <div v-if="attentionRepositories.length" class="attention-list">
              <RouterLink v-for="repository in attentionRepositories" :key="repository.id" :to="`/repositories/${repository.id}/overview`" class="attention-row">
                <span class="attention-main"><strong>{{ repository.fullName }}</strong><small>{{ attentionReason(repository) }}</small></span>
                <ArrowRight :size="13" />
              </RouterLink>
              <RouterLink v-if="attentionCount > attentionRepositories.length" to="/repositories" class="aside-link">在仓库清单中筛选全部 <ArrowRight :size="12" /></RouterLink>
            </div>
            <p v-else class="aside-empty"><Activity :size="15" />当前没有需要处理的仓库</p>
          </UiPanel>

          <UiPanel as="section" class="aside-panel task-panel">
            <div class="panel-heading"><div><h2 class="panel-title">正在采集</h2><p class="panel-description">本地任务实时状态</p></div><RouterLink to="/tasks" class="aside-link">全部 <ArrowRight :size="12" /></RouterLink></div>
            <div v-if="taskRequest.error.value" class="small task-error" role="alert">任务加载失败：{{ taskRequest.error.value }}</div>
            <div v-else-if="activeTasks.length" class="task-list">
              <RouterLink v-for="task in activeTasks.slice(0, 4)" :key="task.id" :to="task.repositoryId ? `/repositories/${task.repositoryId}/overview` : '/tasks'" class="task-row">
                <span class="task-row-main"><strong>{{ task.repository || '仓库任务' }}</strong><small>{{ taskModuleLabel[task.module] ?? task.module }} · {{ taskStatusLabel[task.status] ?? task.status }}</small></span>
                <span v-if="taskProgress(task) !== null" class="task-progress" role="progressbar" :aria-label="`进度 ${taskProgress(task)}%`" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="Math.round(taskProgress(task)!)"><span :style="{ width: `${taskProgress(task)}%` }" /></span>
                <span v-else-if="taskProgressIndeterminate(task)" class="task-progress" role="progressbar" aria-label="任务正在执行，进度动态显示" aria-valuetext="正在执行，进度动态显示"><span class="indeterminate" /></span>
              </RouterLink>
            </div>
            <p v-else class="aside-empty">当前没有排队或运行中的任务</p>
          </UiPanel>
        </aside>
      </section>

      <p class="helper-note"><Database :size="12" style="vertical-align:-2px" /> Stars、Forks 和 Push 时间来自最近 GitHub 仓库快照；本地分析状态与快照新鲜度分开显示，未采集字段不会补零。</p>
    </template>
  </div>
</template>

<style scoped>
.onboarding-panel { display: grid; gap: 18px; }
.onboarding-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 18px; }
.onboarding-heading h2 { margin: 0; font-size: 16px; }
.onboarding-heading p { margin: 6px 0 0; max-width: 720px; color: var(--muted); font-size: 12px; line-height: 1.6; }
.onboarding-steps { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; margin: 0; padding: 0; list-style: none; }
.onboarding-steps li { display: flex; align-items: flex-start; gap: 10px; padding-top: 13px; border-top: 1px solid var(--line); }
.onboarding-steps li > span { color: var(--primary-ink); font-size: 11px; font-variant-numeric: tabular-nums; font-weight: 700; }
.onboarding-steps strong { font-size: 11px; }
.onboarding-steps p { margin: 4px 0 0; color: var(--muted); font-size: 10.5px; line-height: 1.55; }
.add-repository-form .search-field { flex: 1 1 360px; }
.selection-notice { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 12px; margin: 12px 0; padding: 8px 10px; border: 1px solid color-mix(in srgb, var(--primary) 28%, var(--line)); border-radius: 7px; color: var(--muted); background: var(--primary-soft); font-size: 10.5px; }
.selection-notice button { padding: 4px 7px; border: 0; border-radius: 5px; color: var(--primary-ink); background: transparent; font: inherit; font-weight: 600; cursor: pointer; }
.selection-notice button:hover { background: color-mix(in srgb, var(--primary) 10%, transparent); }
.portfolio-grid { display: grid; grid-template-columns: minmax(0, 1.85fr) minmax(285px, .8fr); gap: 12px; align-items: start; }
.repository-panel { min-width: 0; }
.repository-heading { align-items: flex-start; }
.repository-total, .aside-count { color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.aside-count { display: grid; min-width: 28px; height: 28px; place-items: center; border-radius: 8px; color: var(--primary-ink); background: var(--primary-soft); font-weight: 650; }
.repository-toolbar { display: grid; grid-template-columns: minmax(180px, 1fr) 155px 155px; gap: 8px; margin: 14px 0 12px; }
.repository-toolbar .search-field { min-width: 0; }
.repository-filter, .repository-sort { width: 100%; }
.repository-table-wrap { overflow-x: auto; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.repository-table-wrap:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.portfolio-table { width: 100%; min-width: 760px; border-collapse: collapse; table-layout: fixed; text-align: left; }
.portfolio-table th { padding: 10px 9px; color: var(--muted); font-size: 10.5px; font-weight: 600; white-space: nowrap; }
.portfolio-table td { padding: 12px 9px; border-top: 1px solid var(--line); vertical-align: middle; font-size: 11.5px; }
.portfolio-table tr.is-selected td { background: var(--primary-soft); }
.portfolio-table th:first-child, .portfolio-table td:first-child { padding-left: 2px; }
.portfolio-table th:nth-child(1) { width: 31%; }
.portfolio-table th:nth-child(2) { width: 16%; }
.portfolio-table th:nth-child(3) { width: 18%; }
.portfolio-table th:nth-child(4) { width: 14%; }
.portfolio-table th:nth-child(5) { width: 21%; }
.repository-name { color: var(--ink); font-size: 12px; font-weight: 650; text-decoration: none; }
.repository-name:hover { color: var(--primary-ink); text-decoration: underline; text-underline-offset: 3px; }
.repository-description { max-width: 340px; margin: 3px 0 0; overflow: hidden; color: var(--muted); font-size: 10.5px; line-height: 1.45; text-overflow: ellipsis; white-space: nowrap; }
.archive-badge { margin-top: 5px; }
.language-value { color: var(--ink); }
.popularity-values { display: flex; flex-wrap: wrap; gap: 10px; color: var(--ink); font-variant-numeric: tabular-nums; }
.popularity-values span { display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
.popularity-values svg { color: var(--muted); }
.date-cell { color: var(--muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
.repository-data-state :deep(.badge) { max-width: 100%; }
.repository-data-note { display: flex; align-items: center; gap: 5px; margin-top: 5px; color: var(--muted); font-size: 10px; white-space: nowrap; }
.freshness-dot { width: 6px; height: 6px; flex: none; border-radius: 50%; background: var(--muted); }
.freshness-dot--fresh { background: var(--green); }
.freshness-dot--stale { background: var(--amber); }
.freshness-dot--missing { background: var(--line-strong, var(--muted)); }
.data-date { font-variant-numeric: tabular-nums; }
.repository-pagination { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-top: 12px; }
.pagination-actions { display: flex; align-items: center; gap: 9px; }
.page-button { min-height: 30px; padding: 0 9px; border: 1px solid var(--line); border-radius: 7px; color: var(--ink); background: var(--surface); font: inherit; font-size: 10.5px; cursor: pointer; }
.page-button:hover:not(:disabled) { border-color: color-mix(in srgb, var(--primary) 50%, var(--line)); background: var(--surface-soft); }
.page-button:disabled { opacity: .45; cursor: not-allowed; }
.page-indicator { min-width: 40px; color: var(--muted); font-size: 10.5px; text-align: center; }
.repository-empty-state { display: flex; min-height: 150px; flex-direction: column; align-items: center; justify-content: center; gap: 8px; color: var(--muted); font-size: 11.5px; }
.repository-empty-state button { padding: 3px 6px; border: 0; color: var(--primary-ink); background: transparent; font: inherit; cursor: pointer; }
.portfolio-aside { display: grid; min-width: 0; gap: 12px; }
.aside-panel { min-width: 0; }
.attention-list, .task-list { display: grid; gap: 0; margin-top: 12px; }
.attention-row, .task-row { display: flex; min-width: 0; align-items: center; justify-content: space-between; gap: 10px; padding: 9px 0; border-top: 1px solid var(--line); color: inherit; text-decoration: none; }
.attention-row:first-child, .task-row:first-child { border-top: 0; padding-top: 0; }
.attention-row:hover .attention-main strong, .task-row:hover .task-row-main strong { color: var(--primary-ink); }
.attention-main, .task-row-main { display: grid; min-width: 0; gap: 4px; }
.attention-main strong, .task-row-main strong { overflow: hidden; font-size: 11px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.attention-main small, .task-row-main small { color: var(--muted); font-size: 10px; }
.attention-row > svg { flex: none; color: var(--muted); }
.aside-link { display: inline-flex; align-items: center; gap: 4px; color: var(--primary-ink); font-size: 10.5px; text-decoration: none; }
.attention-list > .aside-link { justify-self: start; margin-top: 8px; }
.aside-empty { display: flex; align-items: center; gap: 7px; margin: 14px 0 2px; color: var(--muted); font-size: 10.5px; }
.task-panel .panel-heading { align-items: center; }
.task-panel .task-list { margin-top: 12px; }
.task-panel .task-row { align-items: center; }
.task-progress { width: 54px; height: 5px; flex: none; overflow: hidden; border-radius: 9px; background: var(--surface-soft); }
.task-progress span { display: block; height: 100%; border-radius: inherit; background: var(--accent); transition: width .3s ease; }
.task-progress .indeterminate { width: 35%; animation: task-pulse 1.2s ease-in-out infinite alternate; }
.task-error { margin-top: 12px; color: var(--red); }
@keyframes task-pulse { from { transform: translateX(0); } to { transform: translateX(180%); } }
@media (max-width: 1080px) {
  .portfolio-grid { grid-template-columns: minmax(0, 1.5fr) minmax(260px, .9fr); }
  .repository-toolbar { grid-template-columns: minmax(150px, 1fr) 142px 142px; }
}
@media (max-width: 860px) {
  .onboarding-heading { flex-direction: column; }
  .onboarding-steps { grid-template-columns: 1fr; gap: 10px; }
  .portfolio-grid { grid-template-columns: 1fr; }
  .portfolio-aside { grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; }
  .task-panel { grid-column: 1 / -1; }
}
@media (max-width: 600px) {
  .repository-toolbar { grid-template-columns: 1fr 1fr; }
  .repository-toolbar .search-field { grid-column: 1 / -1; }
  .portfolio-aside { grid-template-columns: 1fr; }
  .task-panel { grid-column: auto; }
  .repository-pagination { align-items: flex-start; flex-direction: column; }
  .pagination-actions { align-self: flex-end; }
}
</style>
