<script setup lang="ts">
import { Activity, ArrowRight, Database, GitCommitHorizontal, GitFork, RefreshCw, Star } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { EChartsOption } from 'echarts'
import ChartPanel from '../components/ChartPanel.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useDataSource } from '@/composables/useDataSource'
import { useUiStore } from '@/stores/ui'

const source = useDataSource()
const router = useRouter()
const ui = useUiStore()
const dashboardRequest = useAsyncData(() => source.getOverviewDashboard())
const repositoryRequest = useAsyncData(() => source.listRepositories())

const dashboard = computed(() => dashboardRequest.data.value)
const repositories = computed(() => repositoryRequest.data.value ?? [])
const courseRepositories = computed(() => dashboard.value?.courseRepositories ?? [])
const languageGroups = computed(() => [...(dashboard.value?.courseLanguageGroups ?? [])]
  .sort((left, right) => right.repositoryCount - left.repositoryCount || left.language.localeCompare(right.language)))
const topLanguages = computed(() => languageGroups.value.slice(0, 8))
const hasDashboardData = computed(() => (dashboard.value?.repositoryCount ?? 0) > 0)
const loading = computed(() => dashboardRequest.loading.value || repositoryRequest.loading.value)
const dashboardError = computed(() => dashboardRequest.error.value ?? repositoryRequest.error.value)
const totalStars = computed(() => courseRepositories.value.reduce((total, repository) => total + (repository.stars ?? 0), 0))
const starSampleCount = computed(() => courseRepositories.value.filter((repository) => repository.stars !== null).length)
const activeRepositoryCount = computed(() => courseRepositories.value.filter((repository) => (repository.activeWeeks ?? 0) >= 9).length)
const createdYearRows = computed(() => {
  const counts = new Map<number, number>()
  for (const repository of courseRepositories.value) {
    const year = Number(repository.createdAt?.slice(0, 4))
    if (Number.isInteger(year) && year >= 2000 && year <= 2100) counts.set(year, (counts.get(year) ?? 0) + 1)
  }
  const years = [...counts.keys()].sort((left, right) => left - right)
  if (!years.length) return []
  const firstYear = years[0]
  const lastYear = years[years.length - 1]
  return Array.from({ length: lastYear - firstYear + 1 }, (_, index): [number, number] => {
    const year = firstYear + index
    return [year, counts.get(year) ?? 0]
  })
})
const starBuckets = computed(() => {
  const labels = ['< 1k', '1k–5k', '5k–10k', '10k–25k', '25k+']
  const counts = [0, 0, 0, 0, 0]
  for (const repository of courseRepositories.value) {
    if (repository.stars === null) continue
    const index = repository.stars < 1_000 ? 0 : repository.stars < 5_000 ? 1 : repository.stars < 10_000 ? 2 : repository.stars < 25_000 ? 3 : 4
    counts[index] += 1
  }
  return labels.map((label, index) => ({ label, count: counts[index] }))
})
const activeWeekBuckets = computed(() => Array.from({ length: 13 }, (_, week) => ({
  week,
  count: courseRepositories.value.filter((repository) => repository.activeWeeks === week).length,
})))
const axisColor = computed(() => ui.isDark ? '#a0a8b0' : '#6e7781')
const gridColor = computed(() => ui.isDark ? '#2b3238' : '#e8ebed')
const chartPalette = ['#68c63a', '#5d80de', '#eba33a', '#46b8a3', '#f0796b']
const axis = computed(() => ({ color: axisColor.value, fontSize: 9 }))
const splitLine = computed(() => ({ lineStyle: { color: gridColor.value, type: 'dashed' as const } }))

const languageOption = computed<EChartsOption>(() => ({
  color: chartPalette,
  tooltip: { trigger: 'item', formatter: (parameter: unknown) => {
    const item = parameter as { name?: string; value?: number }
    return `${item.name ?? '未知'}：${formatNumber(item.value)} 个仓库`
  } },
  series: [{
    type: 'treemap',
    roam: false,
    nodeClick: false,
    breadcrumb: { show: false },
    label: { show: true, formatter: '{b}\n{c} 个', color: '#17212b', fontSize: 10, lineHeight: 14, overflow: 'truncate' },
    itemStyle: { borderColor: ui.isDark ? '#151518' : '#ffffff', borderWidth: 2, gapWidth: 2 },
    data: topLanguages.value.map((group, index) => ({ name: group.language, value: group.repositoryCount, itemStyle: { color: chartPalette[index % chartPalette.length] } })),
  }],
}))

