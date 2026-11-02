<script setup lang="ts">
import { computed, ref } from 'vue'
import ReleaseCadenceChart from '@/components/charts/ReleaseCadenceChart.vue'
import TimelineChart from '@/components/charts/TimelineChart.vue'
import { coveredCommitPoints } from '@/components/charts/comboHelpers'
import KpiStrip from '@/components/common/KpiStrip.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import type { RepositoryAnalysis } from '@/services/types'
import { useReleaseDrawer } from '@/composables/useReleaseDrawer'

const props = defineProps<{ analysis: RepositoryAnalysis }>()
const { openRelease } = useReleaseDrawer(() => props.analysis.repository.id)
const cadenceRange = ref<'year' | 'threeYears' | 'all'>('year')
const cadenceRanges = [
  { value: 'year' as const, label: '近 365 天' },
  { value: 'threeYears' as const, label: '近 3 年' },
  { value: 'all' as const, label: '全部已采集' },
]

const yearReleases = computed(() => props.analysis.releases)
const commitPoints = computed(() => {
  const points = props.analysis.commits.series[0]?.points ?? []
  return props.analysis.chartData ? coveredCommitPoints(points, props.analysis.chartData.commitWeekly) : points
})
const releaseHistory = computed(() => {
  const saved = props.analysis.chartData?.releaseHistory ?? []
  if (saved.length) return saved
  return yearReleases.value.filter((release) => !release.prerelease).map((release) => ({
    id: release.tag, publishedAt: release.publishedAt, identifierType: release.identifierType ?? 'tag',
  }))
})
const allCadenceItems = computed(() => {
  const chartIntervals = props.analysis.chartData?.releaseIntervals ?? []
  if (chartIntervals.length) return chartIntervals.map((interval) => ({
    tag: interval.id,
    previousTag: interval.previousId,
    date: interval.publishedAt,
    days: interval.days,
    previousDate: interval.previousPublishedAt,
    commitCount: interval.commitCount,
    reason: interval.reason,
  }))

  const formal = yearReleases.value.filter((release) => !release.prerelease).sort((a, b) => a.publishedAt.localeCompare(b.publishedAt))
  return formal.slice(1).map((release, index) => {
    const previous = formal[index]
    return {
      tag: release.tag, previousTag: previous.tag, date: release.publishedAt,
      days: release.intervalDays ?? Math.max(0, (Date.parse(release.publishedAt) - Date.parse(previous.publishedAt)) / 86400000),
      previousDate: previous.publishedAt, commitCount: null, reason: 'Commit 未完整覆盖此发布间隔',
    }
  })
})
const cadenceEnd = computed(() => Date.parse(props.analysis.commits.window.endUtc ?? props.analysis.metrics.window.end ?? props.analysis.collectedAt ?? new Date().toISOString()))
const cadenceItems = computed(() => {
  const days = cadenceRange.value === 'year' ? 365 : cadenceRange.value === 'threeYears' ? 365 * 3 : null
  const cutoff = days === null ? Number.NEGATIVE_INFINITY : cadenceEnd.value - days * 86400000
  return allCadenceItems.value.filter((item) => Date.parse(item.date) >= cutoff && Date.parse(item.date) < cadenceEnd.value)
})
const identifierLabel = computed(() => yearReleases.value[0]?.identifierType === 'release_id' ? 'Release ID' : '版本')
const sorted = computed(() => [...yearReleases.value].sort((a, b) => +new Date(b.publishedAt) - +new Date(a.publishedAt)))
const cadenceValues = computed(() => cadenceItems.value.map((item) => item.days).sort((a, b) => a - b))
const median = computed(() => {
  const days = cadenceValues.value
  if (!days.length) return null
  const middle = Math.floor(days.length / 2)
  return days.length % 2 ? days[middle] : (days[middle - 1] + days[middle]) / 2
})
const releaseSpan = computed(() => {
  if (!releaseHistory.value.length) return ''
  const dates = releaseHistory.value.map((release) => release.publishedAt).sort()
  return `${dates[0].slice(0, 10)} 至 ${dates[dates.length - 1].slice(0, 10)}`
})
const releaseCoverageNote = computed(() => {
  const state = props.analysis.chartData?.releaseHistoryCoverage
  if (state === 'complete') return '本次 Release 分页采集已完成；更早历史以本地保存记录为准'
  if (state === 'partial') return 'Release 采集不完整，间隔可能跨过未采集版本'
  return '仅展示当前本地可读取的 Release'
})
const hasCommitCounts = computed(() => cadenceItems.value.some((item) => item.commitCount !== null))

function openReleaseByTag(tag: string) {
  const release = yearReleases.value.find((item) => item.tag === tag)
  if (release) {
    void openRelease(release)
    return
  }
  const saved = releaseHistory.value.find((item) => item.id === tag)
  if (saved) void openRelease({
    tag: saved.id, identifierType: saved.identifierType, publishedAt: saved.publishedAt,
    prerelease: false, intervalDays: null, note: '已采集的正式发布记录',
  })
}

</script>

