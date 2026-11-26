<script setup lang="ts">
import { ArrowRight } from 'lucide-vue-next'
import { computed } from 'vue'
import type { G2Spec } from '@antv/g2'
import GdCard from '@/components/ui/GdCard.vue'
import KpiStrip from '@/components/common/KpiStrip.vue'
import ObservationList from '@/components/common/ObservationList.vue'
import CommitActivityComboChart from '@/components/charts/CommitActivityComboChart.vue'
import GroupedChart from '@/components/charts/GroupedChart.vue'
import DonutChart from '@/components/charts/DonutChart.vue'
import G2Chart from '@/components/charts/G2Chart.vue'
import TimelineChart from '@/components/charts/TimelineChart.vue'
import { coveredCommitPoints } from '@/components/charts/comboHelpers'
import { maintenanceReason } from '@/lib/maintenanceSummary'
import MaintenanceInsights from './MaintenanceInsights.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useDataSource } from '@/composables/useDataSource'
import type { RepositoryAnalysis, RepositoryEvaluation } from '@/services/types'

const props = defineProps<{ analysis: RepositoryAnalysis }>()
const emit = defineEmits<{ 'select-week': [payload: { date: string; count: number }] }>()
const repoId = computed(() => props.analysis.repository.id)
const source = useDataSource()
const { data: evaluation, loading: evaluationLoading, error: evaluationError } = useAsyncData<RepositoryEvaluation>(
  () => source.getEvaluation(String(repoId.value)),
  () => repoId.value,
)
const overviewObservations = computed(() => props.analysis.observations.filter((item) => item.id !== 'commit-trend'))
const commitsPoints = computed(() => {
  const points = props.analysis.commits.series[0]?.points ?? []
  return props.analysis.chartData ? coveredCommitPoints(points, props.analysis.chartData.commitWeekly) : points
})
const formalReleases = computed(() => props.analysis.releases
  .filter((release) => !release.prerelease)
  .sort((a, b) => a.publishedAt.localeCompare(b.publishedAt)))
