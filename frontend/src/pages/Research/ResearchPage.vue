<script setup lang="ts">
import { BookOpen, Download, LoaderCircle } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import ResearchGroupComboChart from '@/components/charts/ResearchGroupComboChart.vue'
import ResearchQualityChart from '@/components/charts/ResearchQualityChart.vue'
import ScatterChart from '@/components/charts/ScatterChart.vue'
import GdBadge from '@/components/ui/GdBadge.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import GdSegmented from '@/components/ui/GdSegmented.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useDataSource } from '@/composables/useDataSource'
import { downloadBlob } from '@/lib/download'
import { useAnalysisStore } from '@/stores/analysis'
import { useUiStore } from '@/stores/ui'
import type { ResearchAnalysisMode } from '@/services/types'

const ui = useUiStore()
const analysisStore = useAnalysisStore()
const source = useDataSource()
const exporting = ref(false)
const importing = ref(false)
const requestedMode = ref<ResearchAnalysisMode | 'auto'>('auto')
const repositorySearch = ref('')
const roleFilter = ref<'all' | 'train' | 'test'>('all')
const { data, loading, error, reload } = useAsyncData(() => source.getResearchDataset(undefined, requestedMode.value), () => requestedMode.value)
const { data: featuredStatus, error: featuredStatusError, reload: reloadFeaturedStatus } = useAsyncData(() => source.getFeaturedDatasetStatus())
const modeOptions = [
  { value: 'course', label: '课程研究', hint: '默认使用 300 仓库历史快照，显示固定 150/150 实验角色与覆盖范围。' },
  { value: 'exploratory', label: '精选探索', hint: '基于当前本地已采集的精选仓库数据，不代表 GitHub 总体。' },
  { value: 'formal', label: '正式研究', hint: '只读取已确认并导入的研究样本；不会替用户冻结样本清单。' },
]
const selectedMode = computed(() => requestedMode.value === 'auto' ? data.value?.analysisMode ?? 'course' : requestedMode.value)
const activeFeaturedImport = computed(() => ['queued', 'running'].includes(featuredStatus.value?.activeTask?.status ?? ''))
const featuredImportUnavailable = computed(() => !featuredStatus.value?.available)

const groupChartItems = computed(() => data.value?.groups.map((group) => ({
  label: group.label,
  repositoryCount: group.count,
  issueSampleSize: group.issueSampleSize,
  medianCloseDays: group.medianCloseDays,
})) ?? [])
const groupChartHeight = computed(() => Math.max(190, groupChartItems.value.length * 32))
const groupsWithoutIssueSamples = computed(() => groupChartItems.value.filter((group) => group.issueSampleSize === 0).length)
const qualityItems = computed(() => (data.value?.quality ?? []).flatMap((quality) =>
  quality.missingCount === null || quality.totalRecords === null
    ? []
    : [{ field: quality.field, missingCount: quality.missingCount, totalRecords: quality.totalRecords }],
))
const groups = computed(() => (data.value?.groups ?? []).map((group) => group.label))
const courseRepositories = computed(() => data.value?.courseRepositories ?? [])
const filteredCourseRepositories = computed(() => {
  const query = repositorySearch.value.trim().toLocaleLowerCase()
  return courseRepositories.value.filter((repository) => {
    const matchesRole = roleFilter.value === 'all' || repository.sampleRole === roleFilter.value
    const matchesQuery = !query || `${repository.fullName} ${repository.language}`.toLocaleLowerCase().includes(query)
    return matchesRole && matchesQuery
  })
})

function setMode(value: string | number) {
  if (value === 'formal' || value === 'exploratory' || value === 'course') requestedMode.value = value
}

function addToComparison(repositoryId: string) {
  if (analysisStore.compareIds.includes(repositoryId)) return
  if (analysisStore.compareIds.length >= 5) {
    ui.toast('最多可同时比较 5 个仓库，请先移除一个候选。', 'warning')
    return
  }
  analysisStore.toggleCompare(repositoryId)
  ui.toast('已加入仓库比较候选')
}