const starOption = computed<EChartsOption>(() => ({
  color: chartPalette,
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  grid: { top: 10, right: 22, bottom: 8, left: 58 },
  xAxis: { type: 'value', minInterval: 1, axisLabel: axis.value, axisLine: { show: false }, axisTick: { show: false }, splitLine: splitLine.value },
  yAxis: { type: 'category', inverse: true, data: starBuckets.value.map((bucket) => bucket.label), axisLabel: axis.value, axisLine: { show: false }, axisTick: { show: false } },
  series: [{ type: 'bar', data: starBuckets.value.map((bucket, index) => ({ value: bucket.count, itemStyle: { color: chartPalette[index % chartPalette.length] } })), barMaxWidth: 20, itemStyle: { borderRadius: [0, 4, 4, 0] }, label: { show: true, position: 'right', color: axisColor.value, fontSize: 8 } }],
}))

const scatterRepositories = computed(() => courseRepositories.value.filter((repository) => (repository.stars ?? 0) > 0 && (repository.forks ?? 0) > 0))
const scatterLanguageGroups = computed(() => {
  const knownLanguages = new Set(topLanguages.value.map((group) => group.language))
  const groups = new Map<string, typeof courseRepositories.value>()
  for (const repository of scatterRepositories.value) {
    const language = repository.language && knownLanguages.has(repository.language) ? repository.language : '其他'
    const items = groups.get(language) ?? []
    items.push(repository)
    groups.set(language, items)
  }
  return [...groups.entries()].map(([language, repositories]) => ({ language, repositories }))
})
const scatterOption = computed<EChartsOption>(() => ({
  color: chartPalette,
  tooltip: { trigger: 'item', formatter: (parameter: unknown) => {
    const item = parameter as { name?: string; seriesName?: string; value?: number[] }
    const point = item.value ?? []
    return `${item.name ?? '仓库'}<br/>主语言：${item.seriesName ?? '未知'}<br/>Stars：${formatNumber(point[0] ?? 0)}<br/>Forks：${formatNumber(point[1] ?? 0)}<br/>活跃周：${formatNumber(point[2] ?? 0)}`
  } },
  legend: { bottom: 0, left: 'center', itemWidth: 8, itemHeight: 8, textStyle: { color: axisColor.value, fontSize: 9 }, type: 'scroll' },
  grid: { top: 14, right: 18, bottom: 48, left: 43 },
  xAxis: { type: 'log', name: 'Stars', nameTextStyle: { color: axisColor.value, fontSize: 9 }, axisLabel: axis.value, axisLine: { lineStyle: { color: gridColor.value } }, splitLine: { show: false } },
  yAxis: { type: 'log', name: 'Forks', nameTextStyle: { color: axisColor.value, fontSize: 9 }, axisLabel: axis.value, axisLine: { show: false }, axisTick: { show: false }, splitLine: splitLine.value },
  series: scatterLanguageGroups.value.map(({ language, repositories }) => ({
    name: language,
    type: 'scatter' as const,
    symbolSize: (value: number[]) => 6 + Math.min(12, Math.max(0, value[2] ?? 0)) * .65,
    data: repositories.map((repository) => ({ name: repository.fullName, value: [repository.stars ?? 0, repository.forks ?? 0, repository.activeWeeks ?? 0] })),
    itemStyle: { opacity: .72 },
  })),
}))

const createdOption = computed<EChartsOption>(() => ({
  color: chartPalette,
  tooltip: { trigger: 'axis', valueFormatter: (value: unknown) => `${formatNumber(Number(value))} 个仓库` },
  grid: { top: 14, right: 12, bottom: 30, left: 32 },
  xAxis: { type: 'category', data: createdYearRows.value.map(([year]) => String(year)), axisLabel: { ...axis.value, interval: 'auto' }, axisLine: { lineStyle: { color: gridColor.value } }, axisTick: { show: false } },
  yAxis: { type: 'value', minInterval: 1, axisLabel: axis.value, axisLine: { show: false }, axisTick: { show: false }, splitLine: splitLine.value },
  series: [{ type: 'line', data: createdYearRows.value.map(([, count]) => count), smooth: false, symbol: 'circle', symbolSize: 5, lineStyle: { color: chartPalette[1], width: 2 }, itemStyle: { color: chartPalette[1] }, areaStyle: { color: chartPalette[1], opacity: .14 } }],
}))

