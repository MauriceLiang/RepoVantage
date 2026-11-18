<script setup lang="ts">
import { Activity, ArrowRight, Database, GitFork, RefreshCw, Star } from 'lucide-vue-next'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { G2Spec } from '@antv/g2'
import G2Chart from '@/components/charts/G2Chart.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useDataSource } from '@/composables/useDataSource'
import type { RepositorySummary, TaskItem } from '@/services/types'
import { useUiStore } from '@/stores/ui'

const source = useDataSource()
const router = useRouter()
const ui = useUiStore()
const repositoryRequest = useAsyncData(() => source.listRepositories())
const taskRequest = useAsyncData(() => source.listTasks())
const repositories = computed(() => repositoryRequest.data.value ?? [])
const languageGroups = computed(() => {
  const counts = new Map<string, number>()
  for (const repository of repositories.value) {
    const language = repository.language || '未知语言'
    counts.set(language, (counts.get(language) ?? 0) + 1)
  }
  return [...counts.entries()]
    .map(([language, repositoryCount]) => ({ language, repositoryCount }))
    .sort((left, right) => right.repositoryCount - left.repositoryCount || left.language.localeCompare(right.language))
})
const topLanguages = computed(() => languageGroups.value.slice(0, 8))
const hasRepositoryData = computed(() => repositories.value.length > 0)
const loading = computed(() => repositoryRequest.loading.value || taskRequest.loading.value)
const repositoryError = computed(() => repositoryRequest.error.value)
const totalStars = computed(() => repositories.value.reduce((total, repository) => total + (repository.stars ?? 0), 0))
const starSampleCount = computed(() => repositories.value.filter((repository) => repository.stars !== null).length)
const comparableRepositoryCount = computed(() => repositories.value.filter((repository) => repository.status === 'ready' || repository.status === 'partial').length)
const activeTasks = computed(() => (taskRequest.data.value ?? []).filter((task) => ['queued', 'running', 'analyzing'].includes(task.status)))
const taskModuleLabel: Record<string, string> = {
  profile: '仓库概况', commits: 'Commit 采集', issues: 'Issue 采集', pulls: 'PR 采集', releases: 'Release 采集',
  collect_repository: '仓库采集', repository: '仓库分析',
}
const taskStatusLabel: Record<string, string> = { queued: '排队中', running: '执行中', analyzing: '分析中' }
const repositoryInput = ref('')
const addingRepository = ref(false)
const addError = ref('')
const activityChanges = ref<{ repo: RepositorySummary; changePercent: number }[]>([])
const changesLoading = ref(false)
const changesError = ref('')
const changeCandidateCount = ref(0)
let changesRequestId = 0
let pollTimer: number | undefined

