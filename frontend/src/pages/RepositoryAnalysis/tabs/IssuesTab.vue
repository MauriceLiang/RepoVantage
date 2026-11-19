<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import IssueTrendChart from '@/components/charts/IssueTrendChart.vue'
import GroupedChart from '@/components/charts/GroupedChart.vue'
import HistogramChart from '@/components/charts/HistogramChart.vue'
import BoxPlotChart from '@/components/charts/BoxPlotChart.vue'
import CalendarHeatmap from '@/components/charts/CalendarHeatmap.vue'
import KpiStrip from '@/components/common/KpiStrip.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import GdCoverageNote from '@/components/ui/GdCoverageNote.vue'
import GdInput from '@/components/ui/GdInput.vue'
import { useDataSource } from '@/composables/useDataSource'
import { usePagedRecords } from '@/composables/usePagedRecords'
import { downloadBlob } from '@/lib/download'
import { formatDate, formatDuration, formatTime } from '@/lib/format'
import { dailyCoveragePoints, groupByMonth } from '@/lib/chartAnalytics'
import type { IssueRecord, IssueRecordPage, RepositoryAnalysis } from '@/services/types'
import { useUiStore } from '@/stores/ui'

const props = defineProps<{ analysis: RepositoryAnalysis }>()
const ui = useUiStore()
const source = useDataSource()
const { page, searchInput, appliedSearch, records, loading, loadError, pageCount, firstRecord, lastRecord, loadRecords, applySearch } = usePagedRecords<IssueRecordPage>(
  () => props.analysis.repository.id,
  (id, page, perPage, search) => source.getIssueRecords(id, page, perPage, search, props.analysis.windowAvailability.requestedDays),
  'Issue 记录加载失败',
  () => props.analysis.windowAvailability.requestedDays,
)
const exporting = ref(false)
const issueViz = ref<{ items: IssueRecord[]; total: number; complete: boolean; available: boolean; note: string; windowStart: string | null; windowEnd: string | null; coverage: IssueRecordPage['coverage'] } | null>(null)
const issueVizLoading = ref(false)
const issueVizError = ref('')
let issueDetailRequest = 0
watch(() => props.analysis.windowAvailability.requestedDays, () => { page.value = 1 }, { flush: 'sync' })

const issueBoxSamples = computed(() => groupByMonth((issueViz.value?.items ?? []).map((item) => ({ date: item.closedAt, value: item.durationDays }))))
const issueClosedDaily = computed(() => {
  const counts = new Map<string, number>()
  for (const item of issueViz.value?.items ?? []) {
    const date = item.closedAt.slice(0, 10)
    if (/^\d{4}-\d{2}-\d{2}$/.test(date)) counts.set(date, (counts.get(date) ?? 0) + 1)
  }
  return dailyCoveragePoints(
    [...counts.entries()].map(([date, count]) => ({ date, count })),
    issueViz.value?.windowStart,
    issueViz.value?.windowEnd,
    issueViz.value?.complete === true && issueViz.value.coverage.state === 'complete',
  )
})

async function loadIssueVisualData() {
  const repositoryId = props.analysis.repository.id
  const windowDays = props.analysis.windowAvailability.requestedDays
  issueVizLoading.value = true
  issueVizError.value = ''
  issueViz.value = null
  try {
    const first = await source.getIssueRecords(repositoryId, 1, 100, '', windowDays)
    if (!first.available) {
      issueViz.value = { ...first, items: [], total: first.total, complete: false }
      return
    }
    const requestedPages = Math.min(10, Math.ceil(first.total / 100))
    const rest = requestedPages > 1
      ? await Promise.all(Array.from({ length: requestedPages - 1 }, (_, index) => source.getIssueRecords(repositoryId, index + 2, 100, '', windowDays)))
      : []
    const items = [first, ...rest].flatMap((result) => result.items)
    issueViz.value = { ...first, items, total: first.total, complete: items.length >= first.total }
  } catch (cause) {
    issueVizError.value = cause instanceof Error ? cause.message : 'Issue 图表样本加载失败'
  } finally {
    issueVizLoading.value = false
  }
}
watch([() => props.analysis.repository.id, () => props.analysis.windowAvailability.requestedDays], () => { void loadIssueVisualData() }, { immediate: true })

