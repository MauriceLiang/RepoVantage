<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ModuleTabs from '@/components/layout/ModuleTabs.vue'
import RepoHeader from '@/components/layout/RepoHeader.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import GdEmptyState from '@/components/ui/GdEmptyState.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useDataSource } from '@/composables/useDataSource'
import type { RepositoryAnalysis } from '@/services/types'
import { useAnalysisStore } from '@/stores/analysis'
import { useUiStore } from '@/stores/ui'
import OverviewTab from './tabs/OverviewTab.vue'
import MaintenanceInsights from './tabs/MaintenanceInsights.vue'
import ActivityTab from './tabs/ActivityTab.vue'
import IssuesTab from './tabs/IssuesTab.vue'
import PrsTab from './tabs/PrsTab.vue'
import ReleasesTab from './tabs/ReleasesTab.vue'

const route = useRoute()
const router = useRouter()
const ui = useUiStore()
const analysisStore = useAnalysisStore()
const source = useDataSource()
const refreshing = ref(false)
const clearing = ref(false)
const repoId = computed(() => String(route.params.id ?? ''))
const tab = computed(() => String(route.params.tab || 'overview'))
const isCourseTestRepository = computed(() => data.value?.repository.datasetIds?.includes('course-research-300-v1') === true)
const showingHistoricalCourseOverview = computed(() => tab.value === 'overview'
  && isCourseTestRepository.value
  && data.value?.repository.hasHistoricalData === true
  && data.value?.windowAvailability.available === false)
const showingCourseMaintenance = computed(() => isCourseTestRepository.value
  && showingHistoricalCourseOverview.value)
const tabComponent = computed(() => ({ overview: OverviewTab, activity: ActivityTab, issues: IssuesTab, prs: PrsTab, releases: ReleasesTab }[tab.value] ?? OverviewTab))
const { data, loading, error, reload } = useAsyncData<RepositoryAnalysis>(
  () => source.getAnalysis(repoId.value, analysisStore.timeWindow),
  () => [repoId.value, analysisStore.timeWindow],
)
const notAnalyzed = computed(() => data.value?.repository.status === 'idle' && data.value?.windowAvailability.available !== true)
const failed = computed(() => Boolean(error.value) || (data.value?.repository.status === 'failed' && data.value?.windowAvailability.available !== true))

async function refresh() {
  refreshing.value = true
  try {
    await source.refreshRepository(repoId.value, { scopeKind: 'window', windowDays: 180 })
    ui.toast('已排队：最近 180 天完整数据更新，可在任务页查看进度', 'warning')
    void router.push('/tasks')
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '启动采集失败', 'error')
  } finally { refreshing.value = false }
}

async function clearCurrentRepositoryData() {
  const fullName = data.value?.repository.fullName ?? `仓库 #${repoId.value}`
  if (!window.confirm(`清除 ${fullName} 在本机保存的采集与分析记录，包括快照、活动记录、分析结果和单仓归档？仓库资料、预装原始数据包、我的仓库归属、其他数据集关系与任务历史会保留。此操作不可撤销。`)) return
  clearing.value = true
  try {
    await source.clearRepositoryData([repoId.value])
    analysisStore.setCompare(analysisStore.compareIds.filter((id) => id !== repoId.value))
    await reload()
    ui.toast('已清除该仓库的本地采集与分析数据')
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '清除仓库数据失败', 'error')
  } finally { clearing.value = false }
}

function openWeek(payload: { date: string; count: number }) {
  ui.openDrawer('commits', {
    repoId: repoId.value,
    weekLabel: payload.date,
    count: String(payload.count),
    windowDays: String(analysisStore.timeWindow),
  })
}
</script>