const createdYearRows = computed(() => {
  const counts = new Map<number, number>()
  for (const repository of repositories.value) {
    const year = Number(repository.createdAt?.slice(0, 4))
    if (Number.isInteger(year) && year >= 2000 && year <= 2100) counts.set(year, (counts.get(year) ?? 0) + 1)
  }
  const years = [...counts.keys()].sort((left, right) => left - right)
  if (!years.length) return []
  return Array.from({ length: years.at(-1)! - years[0] + 1 }, (_, index) => {
    const year = years[0] + index
    return { year: String(year), count: counts.get(year) ?? 0 }
  })
})
const starBuckets = computed(() => {
  const labels = ['< 1k', '1k–5k', '5k–10k', '10k–25k', '25k+']
  const counts = [0, 0, 0, 0, 0]
  for (const repository of repositories.value) {
    if (repository.stars === null) continue
    const index = repository.stars < 1_000 ? 0 : repository.stars < 5_000 ? 1 : repository.stars < 10_000 ? 2 : repository.stars < 25_000 ? 3 : 4
    counts[index] += 1
  }
  return labels.map((label, index) => ({ label, count: counts[index] }))
})
const licenseRows = computed(() => {
  const counts = new Map<string, number>()
  for (const repository of repositories.value) {
    const license = repository.license || '未标注'
    counts.set(license, (counts.get(license) ?? 0) + 1)
  }
  return [...counts.entries()].map(([license, count]) => ({ license, count })).sort((left, right) => right.count - left.count).slice(0, 8)
})
const statusRows = computed(() => {
  const labels = { ready: '已完成', partial: '部分数据', running: '正在更新', idle: '待采集', failed: '采集失败' } as const
  const counts = new Map<string, number>()
  for (const repository of repositories.value) {
    const label = labels[repository.status]
    counts.set(label, (counts.get(label) ?? 0) + 1)
  }
  return [...counts.entries()].map(([status, count]) => ({ status, count }))
})
const scatterRepositories = computed(() => repositories.value.filter((repository) => typeof repository.stars === 'number' && repository.stars > 0 && typeof repository.forks === 'number' && repository.forks > 0))
const knownScatterLanguages = computed(() => new Set(topLanguages.value.map((group) => group.language)))
const scatterData = computed(() => scatterRepositories.value.map((repository) => ({
  fullName: repository.fullName,
  language: repository.language && knownScatterLanguages.value.has(repository.language) ? repository.language : '其他',
  stars: repository.stars!,
  forks: repository.forks!,
  status: repository.status,
})))
const palette = ['#68c63a', '#5d80de', '#eba33a', '#46b8a3', '#f0796b', '#a679d2', '#38a7c7', '#d86c9b', '#89939d']
const languageDomain = computed(() => [...new Set(scatterData.value.map((row) => row.language))])
const languageColors = computed(() => languageDomain.value.map((_, index) => palette[index % palette.length]))
const axisColor = computed(() => ui.isDark ? '#a0a8b0' : '#6e7781')
const gridColor = computed(() => ui.isDark ? '#2b3238' : '#e8ebed')
const axisBase = computed(() => ({ labelFill: axisColor.value, labelFontSize: 9, lineStroke: gridColor.value, tickStroke: gridColor.value, titleFill: axisColor.value }))
const gridStyle = computed(() => ({ stroke: gridColor.value, lineDash: [3, 3] }))
const languageData = computed(() => ({
  name: '仓库',
  children: topLanguages.value.map((group) => ({ name: group.language, language: group.language, repositoryCount: group.repositoryCount })),
}))
const languageSpec = computed<G2Spec>(() => ({
  type: 'treemap',
  data: { value: languageData.value },
  layout: { tile: 'treemapBinary', paddingInner: 2, ignoreParentValue: true },
  encode: { value: 'repositoryCount', color: (datum: { path?: string[] }) => datum.path?.[1] ?? '其他' },
  scale: { color: { domain: topLanguages.value.map((group) => group.language), range: topLanguages.value.map((_, index) => palette[index % palette.length]) } },
  style: { stroke: ui.isDark ? '#15191d' : '#ffffff', lineWidth: 2, labelText: (datum: { data?: { language?: string; repositoryCount?: number } }) => `${datum.data?.language ?? ''}\n${formatNumber(datum.data?.repositoryCount)} 個`, labelFill: '#fff', labelFontSize: 10, labelFontWeight: 600 },
  legend: false,
  tooltip: { title: (datum: { language?: string }) => datum.language ?? '未知语言', items: [{ field: 'repositoryCount', name: '仓库数' }] },
}))
const starSpec = computed<G2Spec>(() => ({
  type: 'interval',
  data: starBuckets.value,
  coordinate: { transform: [{ type: 'transpose' }] },
  encode: { x: 'label', y: 'count', color: 'label' },
  scale: { color: { domain: starBuckets.value.map((item) => item.label), range: palette } },
  axis: { x: { ...axisBase.value, title: false }, y: { ...axisBase.value, title: '仓库数', grid: gridStyle.value } },
  legend: false,
  tooltip: { title: 'label', items: [{ field: 'count', name: '仓库数' }] },
}))
const scatterSpec = computed<G2Spec>(() => ({
  type: 'point',
  data: scatterData.value,
  encode: { x: 'stars', y: 'forks', color: 'language', shape: 'point' },
  scale: {
    x: { type: 'log', base: 10 }, y: { type: 'log', base: 10 },
    color: { domain: languageDomain.value, range: languageColors.value },
  },
  style: { fillOpacity: 0.72, stroke: ui.isDark ? '#20262b' : '#fff', lineWidth: 1 },
  axis: { x: { ...axisBase.value, title: 'Stars（对数轴）', grid: false }, y: { ...axisBase.value, title: 'Forks（对数轴）', grid: gridStyle.value } },
  legend: { color: { position: 'bottom', itemLabelFill: axisColor.value, itemLabelFontSize: 9 } },
  tooltip: { title: 'fullName', items: [
    { field: 'language', name: '主语言' }, { field: 'stars', name: 'Stars', valueFormatter: (value: number) => formatNumber(value) },
    { field: 'forks', name: 'Forks', valueFormatter: (value: number) => formatNumber(value) }, { field: 'status', name: '本地数据状态' },
  ] },
  interaction: { brushHighlight: true, tooltip: { shared: false } },
}))
const createdSpec = computed<G2Spec>(() => ({
  type: 'interval', data: createdYearRows.value, encode: { x: 'year', y: 'count' },
  scale: { x: { padding: 0.2 } },
  style: { fill: '#5d80de' },
  axis: { x: { ...axisBase.value, title: false }, y: { ...axisBase.value, title: '仓库数', grid: gridStyle.value } },
  tooltip: { title: 'year', items: [{ field: 'count', name: '仓库数' }] },
}))
const licenseSpec = computed<G2Spec>(() => ({
  type: 'interval', data: licenseRows.value, coordinate: { transform: [{ type: 'transpose' }] },
  encode: { x: 'license', y: 'count', color: 'license' },
  scale: { color: { domain: licenseRows.value.map((item) => item.license), range: licenseRows.value.map((_, index) => palette[index % palette.length]) } },
  axis: { x: { ...axisBase.value, title: false }, y: { ...axisBase.value, title: '仓库数', grid: gridStyle.value } },
  legend: false,
  tooltip: { title: 'license', items: [{ field: 'count', name: '仓库数' }] },
}))
const statusSpec = computed<G2Spec>(() => ({
  type: 'interval', data: statusRows.value, coordinate: { transform: [{ type: 'transpose' }] },
  encode: { x: 'status', y: 'count', color: 'status' },
  scale: { color: { domain: statusRows.value.map((item) => item.status), range: palette } },
  axis: { x: { ...axisBase.value, title: false }, y: { ...axisBase.value, title: '仓库数', grid: gridStyle.value } },
  legend: false,
  tooltip: { title: 'status', items: [{ field: 'count', name: '仓库数' }] },
}))