const issueColors = computed(() => props.analysis.issues.series.map((series) => series.key === 'opened' ? '#E5A03A' : '#CE3F7C'))
const releaseIntervalPoints = computed(() => {
  const intervals = new Map(props.analysis.releaseIntervals.map((interval) => [interval.tag, interval.days]))
  return formalReleases.value.slice(1).flatMap((release, index) => {
    const previous = formalReleases.value[index]
    const days = intervals.get(release.tag) ?? release.intervalDays
    if (days == null || !Number.isFinite(days)) return []
    return [{
      previousTag: previous.tag,
      tag: release.tag,
      previousPublishedAt: previous.publishedAt,
      publishedAt: release.publishedAt,
      days,
    }]
  })
})
const latestRelease = computed(() => formalReleases.value.at(-1))
const latestReleaseLabel = computed(() => {
  if (!latestRelease.value) return '—'
  return latestRelease.value.identifierType === 'release_id' ? `Release #${latestRelease.value.tag}` : latestRelease.value.tag
})
const medianInterval = computed(() => {
  const days = releaseIntervalPoints.value.map((interval) => interval.days).sort((a, b) => a - b)
  if (!days.length) return null
  const middle = Math.floor(days.length / 2)
  return days.length % 2 ? days[middle] : (days[middle - 1] + days[middle]) / 2
})
const contributorRows = computed(() => {
  const chartData = props.analysis.chartData
  if (!chartData) return []
  const totals = chartData.commitAccounts.map((author) => ({ label: author, value: 0 }))
  let other = 0
  let unidentified = 0
  for (const week of chartData.commitWeekly) {
    if (!week.complete) continue
    totals.forEach((row, index) => { row.value += week.contributors[index] ?? 0 })
    other += week.otherCommits
    unidentified += week.unidentifiedCommits
  }
  const rows = totals.filter((row) => row.value > 0).slice(0, 5)
  if (other > 0) rows.push({ label: '其他已识别作者', value: other })
  if (unidentified > 0) rows.push({ label: '身份未识别', value: unidentified })
  return rows
})
const contributorTotal = computed(() => contributorRows.value.reduce((sum, row) => sum + row.value, 0))
const completeCommitWeeks = computed(() => props.analysis.chartData?.commitWeekly.filter((week) => week.complete).length ?? 0)
const waterfallData = computed(() => {
  const change = evaluation.value?.recentActivityChange
  if (!change || change.status === 'insufficient_data'
      || change.previousWeeklyMean === null || change.recentWeeklyMean === null || change.weeklyMeanChange === null
      || !change.previousWindowStart || !change.previousWindowEndExclusive
      || !change.recentWindowStart || !change.recentWindowEndExclusive
      || change.previousCompleteWeeks === 0 || change.recentCompleteWeeks === 0) return []
  const afterChange = change.previousWeeklyMean + change.weeklyMeanChange
  return [
    { stage: `此前周均 (${change.previousCompleteWeeks}/4 周)`, kind: '完整周均', start: 0, end: change.previousWeeklyMean, value: change.previousWeeklyMean, window: `${change.previousWindowStart.slice(0, 10)} 至 ${change.previousWindowEndExclusive.slice(0, 10)}`, completeWeeks: change.previousCompleteWeeks },
    { stage: '周均变化', kind: change.weeklyMeanChange >= 0 ? '增加' : '减少', start: Math.min(change.previousWeeklyMean, afterChange), end: Math.max(change.previousWeeklyMean, afterChange), value: change.weeklyMeanChange, window: `${change.recentWindowStart.slice(0, 10)} 至 ${change.recentWindowEndExclusive.slice(0, 10)}`, completeWeeks: change.recentCompleteWeeks },
    { stage: `最近周均 (${change.recentCompleteWeeks}/4 周)`, kind: '完整周均', start: 0, end: change.recentWeeklyMean, value: change.recentWeeklyMean, window: `${change.recentWindowStart.slice(0, 10)} 至 ${change.recentWindowEndExclusive.slice(0, 10)}`, completeWeeks: change.recentCompleteWeeks },
  ]
})
const waterfallUnavailableReason = computed(() => {
  const change = evaluation.value?.recentActivityChange
  if (!change) return '没有可读取的维护分析记录。'
  if (change.reasonCode === 'insufficient_complete_weeks') return '前后两个窗口至少各需 1 个完整 UTC 周；不完整周已单独排除。'
  if (change.reasonCode === 'short_history') return '最近两个四周窗口的数据不足，暂不能比较。'
  return maintenanceReason(change.reasonCode ?? change.status)
})
const waterfallSpec = computed<G2Spec>(() => ({
  type: 'interval',
  data: waterfallData.value,
  encode: { x: 'stage', y: ['end', 'start'], color: 'kind' },
  scale: { color: { domain: ['完整周均', '增加', '减少'], range: ['#73828d', '#4e927d', '#c47a59'] }, y: { zero: true } },
  axis: { x: { labelFontSize: 10 }, y: { title: 'Commit / 完整周', gridLineDash: [3, 3] } },
  legend: false,
  tooltip: { title: 'stage', items: [
    { field: 'kind', name: '阶段' },
    { field: 'value', name: 'Commit / 完整周' },
    { field: 'completeWeeks', name: '纳入完整周' },
    { field: 'window', name: 'UTC 窗口' },
  ] },
}))

function durationLabel(days: number | null) {
  if (days === null) return '—'
  if (days >= 365) return `${(days / 365).toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 年`
  return `${days.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 天`
}

function selectCommit(dataIndex: number) {
  const point = commitsPoints.value[dataIndex]
  if (point && (point.value !== null || point.observedValue !== null && point.observedValue !== undefined)) {
    emit('select-week', { date: point.date, count: point.value ?? point.observedValue ?? 0 })
  }
}