const languageCommitOption = computed<EChartsOption>(() => {
  const groups = topLanguages.value.filter((group) => group.weeklyCommitMean !== null)
    .sort((left, right) => (right.weeklyCommitMean ?? 0) - (left.weeklyCommitMean ?? 0))
  return {
    color: chartPalette,
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { top: 8, right: 24, bottom: 10, left: 82, containLabel: false },
    xAxis: { type: 'value', axisLabel: axis.value, axisLine: { show: false }, axisTick: { show: false }, splitLine: splitLine.value },
    yAxis: { type: 'category', inverse: true, data: groups.map((group) => group.language), axisLabel: axis.value, axisLine: { show: false }, axisTick: { show: false } },
    series: [{ type: 'bar', data: groups.map((group, index) => ({ value: Number((group.weeklyCommitMean ?? 0).toFixed(1)), itemStyle: { color: chartPalette[index % chartPalette.length] } })), barMaxWidth: 16, itemStyle: { borderRadius: [0, 4, 4, 0] }, label: { show: true, position: 'right', color: axisColor.value, fontSize: 8, formatter: '{c}' } }],
  }
})

const activeWeekOption = computed<EChartsOption>(() => ({
  color: chartPalette,
  tooltip: { trigger: 'axis' },
  grid: { top: 14, right: 12, bottom: 28, left: 34 },
  xAxis: { type: 'category', data: activeWeekBuckets.value.map(({ week }) => String(week)), name: '活跃周', nameLocation: 'end', nameGap: 10, nameTextStyle: { color: axisColor.value, fontSize: 9 }, axisLabel: axis.value, axisLine: { lineStyle: { color: gridColor.value } }, axisTick: { show: false } },
  yAxis: { type: 'value', minInterval: 1, axisLabel: axis.value, axisLine: { show: false }, axisTick: { show: false }, splitLine: splitLine.value },
  series: [{ type: 'line', data: activeWeekBuckets.value.map(({ count }) => count), smooth: false, symbol: 'circle', symbolSize: 5, lineStyle: { color: chartPalette[0], width: 2 }, itemStyle: { color: chartPalette[0] }, areaStyle: { color: chartPalette[0], opacity: .14 } }],
}))

const title = computed(() => hasDashboardData.value ? '仓库总览' : repositories.value.length ? '仓库数据看板' : '从一个仓库开始')
const description = computed(() => hasDashboardData.value
  ? `查看 ${dashboard.value?.name ?? '仓库数据集'} 的技术栈、关注度与维护节奏。`
  : '添加仓库开始分析，或在仓库页查看现有分析库。')
const repositoryInput = ref('')
const addingRepository = ref(false)
const addError = ref('')

function formatNumber(value: number | null | undefined) {
  return value === null || value === undefined ? '—' : value.toLocaleString('zh-CN', { maximumFractionDigits: 1 })
}

async function refresh() {
  await Promise.all([dashboardRequest.reload(), repositoryRequest.reload()])
}

async function addRepository() {
  const input = repositoryInput.value.trim()
  if (!input || addingRepository.value) return
  addingRepository.value = true
  addError.value = ''
  try {
    const result = await source.addRepository(input)
    repositoryInput.value = ''
    ui.toast(result.taskId ? '已加入分析队列，可在任务页查看进度' : '仓库已在分析库中', result.taskId ? 'warning' : 'success')
    await repositoryRequest.reload()
    if (result.taskId) void router.push('/tasks')
  } catch (error) {
    addError.value = error instanceof Error ? error.message : '添加仓库失败'
  } finally {
    addingRepository.value = false
  }
}

</script>