watch([repositories, () => repositoryRequest.loading.value], async ([items, repositoriesLoading]) => {
  const requestId = ++changesRequestId
  activityChanges.value = []
  changesError.value = ''
  if (repositoriesLoading) return
  if (!items.length) { changesLoading.value = false; return }
  const candidates = items.filter((repo) => repo.status === 'ready' || repo.status === 'partial').slice(0, 5)
  changeCandidateCount.value = candidates.length
  if (!candidates.length) { changesLoading.value = false; return }
  changesLoading.value = true
  const results = await Promise.allSettled(candidates.map((repo) => source.getActivityTrend(repo.id)))
  if (requestId !== changesRequestId) return
  const available: { repo: RepositorySummary; changePercent: number }[] = []
  const failures: unknown[] = []
  for (const [index, result] of results.entries()) {
    if (result.status === 'fulfilled') {
      if (result.value.changePercent !== null) available.push({ repo: candidates[index], changePercent: result.value.changePercent })
    } else failures.push(result.reason)
  }
  activityChanges.value = available.sort((left, right) => Math.abs(right.changePercent) - Math.abs(left.changePercent)).slice(0, 3)
  if (failures.length === candidates.length) changesError.value = String(failures[0] instanceof Error ? failures[0].message : '趋势数据读取失败')
  else if (failures.length) changesError.value = `${failures.length} 个仓库的趋势暂时无法读取`
  changesLoading.value = false
}, { immediate: true })

function formatNumber(value: number | null | undefined) {
  return value === null || value === undefined ? '—' : value.toLocaleString('zh-CN', { maximumFractionDigits: 1 })
}
function taskProgress(task: TaskItem): number | null {
  const value = task.progressPercent
  if (task.progressKind !== 'stages' || typeof value !== 'number' || !Number.isFinite(value)) return null
  return Math.max(0, Math.min(100, value))
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
    ui.toast(result.taskId ? '仓库已加入，采集任务已排队' : '仓库已加入分析库', result.taskId ? 'warning' : 'success')
    await repositoryRequest.reload()
    void router.push(`/repositories/${result.repositoryId}/overview`)
  } catch (cause) {
    addError.value = cause instanceof Error ? cause.message : '添加仓库失败'
  } finally { addingRepository.value = false }
}
onMounted(() => {
  pollTimer = window.setInterval(() => { if (activeTasks.value.length) void taskRequest.reload() }, 3000)
})
onBeforeUnmount(() => {
  if (pollTimer !== undefined) window.clearInterval(pollTimer)
  changesRequestId += 1
})
</script>