<template>
  <KpiStrip :metrics="analysis.metrics.metrics" />

  <GdCard class="h-[360px] overflow-hidden">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3 class="m-0 text-[15.5px] font-semibold">发布时间线</h3>
        <p class="mt-0.5 text-[12px] text-muted">提交活动面积与 Release 标记 · 默认显示最近 90 天 · 滑块浏览近 365 天</p>
      </div>
    <span class="text-[11.5px] text-muted">正式发布 {{ yearReleases.length }} 次</span>
    </div>
    <TimelineChart :releases="yearReleases" :commits="commitPoints" :height="220" @select="openRelease" />
    <div class="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted">
      <span>Release 显示近 365 天；标记纵向位置不代表提交数。提交仅显示当前分析窗口的周数据，空白不代表没有提交。</span>
      <span>点击圆点或下方记录查看 Release 详情</span>
    </div>
  </GdCard>

  <div class="grid gap-4 lg:grid-cols-[1fr_1.1fr]">
    <GdCard class="h-[420px] min-h-0 overflow-hidden" :gap="false">
      <div class="mb-2 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">相邻发布间隔</h3>
          <p class="mt-0.5 text-[12px] text-muted">按已采集正式 Release 排序 · 柱顶显示间隔天数</p>
        </div>
        <div class="text-right">
          <div class="font-mono text-[11.5px] text-ink">n={{ cadenceItems.length }} · P50 {{ median?.toLocaleString('en-US', { maximumFractionDigits: 1 }) ?? '—' }} 天</div>
          <div v-if="cadenceValues.length" class="mt-0.5 text-[10.5px] text-muted">范围 {{ cadenceValues[0].toLocaleString('en-US', { maximumFractionDigits: 1 }) }}–{{ cadenceValues[cadenceValues.length - 1].toLocaleString('en-US', { maximumFractionDigits: 1 }) }} 天</div>
        </div>
      </div>
      <div class="mb-1.5 flex flex-wrap items-center justify-between gap-2">
        <div class="flex items-center gap-1" role="group" aria-label="发布间隔时间范围">
          <GdButton v-for="option in cadenceRanges" :key="option.value" size="sm" :variant="cadenceRange === option.value ? 'primary' : 'outline'" :aria-pressed="cadenceRange === option.value" @click="cadenceRange = option.value">{{ option.label }}</GdButton>
        </div>
        <span class="text-[10.5px] text-muted">本地 Release：{{ releaseSpan || '暂无' }}<span v-if="cadenceItems.length > 0 && cadenceItems.length < 5" class="ml-2 rounded bg-warnbg px-1.5 py-0.5 text-warnfg">样本较少</span></span>
      </div>
      <ReleaseCadenceChart v-if="cadenceItems.length" :items="cadenceItems" :height="235" @select="openReleaseByTag" />
      <div v-else class="flex min-h-0 flex-1 items-center justify-center rounded-md bg-soft px-4 text-center text-[12px] text-muted">相邻间隔至少需要 2 次正式发布；当前范围没有可比较的连续版本。</div>
      <p v-if="cadenceItems.length && !hasCommitCounts" class="mb-0 mt-1 text-[10.5px] text-warnfg">当前没有 Commit 完整覆盖这些发布间隔的数据；提交数不可比较，不代表 0。</p>
      <p v-else class="mb-0 mt-1 text-[10.5px] text-muted">横轴为前版日期 → 新版日期；间隔按本地已采集记录计算，采集不完整时可能跨过遗漏版本。折线只显示 Commit 覆盖完整的区间，点击柱查看新版说明。</p>
      <p class="mb-0 mt-1 text-[10px] text-muted">{{ releaseCoverageNote }}；“全部已采集”不代表 GitHub 全历史。</p>
    </GdCard>

    <GdCard class="h-[420px] overflow-hidden">
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">发布记录</h3>
          <p class="mt-0.5 text-[12px] text-muted">点击行查看 Release 详情</p>
        </div>
      </div>
      <div class="min-h-0 flex-1 overflow-auto overscroll-contain">
        <table class="w-full min-w-[560px] border-collapse text-[12.5px]">
          <thead class="sticky top-0 z-10 bg-panel">
            <tr class="text-left text-[11.5px] text-muted">
              <th class="border-b border-line px-2.5 pb-2 font-medium">{{ identifierLabel }}</th>
              <th class="border-b border-line px-2.5 pb-2 font-medium">发布时间</th>
              <th class="border-b border-line px-2.5 pb-2 font-medium">类型</th>
              <th class="border-b border-line px-2.5 pb-2 font-medium">间隔</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="release in sorted" :key="release.tag" class="cursor-pointer hover:bg-soft/40" @click="openRelease(release)">
              <td class="border-b border-line px-2.5 py-2.5 font-mono">
                <button type="button" class="text-left hover:underline focus-visible:underline" @click.stop="openRelease(release)">{{ release.identifierType === 'release_id' ? `#${release.tag}` : release.tag }}</button>
              </td>
              <td class="border-b border-line px-2.5 py-2.5 font-mono text-muted">{{ release.publishedAt.slice(0, 10) }}</td>
              <td class="border-b border-line px-2.5 py-2.5">{{ release.prerelease ? '预发布' : '正式' }}</td>
              <td class="border-b border-line px-2.5 py-2.5 font-mono">{{ release.intervalDays === null ? '—' : `${release.intervalDays.toLocaleString('en-US', { maximumFractionDigits: 1 })} 天` }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </GdCard>
  </div>
</template>