<template>
  <div class="stack optimized-page">
    <UiPageHeader :title="title" :description="description">
      <template #actions>
        <UiButton variant="quiet" :disabled="loading" aria-label="刷新总览数据" @click="refresh"><RefreshCw :size="13" />刷新</UiButton>
        <UiButton variant="outline" @click="router.push('/repositories')">管理仓库 <ArrowRight :size="12" /></UiButton>
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

    <div v-if="dashboardError" class="notice" role="alert">数据加载失败：{{ dashboardError }}</div>
    <div v-else-if="loading && !dashboard" class="kpi-grid" aria-label="正在加载总览">
      <div v-for="item in 4" :key="item" class="kpi"><span class="gd-skeleton-shimmer block h-3 w-20 rounded" /><span class="gd-skeleton-shimmer mt-3 block h-6 w-24 rounded" /></div>
    </div>

    <section v-else class="kpi-grid" aria-label="仓库总览">
      <UiMetricCard label="标准样本仓库" :value="formatNumber(dashboard?.repositoryCount)" note="当前数据集中的仓库数" />
      <UiMetricCard label="累计 Stars" :value="starSampleCount ? formatNumber(totalStars) : '—'" :note="starSampleCount ? `${formatNumber(starSampleCount)} 个仓库有 Stars 数据` : '暂无 Stars 快照'" />
      <UiMetricCard label="主要语言" :value="formatNumber(languageGroups.length)" note="按仓库主语言分组" />
      <UiMetricCard label="近 12 周持续活跃" :value="hasDashboardData ? formatNumber(activeRepositoryCount) : '—'" note="至少 9 个活跃周" />
    </section>

    <section class="chart-grid" aria-label="仓库数据分布图表">
      <UiPanel as="article" class="chart-panel"><div class="panel-heading"><div><h2 class="panel-title">编程语言构成</h2><p class="panel-description">按主语言展示仓库数量占比</p></div></div><ChartPanel v-if="hasDashboardData" :option="languageOption" label="仓库主语言矩形树图" :height="226" /><div v-else class="empty-state small">暂无研究数据集</div></UiPanel>
      <UiPanel as="article" class="chart-panel"><div class="panel-heading"><div><h2 class="panel-title">Stars 关注度分布</h2><p class="panel-description">按仓库 Stars 区间比较数量</p></div><Star :size="15" class="muted" /></div><ChartPanel v-if="starSampleCount" :option="starOption" label="Stars 区间横向条形图" :height="226" /><div v-else class="empty-state small">暂无 Stars 快照</div></UiPanel>
      <UiPanel as="article" class="chart-panel"><div class="panel-heading"><div><h2 class="panel-title">Stars 与 Forks</h2><p class="panel-description">气泡大小表示近 12 周活跃周</p></div><GitFork :size="15" class="muted" /></div><ChartPanel v-if="scatterRepositories.length" :option="scatterOption" label="Stars 与 Forks 活跃度气泡散点图" :height="226" /><div v-else class="empty-state small">暂无完整的 Stars 与 Forks 记录</div></UiPanel>
      <UiPanel as="article" class="chart-panel"><div class="panel-heading"><div><h2 class="panel-title">仓库创建年份</h2><p class="panel-description">按 GitHub 创建年份展示数量趋势</p></div><UiBadge>{{ createdYearRows.length ? `${createdYearRows[0][0]}–${createdYearRows.at(-1)?.[0]}` : '暂无数据' }}</UiBadge></div><ChartPanel v-if="createdYearRows.length" :option="createdOption" label="仓库创建年份趋势面积折线图" :height="226" /><div v-else class="empty-state small">暂无创建日期快照</div></UiPanel>
      <UiPanel as="article" class="chart-panel"><div class="panel-heading"><div><h2 class="panel-title">各语言周均 Commit</h2><p class="panel-description">按完整周均值从高到低排列</p></div><GitCommitHorizontal :size="15" class="muted" /></div><ChartPanel v-if="topLanguages.some((group) => group.weeklyCommitMean !== null)" :option="languageCommitOption" label="各语言周均 Commit 横向排名图" :height="226" /><div v-else class="empty-state small">暂无完整周 Commit 汇总</div></UiPanel>
      <UiPanel as="article" class="chart-panel"><div class="panel-heading"><div><h2 class="panel-title">12 周活动连续性</h2><p class="panel-description">按活跃周数展示仓库分布</p></div><Activity :size="15" class="muted" /></div><ChartPanel v-if="courseRepositories.some((repository) => repository.activeWeeks !== null)" :option="activeWeekOption" label="近 12 周活跃周数分布折线图" :height="226" /><div v-else class="empty-state small">暂无活跃周统计</div></UiPanel>
    </section>
    <p class="helper-note"><Database :size="12" style="vertical-align:-2px" /> 图表只使用接口返回的仓库快照和已归档的周级数据；缺失项显示为空，不用样例值补齐。</p>
  </div>
</template>
