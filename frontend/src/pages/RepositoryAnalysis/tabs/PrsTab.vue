<script setup lang="ts">
import { ref } from 'vue'
import GroupedChart from '@/components/charts/GroupedChart.vue'
import HistogramChart from '@/components/charts/HistogramChart.vue'
import PrMergeTrendChart from '@/components/charts/PrMergeTrendChart.vue'
import PrMonthlyDurationChart from '@/components/charts/PrMonthlyDurationChart.vue'
import KpiStrip from '@/components/common/KpiStrip.vue'
import GdBadge from '@/components/ui/GdBadge.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import GdCoverageNote from '@/components/ui/GdCoverageNote.vue'
import GdInput from '@/components/ui/GdInput.vue'
import { useDataSource } from '@/composables/useDataSource'
import { usePagedRecords } from '@/composables/usePagedRecords'
import { downloadBlob } from '@/lib/download'
import { formatDate, formatDuration, formatTime } from '@/lib/format'
import type { PullRequestActivityPage, PullRequestActivityRecord, RepositoryAnalysis } from '@/services/types'
import { useUiStore } from '@/stores/ui'

const props = defineProps<{ analysis: RepositoryAnalysis }>()
const ui = useUiStore()
const source = useDataSource()
const { page, searchInput, appliedSearch, records, loading, loadError, pageCount, firstRecord, lastRecord, loadRecords, applySearch } = usePagedRecords<PullRequestActivityPage>(
  () => props.analysis.repository.id,
  (id, page, perPage, search) => source.getPullRequestRecords(id, page, perPage, search),
  'Pull Request 记录加载失败',
)
const exporting = ref(false)
let detailRequest = 0

async function openPullRequest(item: PullRequestActivityRecord) {
  const requestId = ++detailRequest
  const payload = {
    repositoryId: props.analysis.repository.id,
    number: String(item.number),
    title: item.title,
    createdAt: item.createdAt ?? '',
    closedAt: item.closedAt ?? '',
    mergedAt: item.mergedAt ?? '',
    durationDays: formatDuration(item.durationDays),
    commentsCount: String(item.commentsCount),
    state: item.state,
    draft: String(item.draft),
    url: item.url ?? '',
    onlineStatus: 'idle',
    bodyStatus: 'loading',
  }
  ui.openDrawer('pr', payload)
  try {
    const detail = await source.getPullRequestDetail(props.analysis.repository.id, item.number)
    if (requestId !== detailRequest || ui.drawerKind !== 'pr' || ui.drawerPayload?.number !== String(item.number)) return
    if (ui.drawerPayload?.onlineStatus === 'loading' || ui.drawerPayload?.onlineStatus === 'ready') return
    ui.openDrawer('pr', { ...payload, bodyStatus: 'ready', body: detail.body ?? '', commentsCount: String(detail.commentsCount) })
  } catch (cause) {
    if (requestId !== detailRequest || ui.drawerKind !== 'pr' || ui.drawerPayload?.number !== String(item.number)) return
    ui.openDrawer('pr', { ...payload, bodyStatus: 'error', bodyError: cause instanceof Error ? cause.message : '无法读取该 Pull Request 的详细内容' })
  }
}