async function openIssue(item: IssueRecord) {
  const requestId = ++issueDetailRequest
  const payload = {
    repositoryId: props.analysis.repository.id,
    number: String(item.number),
    title: item.title,
    createdAt: item.createdAt ?? '',
    closedAt: item.closedAt,
    durationDays: item.durationDays === null ? '—' : formatDuration(item.durationDays),
    url: item.url ?? '',
    state: 'closed',
    historicalSnapshot: props.analysis.provenance?.origin === 'course-test-events-v1' ? 'true' : 'false',
    onlineStatus: 'idle',
    bodyStatus: 'loading',
  }
  ui.openDrawer('issue', payload)
  try {
    const detail = await source.getIssueDetail(props.analysis.repository.id, item.number)
    if (requestId !== issueDetailRequest || ui.drawerKind !== 'issue' || ui.drawerPayload?.number !== String(item.number)) return
    if (ui.drawerPayload?.onlineStatus === 'loading' || ui.drawerPayload?.onlineStatus === 'ready') return
    ui.openDrawer('issue', { ...payload, bodyStatus: 'ready', body: detail.body ?? '', commentsCount: String(detail.commentsCount) })
  } catch (cause) {
    if (requestId !== issueDetailRequest || ui.drawerKind !== 'issue' || ui.drawerPayload?.number !== String(item.number)) return
    ui.openDrawer('issue', { ...payload, bodyStatus: 'error', bodyError: cause instanceof Error ? cause.message : '无法读取该 Issue 的详细内容' })
  }
}