function repositorySizeLabel(sizeKb: number | null | undefined) {
  if (sizeKb == null) return '—'
  if (sizeKb >= 1024) return `${(sizeKb / 1024).toLocaleString('zh-CN', { maximumFractionDigits: 1 })} MB`
  return `${sizeKb.toLocaleString('zh-CN')} KB`
}
</script>

<template>
  <KpiStrip :metrics="analysis.metrics.metrics" />
  <MaintenanceInsights :repository-id="String(repoId)" :repository="analysis.repository" />

  <GdCard>
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h3 class="m-0 text-[15.5px] font-semibold">开发活动</h3>
        <p class="mt-0.5 text-[12px] text-muted">
          提交规模与活跃账号按 UTC 自然周聚合 · {{ analysis.commits.window.start }} 至 {{ analysis.commits.window.end }}
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <span class="rounded-md bg-track px-2 py-1 text-[11.5px] text-ink/70">{{ analysis.commits.limitation }}</span>
      </div>
    </div>
    <div class="relative">
      <CommitActivityComboChart
        :points="commitsPoints"
        :weeks="analysis.chartData?.commitWeekly ?? []"
        :window-start="analysis.commits.window.startUtc ?? analysis.commits.window.start"
        :window-end="analysis.commits.window.endUtc ?? analysis.commits.window.end"
        @select="selectCommit"
      />
    </div>
    <div class="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted">
      <span>左图柱表示完整周 Commit，虚线为连续四个完整周均值；右图面积表示活跃账号趋势。空心点表示部分覆盖的已观察样本。未覆盖数据不补零。SHA 去重 · UTC · 有效样本 {{ analysis.commits.sampleSize?.toLocaleString('en-US') ?? '—' }}</span>
      <span>点击 Commit 或账号趋势查看周明细</span>
    </div>
  </GdCard>

  <div class="grid gap-4 lg:grid-cols-2">
    <GdCard class="min-w-0" data-testid="overview-contributor-composition">
      <div><h3 class="m-0 text-[15.5px] font-semibold">贡献者构成</h3><p class="mt-0.5 text-[12px] text-muted">Top 5 账号、其他已识别作者与身份未识别提交</p></div>
      <DonutChart v-if="contributorRows.length" :rows="contributorRows" :total="contributorTotal.toLocaleString('zh-CN')" center-label="完整周 Commit" label="仓库贡献者 Commit 构成环形图" :height="245" />
      <div v-else class="flex h-[245px] items-center justify-center text-[12px] text-muted">暂无完整周作者贡献样本</div>
      <p class="m-0 text-[10.5px] leading-relaxed text-muted">纳入 {{ completeCommitWeeks }} / {{ analysis.chartData?.commitWeekly.length ?? 0 }} 个完整 UTC 周，共 {{ contributorTotal.toLocaleString('zh-CN') }} 次 Commit；不完整周不进入构成统计，Bot 身份不从账号名称推断。</p>
    </GdCard>

    <GdCard class="min-w-0" data-testid="overview-activity-waterfall">
      <div><h3 class="m-0 text-[15.5px] font-semibold">最近 4 周活动变化</h3><p class="mt-0.5 text-[12px] text-muted">比较前后两个四周窗口的完整周 Commit 均值；不完整周单独标记并排除</p></div>
      <div v-if="evaluationLoading" class="flex h-[245px] items-center justify-center text-[12px] text-muted" role="status">正在读取维护窗口…</div>
      <div v-else-if="evaluationError" class="flex h-[245px] items-center justify-center text-center text-[12px] text-muted" role="alert">读取失败：{{ evaluationError }}</div>
      <G2Chart v-else-if="waterfallData.length" :spec="waterfallSpec" label="最近与此前四周窗口完整周 Commit 均值变化图" :height="245" />
      <div v-else class="flex h-[245px] items-center justify-center px-5 text-center text-[12px] leading-relaxed text-muted">{{ waterfallUnavailableReason }}</div>
      <p v-if="waterfallData.length" class="m-0 text-[10.5px] leading-relaxed text-muted">按完整周周均比较，避免两侧有效周数不同造成总量偏差。<template v-if="evaluation?.recentActivityChange.incompleteWeekStarts.length">已排除 {{ evaluation.recentActivityChange.incompleteWeekStarts.length }} 个覆盖不完整周：{{ evaluation.recentActivityChange.incompleteWeekStarts.map((date) => date.slice(0, 10)).join('、') }}。</template></p>
    </GdCard>
  </div>

  <div class="grid items-stretch gap-4 lg:grid-cols-3">
    <GdCard>
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[14.5px] font-semibold">Issue 处理</h3>
          <p class="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11.5px] text-muted">
            <span>Issue {{ analysis.chartData ? '新增与关闭数' : '关闭数' }} · 按周</span>
            <span v-for="(series, index) in analysis.issues.series" :key="series.key" class="inline-flex items-center gap-1 text-[10.5px]">
              <span class="inline-block h-2 w-2 rounded-sm" :style="{ backgroundColor: issueColors[index] }" />{{ series.label }}
            </span>
          </p>
        </div>
        <RouterLink :to="`/repositories/${repoId}/issues`" class="gd-link text-[11.5px]">查看分析 <ArrowRight :size="12" /></RouterLink>
      </div>
      <GroupedChart :series="analysis.issues.series" :unit="analysis.issues.unit" :colors="['#E5A03A', '#CE3F7C']" :height="150" :show-legend="false" />
      <div class="flex items-end gap-3">
        <b class="text-[20px] font-semibold">{{ analysis.issueDuration.percentiles.p50 ?? '—' }} 天</b>
        <span class="text-[11px] leading-tight text-muted">关闭耗时 P50<br />n={{ analysis.issueDuration.sampleSize }} · P90 <span :title="analysis.issueDuration.percentiles.p90 == null ? undefined : `${analysis.issueDuration.percentiles.p90.toLocaleString('zh-CN')} 天`">{{ durationLabel(analysis.issueDuration.percentiles.p90) }}</span></span>
      </div>
    </GdCard>

    <GdCard>
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[14.5px] font-semibold">PR 协作</h3>
          <p class="mt-0.5 text-[11.5px] text-muted">PR 合并数 · 按周</p>
        </div>
        <RouterLink :to="`/repositories/${repoId}/prs`" class="gd-link text-[11.5px]">查看分析 <ArrowRight :size="12" /></RouterLink>
      </div>
      <GroupedChart :series="analysis.pullRequests.series" :unit="analysis.pullRequests.unit" :colors="['#CE3F7C', '#2E8FCB']" :height="150" :show-legend="false" />
      <div class="flex items-end gap-3">
        <b class="text-[20px] font-semibold">{{ analysis.prDuration.percentiles.p50 ?? '—' }} 天</b>
        <span class="text-[11px] leading-tight text-muted">合并耗时 P50<br />n={{ analysis.prDuration.sampleSize }} · P90 {{ analysis.prDuration.percentiles.p90 ?? '—' }} 天</span>
      </div>
    </GdCard>

    <GdCard>
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[14.5px] font-semibold">Release 时间线</h3>
          <p class="mt-0.5 text-[11.5px] text-muted">按时间段统计正式版与预发布版数量</p>
        </div>
        <RouterLink :to="`/repositories/${repoId}/releases`" class="gd-link text-[11.5px]">查看分析 <ArrowRight :size="12" /></RouterLink>
      </div>
      <TimelineChart v-if="analysis.releases.length" :releases="analysis.releases" :compact="true" :height="150" />
      <div v-else class="flex h-[150px] items-center justify-center text-center text-[11px] text-muted">当前没有已采集的 Release 时间点</div>
      <div class="flex items-end gap-3">
        <b class="text-[20px] font-semibold">{{ medianInterval?.toLocaleString('en-US', { maximumFractionDigits: 1 }) ?? '—' }} 天</b>
        <span class="text-[11px] leading-tight text-muted">正式版间隔 P50 · n={{ releaseIntervalPoints.length }}<br />{{ formalReleases.length }} 次正式发布 · 最近 {{ latestReleaseLabel }} · {{ latestRelease?.publishedAt.slice(0, 10) ?? '—' }}</span>
      </div>
    </GdCard>
  </div>

  <div class="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
    <GdCard class="h-[360px] overflow-hidden">
      <div>
        <h3 class="m-0 text-[15.5px] font-semibold">主要数据观察</h3>
        <p class="mt-0.5 text-[12px] text-muted">完整 8 周提交趋势、Issue/PR 耗时（n≥10）、正式发布节奏（至少 2 次）；部分覆盖只描述已观察样本。</p>
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
        <ObservationList :observations="overviewObservations" />
      </div>
    </GdCard>

    <GdCard class="h-[360px] overflow-hidden">
      <div>
        <h3 class="m-0 text-[15.5px] font-semibold">基础资料</h3>
        <p class="mt-0.5 text-[12px] text-muted">采集时点快照</p>
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
        <div class="space-y-2">
          <div class="grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-3">
            <div><div class="text-[11px] text-muted">Stars</div><div class="mt-0.5 text-[13px] font-medium">{{ analysis.repository.stars?.toLocaleString('en-US') ?? '—' }}</div></div>
            <div><div class="text-[11px] text-muted">Forks</div><div class="mt-0.5 text-[13px] font-medium">{{ analysis.repository.forks?.toLocaleString('en-US') ?? '—' }}</div></div>
            <div><div class="text-[11px] text-muted">主要语言</div><div class="mt-0.5 text-[13px] font-medium">{{ analysis.repository.language ?? '—' }}</div></div>
            <div><div class="text-[11px] text-muted">许可证</div><div class="mt-0.5 text-[13px] font-medium">{{ analysis.repository.license ?? '—' }}</div></div>
            <div><div class="text-[11px] text-muted">开放 Issue / PR</div><div class="mt-0.5 text-[13px] font-medium">{{ analysis.repository.openIssuesAndPrCount?.toLocaleString('en-US') ?? '—' }}</div></div>
            <div><div class="text-[11px] text-muted">仓库大小</div><div class="mt-0.5 text-[13px] font-medium">{{ repositorySizeLabel(analysis.repository.sizeKb) }}</div></div>
            <div><div class="text-[11px] text-muted">创建日期</div><div class="mt-0.5 text-[13px] font-medium">{{ analysis.repository.createdAt ?? '—' }}</div></div>
            <div><div class="text-[11px] text-muted">最近推送</div><div class="mt-0.5 text-[13px] font-medium">{{ analysis.repository.pushedAt ?? '—' }}</div></div>
            <div><div class="text-[11px] text-muted">归档状态</div><div class="mt-0.5 text-[13px] font-medium">{{ analysis.repository.archived == null ? '—' : analysis.repository.archived ? '已归档' : '未归档' }}</div></div>
          </div>
          <div class="border-t border-line pt-3">
            <div class="text-[11px] text-muted">Topics</div>
            <div v-if="analysis.repository.topics.length" class="mt-1.5 flex flex-wrap gap-1.5">
              <span v-for="topic in analysis.repository.topics" :key="topic" class="rounded-md bg-track px-2 py-1 text-[11px] text-ink/75">{{ topic }}</span>
            </div>
            <p v-else class="mt-1 text-[12px] text-muted">未设置 Topics</p>
          </div>
          <p class="m-0 text-[11px] leading-relaxed text-muted">Stars / Forks 为背景信息，不参与开发活动分析；开放数量包含 PR。</p>
        </div>
      </div>
    </GdCard>
  </div>
</template>