async function exportCsv() {
  exporting.value = true
  try {
    downloadBlob(await source.exportPullRequestRecords(props.analysis.repository.id, appliedSearch.value), `${props.analysis.repository.id}-pull-requests.csv`)
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '导出 Pull Request 记录失败', 'error')
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
        <h3 class="m-0 text-[15.5px] font-semibold">PR 合并趋势</h3>
        <p class="mt-0.5 text-[12px] text-muted">按 merged_at 所在自然周统计 · 不代表合并率</p>
      </div>
      <GdCoverageNote :coverage="analysis.pullRequests.coverage" />
    </div>
    <PrMergeTrendChart v-if="analysis.chartData" :points="analysis.pullRequests.series.find((series) => series.key === 'merged')?.points ?? []" :data="analysis.chartData" :duration-p90="analysis.prDuration.percentiles.p90" :height="270" />
    <GroupedChart v-else :series="analysis.pullRequests.series" :unit="analysis.pullRequests.unit" :colors="['#2E8FCB']" :height="250" />
    <p v-if="analysis.chartData" class="text-[11px] text-muted">柱为每周合并数，圆点为单条 PR 耗时，折线为每周中位耗时；耗时轴随当前时间窗口缩放，超过全窗口 P90 的长尾以三角标记，悬浮仍显示真实耗时。窗口只筛选显示范围，柱和中位数仍按 UTC 自然周聚合。覆盖不完整时仅显示已观察样本。<template v-if="analysis.chartData.prSamplesTruncated"> 散点展示 {{ analysis.chartData.prSamples.length }} / {{ analysis.chartData.prSampleTotal }} 条；P90 阈值和周中位数使用全部有效样本。</template></p>
    <p v-else class="text-[11px] text-muted">当前数据未提供逐条耗时，显示已采集的每周合并数量。</p>
  </GdCard>

  <div class="grid gap-4 lg:grid-cols-[1.15fr_1fr]">
    <GdCard class="h-[420px] min-h-0 overflow-hidden">
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">{{ analysis.chartData ? '月度合并耗时分布' : '合并耗时分布' }}</h3>
          <p class="mt-0.5 text-[12px] text-muted">{{ analysis.chartData ? '堆叠柱为各耗时区间样本数 · 菱形为中位耗时' : '柱为区间样本数 · 折线为累计占比' }}</p>
        </div>
        <span class="font-mono text-[11.5px] text-muted">n={{ analysis.prDuration.sampleSize }}</span>
      </div>
      <PrMonthlyDurationChart v-if="analysis.chartData" :months="analysis.chartData.prMonthly" :height="200" class="min-h-[200px] flex-1 w-full" />
      <HistogramChart v-else :buckets="analysis.prDuration.buckets" color="#CE3F7C" unit="个 PR" :height="200" class="min-h-[200px] flex-1 w-full" />
      <div class="text-[11px] text-muted"><template v-if="analysis.chartData">半透明柱表示该月仅观察到部分样本。</template> 整体 P50 {{ analysis.prDuration.percentiles.p50 ?? '—' }} 天 · P90 {{ analysis.prDuration.percentiles.p90 ?? '—' }} 天</div>
      <p v-if="analysis.prDuration.note" class="mt-2 text-[11px] text-warnfg">{{ analysis.prDuration.note }}</p>
    </GdCard>

    <GdCard class="h-[420px] min-h-0 overflow-hidden">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex min-w-0 items-center gap-2">
          <h3 class="m-0 text-[15.5px] font-semibold">PR 逐条记录</h3>
          <GdCoverageNote v-if="records" :coverage="records.coverage" compact />
        </div>
        <GdButton variant="outline" size="sm" :disabled="exporting || loading || !records?.available" @click="exportCsv">{{ exporting ? '导出中…' : '导出 PR CSV' }}</GdButton>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <GdInput v-model="searchInput" size="sm" class="min-w-[190px] flex-1" placeholder="搜索 PR 编号或标题" @enter="applySearch" />
        <GdButton variant="outline" size="sm" :disabled="loading" @click="applySearch">搜索</GdButton>
        <span v-if="records?.available" class="shrink-0 text-[11px] text-muted">{{ records.total.toLocaleString('zh-CN') }} 条 · {{ formatDate(records.windowStart) }} 至 {{ formatDate(records.windowEnd) }}</span>
      </div>

      <p v-if="records?.note" class="m-0 text-[11px] leading-relaxed text-muted">{{ records.note }}</p>

      <div v-if="loading" class="min-h-0 flex-1 overflow-y-auto py-8 text-center text-[12px] text-muted" role="status">正在加载 PR 记录…</div>
      <div v-else-if="loadError" class="min-h-0 flex-1 overflow-y-auto py-6 text-center text-[12px] text-danger">
        <p class="mb-3">{{ loadError }}</p>
        <GdButton variant="outline" size="sm" @click="loadRecords">重新加载</GdButton>
      </div>
      <div v-else-if="records && !records.available" class="min-h-0 flex-1 overflow-y-auto rounded-md bg-soft px-3 py-8 text-center text-[12px] leading-relaxed text-muted">{{ records.note }}</div>
      <div v-else-if="records && records.total === 0" class="min-h-0 flex-1 overflow-y-auto rounded-md bg-soft px-3 py-8 text-center text-[12px] text-muted">{{ appliedSearch ? '没有找到匹配的 PR。' : '本次采集窗口内没有已关闭的 PR。' }}</div>
      <div v-else class="min-h-0 flex-1 overflow-auto overscroll-contain">
        <table class="w-full min-w-[560px] table-fixed border-collapse text-[12px]">
          <thead class="sticky top-0 z-10 bg-panel">
            <tr class="text-left text-[11px] text-muted">
              <th class="w-[48px] border-b border-line px-1.5 pb-2 font-medium">编号</th>
              <th class="w-[170px] border-b border-line px-1.5 pb-2 font-medium">标题</th>
              <th class="w-[84px] border-b border-line px-1.5 pb-2 font-medium">状态</th>
              <th class="w-[82px] border-b border-line px-1.5 pb-2 font-medium">创建时间</th>
              <th class="w-[82px] border-b border-line px-1.5 pb-2 font-medium">合并/关闭</th>
              <th class="w-[48px] border-b border-line px-1.5 pb-2 text-right font-medium">评论</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in records?.items" :key="item.number" class="border-b border-line/70 last:border-0">
              <td class="whitespace-nowrap px-1.5 py-2.5 font-mono text-ink">
                <button type="button" class="underline decoration-line underline-offset-2 hover:decoration-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2" @click="openPullRequest(item)">#{{ item.number }}</button>
              </td>
              <td class="px-1.5 py-2.5 text-ink" :title="item.title"><button type="button" class="line-clamp-2 text-left hover:underline focus-visible:underline" @click="openPullRequest(item)">{{ item.title }}</button><span v-if="item.draft" class="text-[10px] text-muted">草稿</span></td>
              <td class="whitespace-nowrap px-1.5 py-2.5"><GdBadge :variant="item.state === 'merged' ? 'default' : 'warn'">{{ item.state === 'merged' ? '已合并' : '关闭未合并' }}</GdBadge></td>
              <td class="whitespace-nowrap px-1.5 py-2 font-mono text-[10.5px] text-ink"><span>{{ formatDate(item.createdAt) }}</span><span class="block text-[9px] leading-3 text-ink/70">{{ formatTime(item.createdAt) }}</span></td>
              <td class="whitespace-nowrap px-1.5 py-2 font-mono text-[10.5px] text-ink"><span>{{ formatDate(item.mergedAt ?? item.closedAt) }}</span><span class="block text-[9px] leading-3 text-ink/70">{{ formatTime(item.mergedAt ?? item.closedAt) }}</span></td>
              <td class="whitespace-nowrap px-1.5 py-2.5 text-right text-[11px] text-ink">{{ item.commentsCount }}</td>
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
</template>