async function exportCsv() {
  exporting.value = true
  try {
    downloadBlob(await source.exportIssueRecords(props.analysis.repository.id, appliedSearch.value, props.analysis.windowAvailability.requestedDays), `${props.analysis.repository.id}-issues.csv`)
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '导出 Issue 记录失败', 'error')
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <KpiStrip :metrics="analysis.metrics.metrics" />

  <GdCard>
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3 class="m-0 text-[15.5px] font-semibold">Issue 处理趋势</h3>
        <p class="mt-0.5 text-[12px] text-muted">按创建和关闭时间统计自然周 · 已排除 Pull Request</p>
      </div>
      <GdCoverageNote :coverage="analysis.issues.coverage" />
    </div>
    <IssueTrendChart v-if="analysis.chartData" :series="analysis.issues.series" :coverage="analysis.issues.coverage.state" :window-start="analysis.issues.window.startUtc ?? analysis.issues.window.start" :window-end="analysis.issues.window.endUtc ?? analysis.issues.window.end" />
    <GroupedChart v-else :series="analysis.issues.series" :unit="analysis.issues.unit" :height="250" />
    <p v-if="analysis.chartData" class="text-[11px] text-muted">柱为每周新增与关闭数，折线为完整周的两者差值；差值不等于待处理数量。已观察样本与完整覆盖状态分别显示。</p>
    <p v-else class="text-[11px] text-muted">当前数据未提供新增 Issue 趋势，显示已采集的关闭数量。</p>
  </GdCard>

  <div class="grid gap-4 lg:grid-cols-[1fr_1.15fr]">
    <GdCard class="h-[420px] min-h-0 overflow-hidden">
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">关闭耗时分布</h3>
          <p class="mt-0.5 text-[12px] text-muted">closed_at − created_at · 柱为区间样本数，折线为累计占比</p>
        </div>
        <span class="font-mono text-[11.5px] text-muted">n={{ analysis.issueDuration.sampleSize }}</span>
      </div>
      <HistogramChart :buckets="analysis.issueDuration.buckets" color="#E5A03A" unit="个 Issue" :height="200" :median-days="analysis.issueDuration.percentiles.p50" show-median-reference class="min-h-[200px] flex-1 w-full" />
      <p v-if="analysis.issueDuration.sampleSize > 0 && analysis.issueDuration.percentiles.p50 !== null" class="text-[11px] text-muted">柱为耗时区间数量；折线表示累计占比，Tooltip 给出准确百分比。中位数以 P50 标示。</p>
      <div class="text-[11px] text-muted">P50 {{ analysis.issueDuration.percentiles.p50 ?? '—' }} 天 · P75 {{ analysis.issueDuration.percentiles.p75 ?? '—' }} 天 · P90 {{ analysis.issueDuration.percentiles.p90 ?? '—' }} 天</div>
      <p v-if="analysis.issueDuration.note" class="mt-2 text-[11px] text-warnfg">{{ analysis.issueDuration.note }}</p>
    </GdCard>

    <GdCard class="h-[420px] min-h-0 overflow-hidden">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex min-w-0 items-center gap-2">
          <h3 class="m-0 text-[15.5px] font-semibold">Issue 逐条记录</h3>
          <GdCoverageNote v-if="records" :coverage="records.coverage" compact />
        </div>
        <GdButton variant="outline" size="sm" :disabled="exporting || loading || !records?.available" @click="exportCsv">{{ exporting ? '导出中…' : '导出 Issue CSV' }}</GdButton>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <GdInput v-model="searchInput" size="sm" class="min-w-[190px] flex-1" placeholder="搜索 Issue 编号或标题" @enter="applySearch" />
        <GdButton variant="outline" size="sm" :disabled="loading" @click="applySearch">搜索</GdButton>
        <span v-if="records?.available" class="shrink-0 text-[11px] text-muted">{{ records.total.toLocaleString('zh-CN') }} 条 · {{ formatDate(records.windowStart) }} 至 {{ formatDate(records.windowEnd) }}</span>
      </div>

      <p v-if="records?.note" class="m-0 text-[11px] leading-relaxed text-muted">{{ records.note }}</p>

      <div v-if="loading" class="min-h-0 flex-1 overflow-y-auto py-8 text-center text-[12px] text-muted" role="status">正在加载 Issue 记录…</div>
      <div v-else-if="loadError" class="min-h-0 flex-1 overflow-y-auto py-6 text-center text-[12px] text-danger">
        <p class="mb-3">{{ loadError }}</p>
        <GdButton variant="outline" size="sm" @click="loadRecords">重新加载</GdButton>
      </div>
      <div v-else-if="records && !records.available" class="min-h-0 flex-1 overflow-y-auto rounded-md bg-soft px-3 py-8 text-center text-[12px] leading-relaxed text-muted">{{ records.note }}</div>
      <div v-else-if="records && records.total === 0" class="min-h-0 flex-1 overflow-y-auto rounded-md bg-soft px-3 py-8 text-center text-[12px] text-muted">{{ appliedSearch ? '没有找到匹配的 Issue。' : '本次采集窗口内没有已关闭的 Issue。' }}</div>
      <div v-else class="min-h-0 flex-1 overflow-auto overscroll-contain">
        <table class="w-full min-w-[480px] table-fixed border-collapse text-[12px]">
          <thead class="sticky top-0 z-10 bg-panel">
            <tr class="text-left text-[11px] text-muted">
              <th class="w-[40px] border-b border-line px-1.5 pb-2 font-medium">编号</th>
              <th class="w-[166px] border-b border-line px-1.5 pb-2 font-medium">标题</th>
              <th class="w-[76px] border-b border-line px-1.5 pb-2 font-medium">创建时间</th>
              <th class="w-[76px] border-b border-line px-1.5 pb-2 font-medium">关闭时间</th>
              <th class="w-[56px] border-b border-line px-1.5 pb-2 font-medium">耗时</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in records?.items" :key="item.number" class="border-b border-line/70 last:border-0">
              <td class="whitespace-nowrap px-1.5 py-2.5 font-mono text-ink">
                <button type="button" class="underline decoration-line underline-offset-2 hover:decoration-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2" @click="openIssue(item)">#{{ item.number }}</button>
              </td>
              <td class="px-1.5 py-2.5 text-ink" :title="item.title"><button type="button" class="line-clamp-2 text-left hover:underline focus-visible:underline" @click="openIssue(item)">{{ item.title }}</button></td>
              <td class="whitespace-nowrap px-1.5 py-2 font-mono text-[10.5px] text-ink">
                <span>{{ formatDate(item.createdAt) }}</span>
                <span class="block text-[9px] leading-3 text-ink/70">{{ formatTime(item.createdAt) }}</span>
              </td>
              <td class="whitespace-nowrap px-1.5 py-2 font-mono text-[10.5px] text-ink">
                <span>{{ formatDate(item.closedAt) }}</span>
                <span class="block text-[9px] leading-3 text-ink/70">{{ formatTime(item.closedAt) }}</span>
              </td>
              <td class="whitespace-nowrap px-1.5 py-2.5 text-[11px] text-ink">{{ formatDuration(item.durationDays) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="records?.available && records.total > 0" class="flex shrink-0 items-center justify-between gap-2 border-t border-line pt-2 text-[11px] text-muted">
        <span>显示 {{ firstRecord }}–{{ lastRecord }} / {{ records.total }}</span>
        <div class="flex items-center gap-2">
          <GdButton variant="outline" size="sm" :disabled="loading || page <= 1" @click="page -= 1">上一页</GdButton>
          <span class="font-mono">{{ page }} / {{ pageCount }}</span>
          <GdButton variant="outline" size="sm" :disabled="loading || page >= pageCount" @click="page += 1">下一页</GdButton>
        </div>
      </div>
    </GdCard>
  </div>

  <div class="grid gap-4 lg:grid-cols-2">
    <GdCard class="min-w-0" data-testid="issue-duration-boxplot-card">
      <div class="flex flex-wrap items-start justify-between gap-3"><div><h3 class="m-0 text-[15.5px] font-semibold">按月关闭耗时箱线图</h3><p class="mt-0.5 text-[12px] text-muted">按 closed_at 月份分组，仅显示每组至少 5 条的月份</p></div><GdCoverageNote v-if="issueViz" :coverage="issueViz.coverage" compact /></div>
      <div v-if="issueVizLoading" class="flex h-[280px] items-center justify-center text-[12px] text-muted" role="status">正在汇总 Issue 关闭样本…</div>
      <div v-else-if="issueVizError" class="flex h-[280px] items-center justify-center text-center text-[12px] text-danger" role="alert">{{ issueVizError }}</div>
      <BoxPlotChart v-else-if="issueBoxSamples.length" :samples="issueBoxSamples" label="Issue 每月关闭耗时箱线图" unit="关闭耗时（天）" :height="260" />
      <div v-else class="flex h-[280px] items-center justify-center text-center text-[12px] text-muted">当前数据中没有样本量达到 5 的月份；已加载 {{ issueViz?.items.length ?? 0 }} / {{ issueViz?.total ?? 0 }} 条。</div>
      <p v-if="issueViz && !issueViz.complete" class="m-0 text-[10.5px] text-muted">图表最多读取前 1,000 条可用记录（{{ issueViz.items.length }} / {{ issueViz.total }}）；月度分布仅代表已加载样本。</p>
    </GdCard>
    <GdCard class="min-w-0" data-testid="issue-close-heatmap-card">
      <div class="flex flex-wrap items-start justify-between gap-3"><div><h3 class="m-0 text-[15.5px] font-semibold">Issue 关闭日历</h3><p class="mt-0.5 text-[12px] text-muted">每天关闭的 Issue 数；空白表示该日没有已归档记录或当前未覆盖</p></div><span class="text-[11px] text-muted">{{ issueViz?.complete && issueViz.coverage.state === 'complete' ? `${issueClosedDaily.length} 个窗口日期桶` : `${issueClosedDaily.length} 个有观察的日期` }}</span></div>
      <div v-if="issueVizLoading" class="flex h-[260px] items-center justify-center text-[12px] text-muted" role="status">正在读取关闭日期…</div>
      <div v-else-if="issueVizError" class="flex h-[260px] items-center justify-center text-[12px] text-danger" role="alert">{{ issueVizError }}</div>
      <CalendarHeatmap v-else-if="issueViz?.available && issueClosedDaily.length" :points="issueClosedDaily" :window-start="issueViz.windowStart" :window-end="issueViz.windowEnd" :height="250" metric-label="关闭 Issue" />
      <div v-else class="flex h-[260px] items-center justify-center text-center text-[12px] text-muted">暂无可用的 Issue 关闭日期样本</div>
      <p v-if="issueViz" class="m-0 text-[10.5px] text-muted">{{ issueViz.coverage.label }} · 已加载 {{ issueViz.items.length }} / {{ issueViz.total }} 条{{ issueViz.complete ? '' : '，日历仅覆盖当前样本' }}</p>
    </GdCard>
  </div>
</template>
