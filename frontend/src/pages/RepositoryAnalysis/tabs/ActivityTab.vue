<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AuthorConcentrationChart from '@/components/charts/AuthorConcentrationChart.vue'
import CalendarHeatmap from '@/components/charts/CalendarHeatmap.vue'
import TrendChart from '@/components/charts/TrendChart.vue'
import CommitAuthorStackChart from '@/components/charts/CommitAuthorStackChart.vue'
import ContributionBreakdown from '@/components/charts/ContributionBreakdown.vue'
import { coveredCommitPoints } from '@/components/charts/comboHelpers'
import KpiStrip from '@/components/common/KpiStrip.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import GdCoverageNote from '@/components/ui/GdCoverageNote.vue'
import GdInput from '@/components/ui/GdInput.vue'
import { useDataSource } from '@/composables/useDataSource'
import { dailyCoveragePoints } from '@/lib/chartAnalytics'
import { formatDate, formatTime } from '@/lib/format'
import type { CommitActivityPage, RepositoryAnalysis } from '@/services/types'

const props = defineProps<{ analysis: RepositoryAnalysis }>()
const emit = defineEmits<{ 'select-week': [payload: { date: string; count: number }] }>()
const source = useDataSource()
const pageSize = 10
const page = ref(1)
const searchInput = ref('')
const appliedSearch = ref('')
const activity = ref<CommitActivityPage | null>(null)
const loading = ref(false)
const loadError = ref('')
let requestVersion = 0

const weeklyPoints = computed(() => {
  const points = props.analysis.commits.series[0]?.points ?? []
  return props.analysis.chartData ? coveredCommitPoints(points, props.analysis.chartData.commitWeekly) : points
})
const pageCount = computed(() => Math.max(1, Math.ceil((activity.value?.total ?? 0) / pageSize)))
const firstRecord = computed(() => activity.value?.total ? (page.value - 1) * pageSize + 1 : 0)
const lastRecord = computed(() => Math.min(page.value * pageSize, activity.value?.total ?? 0))
const dailyPoints = computed(() => dailyCoveragePoints(
  activity.value?.dailyCounts ?? [],
  activity.value?.windowStart,
  activity.value?.windowEnd,
  activity.value?.coverage.state === 'complete',
))
const activeDays = computed(() => activity.value?.dailyCounts.length ?? 0)
const identifiedAuthors = computed(() => (activity.value?.authors ?? []).filter((author) => author.author !== '匿名作者' && author.author !== '未关联账号'))
const identifiedCommitCount = computed(() => (activity.value?.authorDistribution ?? []).reduce((sum, bucket) => sum + bucket.commits * bucket.authors, 0))
const contributorRows = computed(() => {
  const ranked = [...identifiedAuthors.value].sort((left, right) => right.commits - left.commits)
  const top = ranked.slice(0, 5).map((author) => ({ label: author.author, value: author.commits }))
  const topTotal = top.reduce((sum, row) => sum + row.value, 0)
  const other = Math.max(0, identifiedCommitCount.value - topTotal)
  const unidentified = activity.value?.unidentifiedCommitCount
  if (other > 0) top.push({ label: '其他已识别作者', value: other })
  if (unidentified !== null && unidentified !== undefined && unidentified > 0) top.push({ label: '身份未识别', value: unidentified })
  const colors = ['#356fc7', '#56a58c', '#d1a34a', '#9c78bd', '#ce7189', '#74828e', '#aeb6bd']
  return top.map((row, index) => ({ ...row, color: colors[index % colors.length] }))
})
const botRows = computed(() => {
  const bot = identifiedAuthors.value.filter((author) => author.isBot === true).reduce((sum, author) => sum + author.commits, 0)
  const human = identifiedAuthors.value.filter((author) => author.isBot === false).reduce((sum, author) => sum + author.commits, 0)
  const total = activity.value?.commitCount ?? 0
  const unclassified = Math.max(0, total - bot - human)
  return [
    { label: 'Bot', value: bot, color: '#9c78bd' },
    { label: '人工账号', value: human, color: '#356fc7' },
    { label: '长尾/未知类型', value: unclassified, color: '#74828e' },
  ]
})
const contributorTotal = computed(() => contributorRows.value.reduce((sum, row) => sum + row.value, 0))
const botTotal = computed(() => activity.value?.commitCount ?? 0)