<template>
  <div class="stack app-page">
    <UiPageHeader :title="hasRepositoryData ? '仓库概览' : '从一个仓库开始'" :description="hasRepositoryData ? `这里汇总你已加入的 ${formatNumber(repositories.length)} 个仓库及本地采集数据。` : '添加要使用或比较的仓库，概览会展示这些仓库的真实快照。'">
      <template #actions>
        <UiButton variant="quiet" :disabled="loading" aria-label="刷新总览数据" @click="refresh"><RefreshCw :size="13" />刷新</UiButton>
        <UiButton variant="outline" @click="router.push('/repositories')">进入仓库 <ArrowRight :size="12" /></UiButton>
      </template>
    </UiPageHeader>

    <UiPanel as="section">
      <form class="toolbar" @submit.prevent="addRepository">
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
        <div><h2 id="onboarding-title">从你正在使用或考虑采用的项目开始</h2><p>添加仓库后，这里会汇总 Stars、技术栈、许可证与采集状态。</p></div>
        <UiButton variant="outline" @click="router.push({ name: 'repositories', query: { scope: 'discover' } })">发现仓库 <ArrowRight :size="12" /></UiButton>
      </div>
      <ol class="onboarding-steps">
        <li><span>01</span><div><strong>添加仓库</strong><p>在上方输入 GitHub 地址，或在「发现」中搜索。</p></div></li>
        <li><span>02</span><div><strong>查看采集进度</strong><p>任务完成后，仓库会显示可用的资料和活动数据。</p></div></li>
        <li><span>03</span><div><strong>回到概览比较</strong><p>图表只汇总已加入仓库中实际采集到的字段。</p></div></li>
      </ol>
    </UiPanel>
    <template v-else>
    <section class="kpi-grid" aria-label="仓库总览">
      <UiMetricCard label="当前仓库" :value="formatNumber(repositories.length)" note="仅统计你主动加入的仓库" />
      <UiMetricCard label="累计 Stars" :value="starSampleCount ? formatNumber(totalStars) : '—'" :note="starSampleCount ? `${formatNumber(starSampleCount)} 个仓库有 Stars 数据` : '暂无 Stars 快照'" />
      <UiMetricCard label="技术栈数量" :value="formatNumber(languageGroups.length)" note="按仓库主语言统计" />
      <UiMetricCard label="已有采集数据" :value="formatNumber(comparableRepositoryCount)" note="可进入仓库页查看或比较" />
    </section>

    <section class="chart-grid" aria-label="仓库数据分布图表">
      <UiPanel as="article" class="chart-panel"><div class="panel-heading"><div><h2 class="panel-title">编程语言构成</h2><p class="panel-description">按已加入仓库的主语言统计</p></div></div><G2Chart v-if="hasRepositoryData" :spec="languageSpec" label="当前仓库主语言矩形树图" :height="226" /><div v-else class="empty-state small">添加仓库后显示你的技术栈构成</div></UiPanel>
      <UiPanel as="article" class="chart-panel"><div class="panel-heading"><div><h2 class="panel-title">Stars 关注度分布</h2><p class="panel-description">按仓库 Stars 区间比较数量，缺失 Stars 不计为零</p></div><Star :size="15" class="muted" /></div><G2Chart v-if="starSampleCount" :spec="starSpec" label="Stars 区间横向条形图" :height="226" /><div v-else class="empty-state small">暂无 Stars 快照</div></UiPanel>
      <UiPanel as="article" class="chart-panel"><div class="panel-heading"><div><h2 class="panel-title">Stars 与 Forks</h2><p class="panel-description">当前仓库关注度与复刻数分布，使用对数坐标</p></div><GitFork :size="15" class="muted" /></div><G2Chart v-if="scatterData.length" :spec="scatterSpec" label="当前仓库 Stars 与 Forks 散点图；可框选高亮" :height="226" /><div v-else class="empty-state small">暂无 Stars 与 Forks 快照</div></UiPanel>
      <UiPanel as="article" class="chart-panel"><div class="panel-heading"><div><h2 class="panel-title">仓库创建年份</h2><p class="panel-description">按 GitHub 创建年份展示数量</p></div></div><G2Chart v-if="createdYearRows.length" :spec="createdSpec" label="仓库创建年份频数图" :height="226" /><div v-else class="empty-state small">暂无创建日期快照</div></UiPanel>
      <UiPanel as="article" class="chart-panel"><div class="panel-heading"><div><h2 class="panel-title">开源许可证分布</h2><p class="panel-description">按仓库快照中的 SPDX 许可证分类</p></div></div><G2Chart v-if="repositories.length" :spec="licenseSpec" label="当前仓库开源许可证横向分布图" :height="226" /><div v-else class="empty-state small">添加仓库后显示许可证分布</div></UiPanel>
      <UiPanel as="article" class="chart-panel"><div class="panel-heading"><div><h2 class="panel-title">本地数据状态</h2><p class="panel-description">查看已加入仓库的采集进度</p></div><Activity :size="15" class="muted" /></div><G2Chart v-if="repositories.length" :spec="statusSpec" label="当前仓库本地采集状态分布" :height="226" /><div v-else class="empty-state small">添加仓库后显示采集状态</div></UiPanel>
    </section>

    <section class="detail-grid" aria-label="近期状态">
      <UiPanel as="article">
        <div class="panel-heading"><div><h2 class="panel-title">近期 Commit 变化</h2><p class="panel-description">检查最近采集的最多 5 个可分析仓库；比较最近 4 个完整周与前 4 周</p></div><ArrowRight :size="14" class="muted" /></div>
        <p v-if="changesLoading" class="small muted">正在读取最近活动变化…</p>
        <p v-else-if="changesError" class="small" role="status">部分趋势读取失败：{{ changesError }}</p>
        <div v-if="activityChanges.length" class="details-list">
          <RouterLink v-for="item in activityChanges" :key="item.repo.id" :to="`/repositories/${item.repo.id}/activity`" class="detail-line"><span>{{ item.repo.fullName }}</span><strong :class="item.changePercent < 0 ? 'trend-down' : 'trend-up'">{{ item.changePercent > 0 ? '+' : '' }}{{ item.changePercent.toFixed(1) }}%</strong></RouterLink>
        </div>
        <p v-else-if="!changesLoading && !changesError" class="small muted">{{ changeCandidateCount ? '最近窗口没有可比较的完整周 Commit 数据。' : '暂无已完成采集的仓库。' }}</p>
      </UiPanel>
      <UiPanel as="article">
        <div class="panel-heading"><div><h2 class="panel-title">进行中的采集任务</h2><p class="panel-description">任务状态由本机数据服务返回</p></div><RouterLink to="/tasks" class="small">查看全部</RouterLink></div>
        <div v-if="taskRequest.error.value" class="small" role="alert">任务加载失败：{{ taskRequest.error.value }}</div>
        <div v-else-if="activeTasks.length" class="details-list">
          <RouterLink v-for="task in activeTasks.slice(0, 4)" :key="task.id" :to="task.repositoryId ? `/repositories/${task.repositoryId}/overview` : '/tasks'" class="task-row">
            <span class="task-row__main"><strong>{{ task.repository || '仓库任务' }}</strong><span class="small muted">{{ taskModuleLabel[task.module] ?? task.module }} · {{ taskStatusLabel[task.status] ?? task.status }}</span></span>
            <span v-if="taskProgress(task) !== null" class="task-progress" :aria-label="`进度 ${taskProgress(task)}%`"><span :style="{ width: `${taskProgress(task)}%` }" /></span>
          </RouterLink>
        </div>
        <p v-else class="small muted">当前没有排队或运行中的任务。</p>
      </UiPanel>
    </section>
    <p class="helper-note"><Database :size="12" style="vertical-align:-2px" /> 图表只使用你已加入仓库的本地快照；未采集的字段不会补零。在「我的仓库」中可以勾选项目进行比较。</p>
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
.trend-up { color: var(--green); }
.trend-down { color: var(--red); }
.task-row { display:flex; align-items:center; justify-content:space-between; gap:12px; color:inherit; text-decoration:none; }
.task-row__main { display:grid; gap:3px; min-width:0; }
.task-progress { width:64px; height:5px; flex:none; overflow:hidden; border-radius:9px; background:var(--surface-soft); }
.task-progress span { display:block; height:100%; border-radius:inherit; background:var(--accent); }
@media (max-width: 760px) {
  .onboarding-heading { flex-direction: column; }
  .onboarding-steps { grid-template-columns: 1fr; gap: 10px; }
}
</style>
