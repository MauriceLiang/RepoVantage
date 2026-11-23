<script setup lang="ts">
import { ArrowRight, Database, RefreshCw } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAsyncData } from '@/composables/useAsyncData'
import { useDataSource } from '@/composables/useDataSource'
import { useOverviewChartFilters } from '@/composables/useOverviewChartFilters'
import { buildOverviewChartData } from '@/lib/overviewChartData'
import type { RepositorySummary } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import OverviewCharts from './OverviewCharts.vue'

const source = useDataSource()
const router = useRouter()
const ui = useUiStore()
const repositoryRequest = useAsyncData(() => source.listRepositories())
const repositories = computed(() => repositoryRequest.data.value ?? [])
const hasRepositoryData = computed(() => repositories.value.length > 0)
const loading = computed(() => repositoryRequest.loading.value)
const repositoryError = computed(() => repositoryRequest.error.value)
const dataCoverageCount = computed(() => repositories.value.filter((repository) => repository.status === 'ready' || repository.status === 'partial').length)
const asOfMs = ref(Date.now())
watch(repositories, () => { asOfMs.value = Date.now() })
const chartData = computed(() => buildOverviewChartData({ repositories: repositories.value, asOfMs: asOfMs.value }))
const chartFilters = useOverviewChartFilters(repositories)
const chartFilterState = chartFilters.filterState
const chartFilteredRepositories = chartFilters.filteredRepositories
const chartFilteredIds = computed(() => chartFilteredRepositories.value.map((repository) => repository.id))
const recentActivityCount = computed(() => chartData.value.active30Count)

function needsAttention(repository: RepositorySummary) {
  return repository.status === 'failed'
    || repository.status === 'idle'
    || repository.status === 'partial'
    || repository.dataStatus === 'stale'
    || repository.dataStatus === 'missing'
}

const attentionCount = computed(() => repositories.value.filter(needsAttention).length)

function selectChartRepository(id: string) {
  chartFilters.selectedRepositoryId.value = chartFilters.selectedRepositoryId.value === id ? null : id
}

function clearSelectedRepository() {
  chartFilters.selectedRepositoryId.value = null
}

function clearChartFilters() {
  chartFilters.clearFilters()
}

const repositoryInput = ref('')
const addingRepository = ref(false)
const addError = ref('')

function formatNumber(value: number | null | undefined) {
  return value === null || value === undefined ? '—' : value.toLocaleString('zh-CN', { maximumFractionDigits: 1 })
}

async function refresh() {
  await repositoryRequest.reload()
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
        <li><span>03</span><div><strong>比较项目</strong><p>前往「仓库」页面选择项目进行分析或比较。</p></div></li>
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
        @select-repository="selectChartRepository"
        @clear-selected-repository="clearSelectedRepository"
        @clear-filters="clearChartFilters"
      />

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
@media (max-width: 860px) {
  .onboarding-heading { flex-direction: column; }
  .onboarding-steps { grid-template-columns: 1fr; gap: 10px; }
}
</style>
