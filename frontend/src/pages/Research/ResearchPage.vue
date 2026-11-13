<script setup lang="ts">
import { BookOpen, Download } from 'lucide-vue-next'
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref } from 'vue'
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
import CourseResearchDashboard from './CourseResearchDashboard.vue'

const ResearchGroupComboChart = defineAsyncComponent(() => import('@/components/charts/ResearchGroupComboChart.vue'))
const ResearchQualityChart = defineAsyncComponent(() => import('@/components/charts/ResearchQualityChart.vue'))
const ScatterChart = defineAsyncComponent(() => import('@/components/charts/ScatterChart.vue'))
const ui = useUiStore()
const analysisStore = useAnalysisStore()
const source = useDataSource()
const exporting = ref(false)
const requestedMode = ref<ResearchAnalysisMode | 'auto'>('auto')
const repositorySearch = ref('')
const { data, loading, error } = useAsyncData(() => source.getResearchDataset(undefined, requestedMode.value), () => requestedMode.value)
const entrySkeletonVisible = ref(true)
let entrySkeletonTimer: ReturnType<typeof setTimeout> | undefined
const showSkeleton = computed(() => loading.value || entrySkeletonVisible.value)

onMounted(() => {
  entrySkeletonTimer = setTimeout(() => {
    entrySkeletonVisible.value = false
    entrySkeletonTimer = undefined
  }, 480)
})

onBeforeUnmount(() => {
  if (entrySkeletonTimer) clearTimeout(entrySkeletonTimer)
})

const modeOptions = [
  { value: 'course', label: '默认 300 仓库', hint: '使用 dataprepare 中已采集的 300 个仓库数据；查看分析和比较时复用本地快照。' },
  { value: 'formal', label: '正式研究', hint: '只读取已确认并导入的研究样本；不会替用户冻结样本清单。' },
]
const selectedMode = computed(() => requestedMode.value === 'auto' ? data.value?.analysisMode ?? 'course' : requestedMode.value)

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

function setMode(value: string | number) {
  if (value === 'formal' || value === 'course') requestedMode.value = value
}

function qualityFieldLabel(field: string) {
  return ({ language: '主语言', stars: 'Star 数', forks: 'Fork 数', pushed_at: '最近推送时间', created_at: '创建时间' } as Record<string, string>)[field] ?? field
}