async function loadActivity() {
  const version = ++requestVersion
  loading.value = true
  loadError.value = ''
  try {
    const result = await source.getCommitActivity(props.analysis.repository.id, page.value, pageSize, appliedSearch.value, undefined, props.analysis.windowAvailability.requestedDays)
    if (version === requestVersion) activity.value = result
  } catch (cause) {
    if (version === requestVersion) {
      activity.value = null
      loadError.value = cause instanceof Error ? cause.message : 'Commit 活动明细加载失败'
    }
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

watch([() => props.analysis.repository.id, () => props.analysis.windowAvailability.requestedDays], () => {
  page.value = 1
  activity.value = null
}, { flush: 'sync' })
watch([() => props.analysis.repository.id, () => props.analysis.windowAvailability.requestedDays, page, appliedSearch], () => { void loadActivity() }, { immediate: true })

function selectWeek(dataIndex: number) {
  const point = weeklyPoints.value[dataIndex]
  if (point && (point.value !== null || point.observedValue !== null && point.observedValue !== undefined)) {
    emit('select-week', { date: point.date, count: point.value ?? point.observedValue ?? 0 })
  }
}

function applySearch() {
  const next = searchInput.value.trim()
  if (page.value === 1 && appliedSearch.value === next) {
    void loadActivity()
    return
  }
  page.value = 1
  appliedSearch.value = next
}

function filterAuthor(author: string) {
  searchInput.value = author
  if (page.value !== 1) page.value = 1
  appliedSearch.value = author
}

</script>

<template>
  <KpiStrip :metrics="analysis.metrics.metrics" />

  <GdCard>
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h3 class="m-0 text-[15.5px] font-semibold">Commit 周趋势</h3>
        <p class="mt-0.5 text-[12px] text-muted">默认分支 · SHA 去重 · UTC · {{ analysis.commits.window.start ?? '—' }} 至 {{ analysis.commits.window.end ?? '—' }}</p>
      </div>
      <GdCoverageNote :coverage="analysis.commits.coverage" />
    </div>
    <CommitAuthorStackChart v-if="analysis.chartData" :points="weeklyPoints" :data="analysis.chartData" :height="260" @select="selectWeek" />
    <TrendChart v-else :points="weeklyPoints" :unit="analysis.commits.unit" :height="260" :moving-average-window="4" @select="(payload) => selectWeek(payload.dataIndex)" />
    <div class="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted">
      <span v-if="analysis.chartData">堆叠面积显示前 5 个 GitHub 账号及其他、未关联账号；半透明表示部分覆盖。折线只统计连续 4 个完整周 · 有效样本 {{ analysis.commits.sampleSize?.toLocaleString('en-US') ?? '—' }}。</span>
      <span v-else>当前数据未提供作者贡献构成，显示每周提交数及完整 4 周均值。</span>
      <span>点击周趋势点，可查看该周已采集的逐条 Commit。</span>
    </div>
  </GdCard>

  <div class="grid gap-4 lg:grid-cols-2">
    <GdCard class="min-h-[460px]" data-testid="commit-heatmap-card">
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">每日提交热力图</h3>
          <p class="mt-0.5 text-[12px] text-muted">UTC · 设置每日 Commit 数范围突出对应日期；未命中数据会淡化，灰格也可能表示无归档提交</p>
        </div>
        <span class="shrink-0 text-[11px] text-muted">{{ activity?.commitCount.toLocaleString('zh-CN') ?? '—' }} 条 · {{ activeDays }} 个有记录日期</span>
      </div>
      <GdCoverageNote v-if="activity" :coverage="activity.coverage" compact />
      <div v-if="loading && !activity" class="flex min-h-0 flex-1 items-center justify-center text-[12px] text-muted" role="status">正在读取本地 Commit 归档…</div>
      <div v-else-if="loadError" class="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 text-center text-[12px] text-danger" role="alert">
        <span>{{ loadError }}</span>
        <GdButton variant="outline" size="sm" @click="loadActivity">重新加载</GdButton>
      </div>
      <div v-else-if="activity && !activity.available" class="flex min-h-0 flex-1 items-center justify-center rounded-md bg-soft px-4 text-center text-[12px] leading-relaxed text-muted">{{ activity.note }}</div>
      <div v-else-if="activity && !activity.dailyCounts.length && (!activity.windowStart || !activity.windowEnd)" class="flex min-h-0 flex-1 items-center justify-center rounded-md bg-soft px-4 text-center text-[12px] text-muted">本次采集范围内没有可展示的逐条 Commit。</div>
      <CalendarHeatmap v-else-if="activity" :points="dailyPoints" :window-start="activity.windowStart" :window-end="activity.windowEnd" :height="260" />
      <p v-if="activity?.note" class="m-0 text-[10.5px] leading-relaxed text-muted">{{ activity.note }}</p>
    </GdCard>

    <GdCard class="h-[500px] min-h-0 overflow-hidden" data-testid="author-concentration-card">
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">作者贡献集中度</h3>
          <p class="mt-0.5 text-[12px] text-muted">比较归档提交在可识别作者之间的分布</p>
        </div>
        <GdCoverageNote v-if="activity" :coverage="activity.coverage" compact />
      </div>
      <AuthorConcentrationChart v-if="activity && identifiedAuthors.length" class="min-h-0 flex-1" :authors="identifiedAuthors" :distribution="activity.authorDistribution" :total-commits="activity.commitCount" :unidentified-commit-count="activity.unidentifiedCommitCount" @select-author="filterAuthor" />
      <div v-else-if="loading" class="flex min-h-0 flex-1 items-center justify-center text-[12px] text-muted" role="status">正在计算作者贡献…</div>
      <div v-else-if="loadError" class="flex min-h-0 flex-1 items-center justify-center text-center text-[12px] text-danger" role="alert">{{ loadError }}</div>
      <div v-else class="flex min-h-0 flex-1 items-center justify-center rounded-md bg-soft px-4 text-center text-[12px] text-muted">当前没有可识别的作者记录。</div>
      <p v-if="activity?.available && identifiedAuthors.length" class="m-0 text-[10.5px] leading-relaxed text-muted">{{ analysis.provenance?.origin === 'course-test-events-v1' ? '历史快照中的账号已匿名化，Bot 类型未知。' : '含 Bot；未关联账号按 Git 名称归并。' }}{{ activity.unidentifiedCommitCount === null ? '身份缺失数未知。' : `身份无法识别的 ${activity.unidentifiedCommitCount} 条提交未计入集中度。` }}点击排行可搜索明细。</p>
    </GdCard>
  </div>

  <div class="grid gap-4 lg:grid-cols-2">
    <GdCard class="min-w-0" data-testid="contributor-composition-card">
      <div class="flex items-start justify-between gap-3"><div><h3 class="m-0 text-[15.5px] font-semibold">贡献者构成</h3><p class="mt-0.5 text-[12px] text-muted">前五位作者、其他已识别作者与身份未识别提交</p></div><GdCoverageNote v-if="activity" :coverage="activity.coverage" compact /></div>
      <ContributionBreakdown v-if="contributorRows.length" :rows="contributorRows" :total="contributorTotal" mode="ranked" label="贡献者提交数量与占比" />
      <div v-else class="flex h-[180px] items-center justify-center text-[12px] text-muted">{{ loading ? '正在读取作者记录…' : '暂无贡献者样本' }}</div>
      <p class="m-0 text-[10.5px] leading-relaxed text-muted">实际样本 {{ contributorTotal.toLocaleString('zh-CN') }} 条。{{ activity?.unidentifiedCommitCount === null ? '身份未识别数量未知，当前仅统计已识别作者分布。' : '作者长尾已合并，未识别身份单独列出。' }}</p>
    </GdCard>
    <GdCard class="min-w-0" data-testid="bot-contribution-card">
      <div class="flex items-start justify-between gap-3"><div><h3 class="m-0 text-[15.5px] font-semibold">Bot 与人工提交</h3><p class="mt-0.5 text-[12px] text-muted">按作者 Bot 标记汇总数量与占比</p></div><GdCoverageNote v-if="activity" :coverage="activity.coverage" compact /></div>
      <ContributionBreakdown v-if="activity?.available && botTotal > 0" class="flex-1" :rows="botRows" :total="botTotal" mode="summary" label="Bot、人工账号、长尾或类型未知的提交数量" />
      <div v-else class="flex min-h-[180px] flex-1 items-center justify-center text-[12px] text-muted">{{ loading ? '正在读取作者类型…' : '暂无作者类型样本' }}</div>
      <p class="m-0 text-[10.5px] leading-relaxed text-muted">{{ activity?.unidentifiedCommitCount === null ? '身份无法识别的提交数量未知。' : `${activity?.unidentifiedCommitCount ?? 0} 条身份未识别提交已归入未知。` }}未知 Bot 类型未归为人工账号。</p>
    </GdCard>
  </div>

  <GdCard class="h-[500px] min-h-0 overflow-hidden">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex min-w-0 items-center gap-2">
        <h3 class="m-0 text-[15.5px] font-semibold">Commit 逐条记录</h3>
        <GdCoverageNote v-if="activity" :coverage="activity.coverage" compact />
      </div>
      <span v-if="activity?.available" class="shrink-0 text-[11px] text-muted">{{ formatDate(activity.windowStart) }} 至 {{ formatDate(activity.windowEnd) }} · {{ activity.commitCount.toLocaleString('zh-CN') }} 条</span>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <GdInput v-model="searchInput" size="sm" class="min-w-[220px] flex-1" placeholder="搜索提交说明、作者或 SHA" @enter="applySearch" />
      <GdButton variant="outline" size="sm" :disabled="loading" @click="applySearch">搜索</GdButton>
      <span v-if="activity?.available" class="shrink-0 text-[11px] text-muted">匹配 {{ activity.total.toLocaleString('zh-CN') }} 条</span>
    </div>

    <p v-if="activity?.note" class="m-0 text-[11px] leading-relaxed text-muted">{{ activity.note }}</p>

    <div v-if="loading && !activity" class="min-h-0 flex-1 overflow-y-auto py-8 text-center text-[12px] text-muted" role="status">正在加载 Commit 记录…</div>
    <div v-else-if="loadError" class="min-h-0 flex-1 overflow-y-auto py-6 text-center text-[12px] text-danger" role="alert">
      <p class="mb-3">{{ loadError }}</p>
      <GdButton variant="outline" size="sm" @click="loadActivity">重新加载</GdButton>
    </div>
    <div v-else-if="activity && !activity.available" class="min-h-0 flex-1 overflow-y-auto rounded-md bg-soft px-3 py-8 text-center text-[12px] leading-relaxed text-muted">{{ activity.note }}</div>
    <div v-else-if="activity && activity.total === 0" class="min-h-0 flex-1 overflow-y-auto rounded-md bg-soft px-3 py-8 text-center text-[12px] text-muted">{{ appliedSearch ? '没有找到匹配的 Commit。' : '本次采集窗口内没有 Commit 记录。' }}</div>
    <div v-else class="min-h-0 flex-1 overflow-auto overscroll-contain">
      <table class="w-full min-w-[640px] table-fixed border-collapse text-[12px]">
        <thead class="sticky top-0 z-10 bg-panel">
          <tr class="text-left text-[11px] text-muted">
            <th class="w-[110px] border-b border-line px-2 pb-2 font-medium">提交</th>
            <th class="border-b border-line px-2 pb-2 font-medium">提交说明</th>
            <th class="w-[150px] border-b border-line px-2 pb-2 font-medium">作者</th>
            <th class="w-[142px] border-b border-line px-2 pb-2 font-medium">提交时间（UTC）</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in activity?.items" :key="item.sha" class="border-b border-line/70 last:border-0">
            <td class="whitespace-nowrap px-2 py-2.5 font-mono text-ink">
              <a v-if="item.url" :href="item.url" target="_blank" rel="noreferrer" class="underline decoration-line underline-offset-2 hover:decoration-ink">{{ item.sha.slice(0, 8) }}</a>
              <span v-else>{{ item.sha.slice(0, 8) }}</span>
            </td>
            <td class="px-2 py-2.5 text-ink" :title="item.title"><span class="line-clamp-2">{{ item.title }}</span></td>
            <td class="px-2 py-2.5 text-ink">
              <span class="block truncate" :title="item.author">{{ item.author }}</span>
              <span v-if="item.isBot" class="text-[10px] text-muted">Bot</span>
              <span v-else-if="item.anonymous" class="text-[10px] text-muted">未关联账号</span>
            </td>
            <td class="whitespace-nowrap px-2 py-2.5 font-mono text-[10.5px] text-ink">
              <span class="block">{{ formatDate(item.date) }}</span>
              <span class="block text-[10px] text-ink/70">{{ formatTime(item.date) }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="activity?.available && activity.total > 0" class="flex shrink-0 items-center justify-between gap-2 border-t border-line pt-2 text-[11px] text-muted">
      <span>显示 {{ firstRecord }}–{{ lastRecord }} / {{ activity.total }}</span>
      <div class="flex items-center gap-2">
        <GdButton variant="outline" size="sm" :disabled="loading || page <= 1" @click="page -= 1">上一页</GdButton>
        <span class="font-mono">{{ page }} / {{ pageCount }}</span>
        <GdButton variant="outline" size="sm" :disabled="loading || page >= pageCount" @click="page += 1">下一页</GdButton>
      </div>
    </div>
  </GdCard>
</template>