<template>
  <div class="app-page" data-testid="repository-analysis" :data-window-days="data?.windowAvailability.requestedDays" :data-window-available="data?.windowAvailability.available">
    <div v-if="data && !showingCourseMaintenance" class="panel repository-page-summary">
      <RepoHeader
        :repository="data.repository"
        :coverage="data.coverage"
        :collected-at="data.collectedAt"
        :window-start="data.metrics.window.start"
        :window-end="data.metrics.window.end"
        :refreshing="refreshing"
        :clearing="clearing"
        @refresh="refresh"
        @clear="clearCurrentRepositoryData"
      />
    </div>
    <div v-else-if="showingCourseMaintenance && data" class="repository-page-summary panel">
      <div><h1 class="page-title">{{ data.repository.fullName }}</h1><p class="page-description">300 仓库研究样本的历史维护证据与模型结果。</p></div>
    </div>

    <ModuleTabs v-if="repoId" :repo-id="repoId" :active="tab" />

    <p v-if="data?.provenance?.origin === 'course-test-events-v1'" class="panel history-note" data-testid="course-history-events">
      当前展示 300 仓库数据集的本地历史快照，观察窗口截至 {{ data.metrics.window.end ?? '—' }}；Issue 仅包含采集范围内创建的记录，提交说明和 Issue / PR 标题、正文未保存在快照中。
    </p>

    <div v-if="loading" class="stack" aria-label="正在加载仓库分析" aria-busy="true">
      <div class="gd-skeleton-shimmer h-24 rounded-xl" /><div class="gd-skeleton-shimmer h-80 rounded-xl" /><div class="detail-grid"><div v-for="i in 3" :key="i" class="gd-skeleton-shimmer h-52 rounded-xl" /></div>
    </div>

    <div v-else-if="showingHistoricalCourseOverview" class="analysis-tab-stage" data-testid="repository-ml-analysis">
      <p v-if="showingHistoricalCourseOverview" class="panel history-note" data-testid="course-history-overview">300 仓库的历史维护数据已在本地，下面直接展示已有事实与分析，不会为此重新抓取。</p>
      <MaintenanceInsights :repository-id="repoId" :repository="data?.repository ?? null" />
    </div>

    <GdCard v-else-if="failed">
      <GdEmptyState title="采集失败，暂时没有可展示的分析结果" :description="error ?? data?.coverage.detail ?? '请检查任务状态后重试。'">
        <template #action><GdButton data-testid="retry-collection" size="sm" class="mt-1" @click="refresh()">重试采集</GdButton></template>
      </GdEmptyState>
    </GdCard>

    <GdCard v-else-if="notAnalyzed">
      <GdEmptyState title="尚未分析这个仓库" description="还没有采集任何模块。开始分析后，这里会出现开发活动、Issue / PR 与发布节奏。">
        <template #action><GdButton data-testid="start-analysis" size="sm" class="mt-1" @click="refresh()">开始分析</GdButton></template>
      </GdEmptyState>
    </GdCard>

    <GdCard v-else-if="data && !data.windowAvailability.available" padding="sm" :gap="false" data-testid="analysis-window-unavailable">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div><h2 class="m-0 text-[15px] font-semibold">尚未采集所选的 {{ data.windowAvailability.requestedDays }} 天范围</h2><p class="mb-0 mt-1 text-[12px] text-muted">{{ data.windowAvailability.reason ?? '当前没有覆盖该范围的分析运行。采集完成后会按所选日期重新计算指标。' }}</p></div>
        <GdButton :disabled="refreshing || clearing" @click="refresh()">按所选时长采集</GdButton>
      </div>
    </GdCard>

    <div v-else-if="data && data.windowAvailability.available" data-testid="analysis-content" class="analysis-tab-stage">
      <Transition name="analysis-tab">
        <div :key="`${repoId}:${tab}`" class="analysis-tab-page min-w-0 flex flex-col gap-[18px]">
          <component :is="tabComponent" :analysis="data" @select-week="openWeek" />
        </div>
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.app-page { display:grid; gap:14px; }
.repository-page-summary { padding:18px; }
.history-note { margin:0; padding:10px 12px; color:var(--muted); font-size:12px; line-height:1.6; }
</style>