async function exportResearchMembers() {
  if (!data.value) return
  exporting.value = true
  try {
    downloadBlob(await source.exportRepositories('research', data.value.id, data.value.analysisMode), `${data.value.id}-members.csv`)
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '导出样本成员失败', 'error')
  } finally {
    exporting.value = false
  }
}

async function exportResearchStatistics() {
  if (!data.value) return
  exporting.value = true
  try {
    downloadBlob(await source.exportResearchStatistics(data.value.id, data.value.analysisMode), `${data.value.id}-statistics.csv`)
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '导出统计结果失败', 'error')
  } finally {
    exporting.value = false
  }
}

async function importFeatured() {
  if (importing.value || !featuredStatus.value?.available || activeFeaturedImport.value) return
  importing.value = true
  try {
    const result = await source.importFeaturedDataset()
    requestedMode.value = 'exploratory'
    await reloadFeaturedStatus()
    if (result.alreadyCurrent) {
      await reload()
      ui.toast('精选数据已是当前版本', 'warning')
    } else {
      ui.toast('精选数据导入任务已排队，可在任务中心查看进度', 'warning')
    }
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '导入精选数据失败', 'error')
  } finally {
    importing.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-[18px] px-4 pb-8 pt-5 sm:px-7 sm:pt-[22px]">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="m-0 text-[24px] font-semibold">研究分析</h1>
        <p class="mt-1.5 text-muted">选择精选探索或正式研究；样本范围、覆盖质量与分析限制会随结果展示。</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <GdSegmented :model-value="selectedMode" :options="modeOptions" aria-label="研究分析模式" data-testid="research-mode" @update:model-value="setMode" />
        <template v-if="data && data.repositoryCount > 0">
          <GdButton variant="outline" :disabled="exporting" data-testid="export-research-members" @click="exportResearchMembers"><Download :size="14" /> 导出样本成员</GdButton>
          <GdButton variant="outline" :disabled="exporting" data-testid="export-research-statistics" @click="exportResearchStatistics"><Download :size="14" /> 导出统计结果</GdButton>
        </template>
      </div>
    </div>

    <p v-if="error" class="rounded-md bg-warnbg px-3 py-2.5 text-[12px] text-warnfg">研究数据集加载失败：{{ error }}</p>
    <div v-else-if="loading" class="flex flex-col gap-4">
      <div class="h-[120px] animate-pulse rounded bg-track/60" />
      <div class="h-[260px] animate-pulse rounded bg-track/60" />
    </div>

    <template v-else-if="data">
      <GdCard v-if="data.repositoryCount === 0" class="gap-3" data-testid="research-empty-state">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 v-if="data.analysisMode === 'exploratory'" class="m-0 text-[16px] font-semibold">精选数据尚未导入</h2>
            <h2 v-else class="m-0 text-[16px] font-semibold">正式研究样本尚不可分析</h2>
            <p v-if="data.analysisMode === 'exploratory'" class="mt-1 text-[12px] leading-relaxed text-muted">
              {{ featuredStatus?.totalRepositories ? `可导入 ${featuredStatus.totalRepositories} 个精选仓库。` : '当前本机没有可用的精选数据包。' }} 导入只读取随应用提供的数据包，不会请求 GitHub。
            </p>
            <p v-else class="mt-1 text-[12px] leading-relaxed text-muted">
              {{ data.studyStatus === 'pending_confirmation' ? '研究样本清单仍待负责人确认；当前未生成正式结果。' : data.studyStatus === 'approved_not_imported' ? '样本已确认，但成员清单尚未导入。' : '成员清单已导入，尚无可分析的本地采集结果。' }}
            </p>
          </div>
          <GdBadge variant="warn">{{ data.analysisMode === 'exploratory' ? '未导入' : data.studyStatus === 'pending_confirmation' ? '待确认' : data.studyStatus === 'approved_not_imported' ? '待导入' : '等待采集' }}</GdBadge>
        </div>
        <p v-if="featuredStatusError && data.analysisMode === 'exploratory'" class="m-0 text-[11px] text-danger">精选数据包状态读取失败：{{ featuredStatusError }}</p>
        <div v-if="data.analysisMode === 'exploratory'" class="flex flex-wrap items-center gap-2">
          <GdButton :disabled="importing || featuredImportUnavailable || activeFeaturedImport" data-testid="import-featured" @click="importFeatured">
            <LoaderCircle v-if="importing || activeFeaturedImport" :size="14" class="animate-spin" />
            {{ importing ? '正在提交…' : activeFeaturedImport ? '精选数据导入中' : featuredImportUnavailable ? '精选数据包不可用' : '导入精选' }}
          </GdButton>
          <RouterLink to="/tasks" class="gd-link text-[12px]">前往任务中心查看进度</RouterLink>
        </div>
      </GdCard>

      <template v-else>
      <p v-if="(requestedMode === 'course' || requestedMode === 'auto') && data.analysisMode !== 'course'" class="m-0 rounded-md bg-warnbg px-3 py-2.5 text-[12px] text-warnfg" data-testid="course-dataset-fallback">
        300 仓库课程研究数据不可用，当前显示 {{ data.analysisMode === 'exploratory' ? '15 仓库精选数据' : '正式研究数据' }}回退结果。
      </p>
      <GdCard>
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="flex items-center gap-2">
            <span class="font-mono text-[13px] font-semibold">{{ data.name }}</span>
            <GdBadge variant="plain">{{ data.analysisMode === 'course' ? '课程研究 · 历史快照' : data.analysisMode === 'exploratory' ? '精选探索' : '正式研究' }}</GdBadge>
          </div>
          <button class="gd-link text-[11.5px]" @click="ui.openDrawer('definitions', { metric: 'M14', sample: `${data.repositoryCount} 个仓库 · ${data.scatter.sampleSize} 个有效配对` })">
            <BookOpen :size="13" /> 查看采样说明与局限
          </button>
        </div>
        <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <div class="text-[11px] text-muted">采样来源</div>
            <div class="mt-1 text-[12.5px] font-medium">{{ data.samplingSource }}</div>
          </div>
          <div class="border-line sm:border-l sm:pl-4">
            <div class="text-[11px] text-muted">采样规则</div>
            <div class="mt-1 text-[12.5px] font-medium">{{ data.samplingRule }}</div>
          </div>
          <div class="border-line lg:border-l lg:pl-4">
            <div class="text-[11px] text-muted">{{ data.analysisMode === 'course' ? '版本 / 资料快照截点' : data.analysisMode === 'exploratory' ? '精选版本 / 快照' : '冻结日期' }}</div>
            <div class="mt-1 text-[12.5px] font-medium">{{ data.analysisMode === 'course' ? `${data.datasetVersion ?? '—'} · ${data.courseSummary?.dataAsOf ?? '—'}` : data.analysisMode === 'exploratory' ? data.datasetVersion ?? '后端未记录' : data.frozenAt ?? '后端未记录' }}</div>
            <div class="mt-0.5 text-[11px] text-muted">观察窗口 {{ data.analysisMode === 'course' ? data.courseSummary?.observationWindow.start ?? '—' : data.eventWindow.start ?? '—' }} — {{ data.analysisMode === 'course' ? data.courseSummary?.observationWindow.endExclusive ?? '—' : data.eventWindow.end ?? '—' }}</div>
          </div>
          <div class="border-line lg:border-l lg:pl-4">
            <div class="text-[11px] text-muted">样本与总体范围</div>
            <div class="mt-1 text-[12.5px] font-medium">{{ data.repositoryCount }} 个仓库{{ data.analysisMode === 'course' ? ` · ${data.courseSummary?.weeklyRecords ?? 0} 条仓库周记录` : ` · ${data.scatter.sampleSize} 个有效配对` }}</div>
            <div class="mt-0.5 text-[11px] text-muted">{{ data.isProbabilitySample ? '概率样本' : '非概率样本' }} · {{ data.populationScope }}</div>
            <div class="mt-0.5 text-[11px] text-muted">{{ data.analysisMode === 'course' ? `Commit 12 周完整覆盖 ${data.courseSummary?.completeCommitRepositories ?? 0} / ${data.repositoryCount}` : `Issue 指标缺失率 ${data.missingRate === null ? '—' : `${data.missingRate}%`}` }}</div>
          </div>
        </div>
      </GdCard>

      <GdCard v-if="data.analysisMode === 'course'" data-testid="course-research-summary">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 class="m-0 text-[15.5px] font-semibold">课程样本与覆盖</h3>
            <p class="mt-1 text-[12px] text-muted">固定历史快照；训练/测试角色只解释实验分组，不表示全新外部样本。</p>
          </div>
          <GdBadge variant="plain">截至 {{ data.courseSummary?.dataAsOf ?? '未知' }}</GdBadge>
        </div>
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
          <div class="rounded-md bg-soft/50 p-3"><div class="text-[11px] text-muted">训练仓库</div><div class="mt-1 text-[22px] font-semibold">{{ data.courseSummary?.splitCounts.train ?? 0 }}</div></div>
          <div class="rounded-md bg-soft/50 p-3"><div class="text-[11px] text-muted">测试仓库</div><div class="mt-1 text-[22px] font-semibold">{{ data.courseSummary?.splitCounts.test ?? 0 }}</div></div>
          <div class="rounded-md bg-soft/50 p-3"><div class="text-[11px] text-muted">12 周完整 Commit 仓库</div><div class="mt-1 text-[22px] font-semibold">{{ data.courseSummary?.completeCommitRepositories ?? 0 }} / 300</div><div class="mt-1 text-[10px] text-muted">{{ data.courseSummary?.coverage.commit_week_complete_or_true_zero ?? 0 }} / {{ data.courseSummary?.weeklyRecords ?? 0 }} 个周记录完整或真实为零</div></div>
          <div class="rounded-md bg-soft/50 p-3"><div class="text-[11px] text-muted">PR 创建周覆盖</div><div class="mt-1 text-[22px] font-semibold">{{ data.courseSummary?.coverage.pr_opened_week_complete_or_true_zero ?? 0 }} / {{ data.courseSummary?.weeklyRecords ?? 0 }}</div><div class="mt-1 text-[10px] text-muted">周级创建数量</div></div>
          <div class="rounded-md bg-soft/50 p-3"><div class="text-[11px] text-muted">PR 合并周覆盖</div><div class="mt-1 text-[22px] font-semibold">{{ data.courseSummary?.coverage.pr_merged_week_complete_or_true_zero ?? 0 }} / {{ data.courseSummary?.weeklyRecords ?? 0 }}</div><div class="mt-1 text-[10px] text-muted">{{ data.courseSummary?.coverage.pr_merged_week_partial_concurrent_change ?? 0 }} 周部分覆盖</div></div>
          <div class="rounded-md bg-soft/50 p-3"><div class="text-[11px] text-muted">观察窗口</div><div class="mt-1 text-[12px] font-medium">{{ data.courseSummary?.observationWindow.start ?? '—' }} 至 {{ data.courseSummary?.observationWindow.endExclusive ?? '—' }}</div><div class="mt-1 text-[11px] text-muted">12 个完整 UTC 周 · {{ data.courseSummary?.weeklyRecords ?? 0 }} 条仓库周记录</div></div>
        </div>
        <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]">
          <div>
            <h4 class="mb-2 mt-0 text-[12px] font-semibold">语言分布与周均 Commit</h4>
            <div class="max-h-[320px] overflow-auto rounded-md border border-line">
              <table class="w-full text-left text-[11px]"><thead class="sticky top-0 bg-soft text-muted"><tr><th class="px-2 py-2">语言</th><th class="px-2 py-2">仓库</th><th class="px-2 py-2">有效 Commit</th><th class="px-2 py-2">周均</th></tr></thead><tbody><tr v-for="group in data.courseLanguageGroups ?? []" :key="group.language" class="border-t border-line"><td class="px-2 py-2">{{ group.language }}</td><td class="px-2 py-2">{{ group.repositoryCount }}</td><td class="px-2 py-2">{{ group.commitSampleCount }}</td><td class="px-2 py-2">{{ group.weeklyCommitMean?.toFixed(2) ?? '—' }}</td></tr></tbody></table>
            </div>
          </div>
          <div>
            <div class="flex flex-wrap items-center justify-between gap-2">
              <h4 class="m-0 text-[12px] font-semibold">研究仓库列表 · {{ filteredCourseRepositories.length }} / {{ courseRepositories.length }}</h4>
              <div class="flex flex-wrap gap-2">
                <input v-model="repositorySearch" aria-label="搜索课程仓库" placeholder="搜索名称或语言" class="h-8 rounded-md border border-line bg-panel px-2 text-[11px]" />
                <select v-model="roleFilter" aria-label="按训练或测试角色筛选" class="h-8 rounded-md border border-line bg-panel px-2 text-[11px]"><option value="all">全部角色</option><option value="train">训练组</option><option value="test">测试组</option></select>
              </div>
            </div>
            <div class="mt-2 max-h-[320px] overflow-auto rounded-md border border-line">
              <table class="w-full text-left text-[11px]"><thead class="sticky top-0 bg-soft text-muted"><tr><th class="px-2 py-2">仓库</th><th class="px-2 py-2">语言</th><th class="px-2 py-2">角色</th><th class="px-2 py-2">周均 Commit</th><th class="px-2 py-2">操作</th></tr></thead><tbody><tr v-for="repository in filteredCourseRepositories" :key="repository.repositoryId" class="border-t border-line"><td class="px-2 py-2 font-mono">{{ repository.fullName }}</td><td class="px-2 py-2">{{ repository.language }}</td><td class="px-2 py-2">{{ repository.sampleRole === 'train' ? '训练' : '测试' }}</td><td class="px-2 py-2">{{ repository.weeklyCommitMean?.toFixed(2) ?? '—' }}</td><td class="whitespace-nowrap px-2 py-2"><RouterLink :to="`/repositories/${repository.repositoryId}/analysis`" class="gd-link">分析</RouterLink><button class="ml-2 gd-link" @click="addToComparison(repository.repositoryId)">{{ analysisStore.compareIds.includes(repository.repositoryId) ? '已加入' : '加入对比' }}</button></td></tr><tr v-if="!filteredCourseRepositories.length"><td colspan="5" class="px-2 py-6 text-center text-muted">没有匹配的课程研究仓库。</td></tr></tbody></table>
            </div>
          </div>
        </div>
        <p class="m-0 text-[11px] leading-relaxed text-muted">当前包包含 PR 创建/合并周级数量及覆盖标识，但不含 Issue 事件、PR 合并耗时或 Release 事件；缺失字段不补零。可选仓库可以进入单仓分析、最多 5 个仓库的比较和规则型选型报告。</p>
      </GdCard>

      <section v-if="data.analysisMode !== 'course'" data-testid="research-kpis" class="grid grid-cols-2 divide-line rounded-[10px] border border-line bg-panel px-5 py-3.5 sm:grid-cols-4 sm:divide-x">
        <div class="px-0 py-2 sm:px-5 sm:py-0 sm:first:pl-0">
          <div class="text-[12.5px] text-muted">样本仓库</div>
          <div data-testid="research-sample-count" class="mt-1 text-[29px] font-semibold leading-tight">{{ data.repositoryCount }}</div>
        </div>
        <div class="px-0 py-2 sm:px-5 sm:py-0">
          <div class="text-[12.5px] text-muted">有效配对样本</div>
          <div class="mt-1 text-[29px] font-semibold leading-tight">{{ data.scatter.sampleSize }}</div>
          <div class="text-[11px] text-muted">同时具备 Issue 与 PR 指标</div>
        </div>
        <div class="px-0 py-2 sm:px-5 sm:py-0">
          <div class="text-[12.5px] text-muted">Issue 关闭耗时 P50</div>
          <div class="mt-1 text-[29px] font-semibold leading-tight">{{ data.issueMedianDays ?? '—' }}<span v-if="data.issueMedianDays !== null" class="ml-1 text-[13px] font-normal text-muted">天</span></div>
          <div class="text-[11px] text-muted">n={{ data.issueSample }}</div>
        </div>
        <div class="px-0 py-2 sm:px-5 sm:py-0">
          <div class="text-[12.5px] text-muted">PR 合并耗时 P50</div>
          <div class="mt-1 text-[29px] font-semibold leading-tight">{{ data.prMedianDays ?? '—' }}<span v-if="data.prMedianDays !== null" class="ml-1 text-[13px] font-normal text-muted">天</span></div>
          <div class="text-[11px] text-muted">n={{ data.prSample }}</div>
        </div>
      </section>

      <GdCard v-if="data.analysisMode !== 'course'" class="h-[360px] overflow-hidden">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 class="m-0 text-[15.5px] font-semibold">语言分组：样本规模与 Issue 耗时</h3>
            <p class="mt-0.5 text-[12px] text-muted">柱：有有效 Issue 耗时的仓库数 · 点：组内 Issue P50（天）</p>
          </div>
          <span class="font-mono text-[11.5px] text-muted">数据集 {{ data.repositoryCount }} 个仓库</span>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
          <ResearchGroupComboChart v-if="groupChartItems.length" :groups="groupChartItems" :height="groupChartHeight" />
          <p v-else class="py-12 text-center text-[12px] text-muted">当前数据集没有可展示的分组。</p>
        </div>
        <p v-if="groupsWithoutIssueSamples" class="m-0 text-[10.5px] text-muted">{{ groupsWithoutIssueSamples }} 个语言组没有有效 Issue 耗时样本。组内仓库数不等于该指标的有效样本数。</p>
      </GdCard>

      <GdCard v-if="data.analysisMode !== 'course'">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 class="m-0 text-[15.5px] font-semibold">Issue 与 PR 协作耗时</h3>
            <p class="mt-0.5 text-[12px] text-muted">每个点是一个仓库；气泡越大表示两项指标中较小的有效样本数越多，虚线为样本中位数分界</p>
          </div>
          <div class="flex flex-wrap items-center gap-2 text-[11.5px]">
            <span class="font-mono">Spearman ρ = {{ data.scatter.spearman ?? '—' }}</span>
            <span class="text-muted">n={{ data.scatter.sampleSize }} · p={{ data.scatter.pValue ?? '—' }} · {{ data.scatter.note }}</span>
          </div>
        </div>
        <ScatterChart v-if="data.scatter.points.length" :points="data.scatter.points" :groups="groups" :height="280" />
        <p v-else class="py-12 text-center text-[12px] text-muted">没有同时具备 Issue 与 PR 耗时的仓库，暂不绘制散点图。</p>
        <p v-if="data.scatter.points.length" class="m-0 text-[10.5px] text-muted">悬浮可查看 Issue / PR 各自有效样本量；中位数分界仅用于描述样本分布，不代表目标阈值或因果关系。</p>
      </GdCard>

      <GdCard>
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="m-0 text-[15.5px] font-semibold">数据质量</h3>
            <p class="mt-0.5 text-[12px] text-muted">条形显示仓库资料已具备 / 缺失比例；分母是数据集成员总数。事件指标有效样本见下方</p>
          </div>
        </div>
        <ResearchQualityChart :items="qualityItems" :height="190" />
        <div v-if="data.metricQuality.length" class="grid gap-2 border-t border-line pt-3 sm:grid-cols-2">
          <div v-for="metric in data.metricQuality" :key="metric.field" class="rounded-md bg-soft/50 px-2.5 py-2 text-[11px]">
            <div class="font-medium">{{ metric.field }} · 有效 {{ metric.validSamples }} / {{ data.repositoryCount }}</div>
            <div class="mt-0.5 text-muted">缺失 {{ metric.missingCount }}{{ metric.missingRate === null ? '' : `（${metric.missingRate}%）` }}<span v-if="metric.reasons.length"> · {{ metric.reasons.join('；') }}</span></div>
          </div>
        </div>
        <div class="text-[11px] leading-relaxed text-muted">{{ data.limitations.join(' ') }}</div>
      </GdCard>
      </template>
    </template>
  </div>
</template>