function qualityPercent(item: { missingCount: number; totalRecords: number }) {
  return item.totalRecords > 0 ? (item.totalRecords - item.missingCount) / item.totalRecords * 100 : 0
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

</script>

<template>
  <div class="flex flex-col gap-[18px] px-4 pb-8 pt-5 sm:px-7 sm:pt-[22px]">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="m-0 text-[24px] font-semibold">研究分析</h1>
        <p class="mt-1.5 text-muted">默认仓库为已采集的 300 个项目；仓库分析与比较直接复用本地历史数据。</p>
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
    <Transition v-else name="research-content" mode="out-in" appear>
      <div v-if="showSkeleton" key="research-skeleton" class="flex flex-col gap-[18px]" role="status" aria-live="polite" aria-label="正在加载研究分析" aria-busy="true">
        <div class="rounded-[14px] border border-line bg-panel p-4 sm:p-5">
          <div class="flex items-start justify-between gap-4">
            <div class="flex-1 space-y-2">
              <div class="gd-skeleton-shimmer h-5 w-44 rounded" />
              <div class="gd-skeleton-shimmer h-3.5 w-72 max-w-full rounded" />
            </div>
            <div class="gd-skeleton-shimmer h-7 w-28 rounded-md" />
          </div>
          <div class="mt-5 grid grid-cols-2 gap-4 border-y border-line py-4 lg:grid-cols-4">
            <div v-for="item in 4" :key="`summary-${item}`" class="space-y-2">
              <div class="gd-skeleton-shimmer h-3 w-20 rounded" />
              <div class="gd-skeleton-shimmer h-7 w-24 rounded" />
              <div class="gd-skeleton-shimmer h-3 w-28 max-w-full rounded" />
            </div>
          </div>
          <div class="mt-4 grid gap-3 sm:grid-cols-3">
            <div v-for="item in 3" :key="`metric-${item}`" class="space-y-2 rounded-md bg-soft/50 p-3">
              <div class="gd-skeleton-shimmer h-3 w-24 rounded" />
              <div class="gd-skeleton-shimmer h-5 w-28 rounded" />
              <div class="gd-skeleton-shimmer h-3 w-20 rounded" />
            </div>
          </div>
        </div>
        <div class="grid min-w-0 gap-[18px] lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
          <div class="min-h-[280px] rounded-[14px] border border-line bg-panel p-4 sm:p-5">
            <div class="gd-skeleton-shimmer h-4 w-48 rounded" />
            <div class="gd-skeleton-shimmer mt-2 h-3 w-64 max-w-full rounded" />
            <div class="mt-7 flex h-[190px] items-end gap-3 border-b border-l border-line px-4">
              <div v-for="item in 7" :key="`bar-${item}`" class="gd-skeleton-shimmer w-full rounded-t" :style="{ height: `${28 + (item * 23) % 58}%` }" />
            </div>
          </div>
          <div class="min-h-[280px] rounded-[14px] border border-line bg-panel p-4 sm:p-5">
            <div class="gd-skeleton-shimmer h-4 w-36 rounded" />
            <div class="gd-skeleton-shimmer mt-2 h-3 w-52 max-w-full rounded" />
            <div class="mt-7 space-y-6">
              <div v-for="item in 3" :key="`coverage-${item}`" class="space-y-2">
                <div class="flex justify-between gap-4"><div class="gd-skeleton-shimmer h-3 w-28 rounded" /><div class="gd-skeleton-shimmer h-3 w-20 rounded" /></div>
                <div class="gd-skeleton-shimmer h-2 w-full rounded-full" />
              </div>
            </div>
          </div>
        </div>
        <div class="rounded-[14px] border border-line bg-panel p-4 sm:p-5">
          <div class="flex items-center justify-between gap-4">
            <div class="gd-skeleton-shimmer h-4 w-24 rounded" />
            <div class="gd-skeleton-shimmer h-8 w-52 max-w-[50%] rounded-md" />
          </div>
          <div class="mt-4 space-y-3">
            <div v-for="item in 4" :key="`repo-${item}`" class="gd-skeleton-shimmer h-10 rounded-md" />
          </div>
        </div>
      </div>

      <div v-else-if="data" key="research-results" class="flex flex-col gap-[18px]">
      <GdCard v-if="data.repositoryCount === 0" class="gap-3" data-testid="research-empty-state">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 v-if="data.analysisMode === 'course'" class="m-0 text-[16px] font-semibold">默认 300 仓库数据暂不可用</h2>
            <h2 v-else class="m-0 text-[16px] font-semibold">正式研究样本尚不可分析</h2>
            <p v-if="data.analysisMode === 'course'" class="mt-1 text-[12px] leading-relaxed text-muted">本机没有可显示的 300 仓库数据，请检查课程数据包和导入状态。</p>
            <p v-else class="mt-1 text-[12px] leading-relaxed text-muted">
              {{ data.studyStatus === 'pending_confirmation' ? '研究样本清单仍待负责人确认；当前未生成正式结果。' : data.studyStatus === 'approved_not_imported' ? '样本已确认，但成员清单尚未导入。' : '成员清单已导入，尚无可分析的本地采集结果。' }}
            </p>
          </div>
          <GdBadge variant="warn">{{ data.analysisMode === 'course' ? '暂无样本' : data.studyStatus === 'pending_confirmation' ? '待确认' : data.studyStatus === 'approved_not_imported' ? '待导入' : '等待样本' }}</GdBadge>
        </div>
      </GdCard>

      <template v-else>
      <GdCard v-if="data.analysisMode !== 'course'">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="flex items-center gap-2">
            <span class="font-mono text-[13px] font-semibold">{{ data.name }}</span>
            <GdBadge variant="plain">正式研究</GdBadge>
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
            <div class="text-[11px] text-muted">冻结日期</div>
            <div class="mt-1 text-[12.5px] font-medium">{{ data.frozenAt ?? '后端未记录' }}</div>
            <div class="mt-0.5 text-[11px] text-muted">观察窗口 {{ data.eventWindow.start ?? '—' }} — {{ data.eventWindow.end ?? '—' }}</div>
          </div>
          <div class="border-line lg:border-l lg:pl-4">
            <div class="text-[11px] text-muted">样本与总体范围</div>
            <div class="mt-1 text-[12.5px] font-medium">{{ data.repositoryCount }} 个仓库 · {{ data.scatter.sampleSize }} 个有效配对</div>
            <div class="mt-0.5 text-[11px] text-muted">{{ data.isProbabilitySample ? '概率样本' : '非概率样本' }} · {{ data.populationScope }}</div>
            <div class="mt-0.5 text-[11px] text-muted">Issue 指标缺失率 {{ data.missingRate === null ? '—' : `${data.missingRate}%` }}</div>
          </div>
        </div>
      </GdCard>

      <CourseResearchDashboard
        v-if="data.analysisMode === 'course'"
        v-model:repository-search="repositorySearch"
        :data="data"
        :compare-ids="analysisStore.compareIds"
        @compare="addToComparison"
        @definitions="ui.openDrawer('definitions', { metric: 'M14', sample: `${data.repositoryCount} 个仓库 · ${data.scatter.sampleSize} 个有效配对` })"
      />

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

      <GdCard data-testid="research-data-quality">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="m-0 text-[15.5px] font-semibold">数据质量</h3>
            <p class="mb-0 mt-1 text-[12px] leading-relaxed text-muted">仓库资料完整度与研究统计的有效样本分开呈现，分母均为数据集成员数。</p>
          </div>
        </div>
        <div class="grid min-w-0 gap-5 xl:grid-cols-2">
          <div class="min-w-0">
            <h4 class="m-0 text-[12.5px] font-medium">仓库资料完整度</h4>
            <ResearchQualityChart v-if="data.analysisMode !== 'course'" :items="qualityItems" :height="190" />
            <div v-else class="mt-3 flex flex-col gap-3">
              <div v-for="item in qualityItems" :key="item.field">
                <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-[11.5px]">
                  <span class="font-medium">{{ qualityFieldLabel(item.field) }}</span>
                  <span class="tabular-nums text-muted">{{ item.totalRecords - item.missingCount }} / {{ item.totalRecords }} 已具备 · 缺失 {{ item.missingCount }}</span>
                </div>
                <div class="mt-1.5 h-2 overflow-hidden rounded-full bg-track" aria-hidden="true"><div class="h-full rounded-full bg-s1" :style="{ width: `${qualityPercent(item)}%` }" /></div>
              </div>
            </div>
          </div>
          <div v-if="data.metricQuality.length" class="min-w-0">
            <h4 class="m-0 text-[12.5px] font-medium">研究指标可用性</h4>
            <div class="mt-3 grid gap-2 sm:grid-cols-2">
              <div v-for="metric in data.metricQuality" :key="metric.field" class="rounded-md bg-soft/50 px-3 py-2.5 text-[11.5px] leading-relaxed">
                <div class="font-medium">{{ metric.field }}</div>
                <div class="mt-1 text-muted">有效 {{ metric.validSamples }} / {{ data.repositoryCount }} · 未形成结果 {{ metric.missingCount }}{{ metric.missingRate === null ? '' : `（${metric.missingRate}%）` }}</div>
                <div v-if="metric.partialCount" class="mt-1 text-muted">其中 {{ metric.partialCount }} 个结果为部分覆盖</div>
                <div v-if="metric.reasons.length" class="mt-1 text-muted">{{ metric.reasons.join('；') }}</div>
              </div>
            </div>
          </div>
        </div>
        <div class="border-t border-line pt-3 text-[11.5px] leading-relaxed text-muted">
          <p v-if="data.analysisMode === 'course'" class="mb-2 mt-0">本页使用周级提交汇总和本地事件快照；没有有效耗时记录时不计算中位数。</p>
          <ul class="m-0 list-disc space-y-1 pl-4"><li v-for="limitation in data.limitations" :key="limitation">{{ limitation }}</li></ul>
        </div>
      </GdCard>
      </template>
      </div>
    </Transition>
  </div>
</template>
