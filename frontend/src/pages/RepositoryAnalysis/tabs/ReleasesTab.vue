<script setup lang="ts">
import { computed, ref } from 'vue'
import ReleaseCadenceChart from '@/components/charts/ReleaseCadenceChart.vue'
import TimelineChart from '@/components/charts/TimelineChart.vue'
import DonutChart from '@/components/charts/DonutChart.vue'
import BoxPlotChart from '@/components/charts/BoxPlotChart.vue'
import G2Chart from '@/components/charts/G2Chart.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import type { RepositoryAnalysis } from '@/services/types'
import type { G2Spec } from '@antv/g2'
import { histogram } from '@/lib/chartAnalytics'
import { useReleaseDrawer } from '@/composables/useReleaseDrawer'

const props = defineProps<{ analysis: RepositoryAnalysis }>()
const { openRelease } = useReleaseDrawer(() => props.analysis.repository.id, () => props.analysis.provenance?.origin === 'course-test-events-v1')
const cadenceRange = ref<'year' | 'threeYears' | 'all'>('year')
const cadenceRanges = [
  { value: 'year' as const, label: '近 365 天' },
  { value: 'threeYears' as const, label: '近 3 年' },
  { value: 'all' as const, label: '全部已采集' },
]

const yearReleases = computed(() => props.analysis.releases)
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
  }))

  const formal = yearReleases.value.filter((release) => !release.prerelease).sort((a, b) => a.publishedAt.localeCompare(b.publishedAt))
  return formal.slice(1).map((release, index) => {
    const previous = formal[index]
    return {
      tag: release.tag, previousTag: previous.tag, date: release.publishedAt,
      days: release.intervalDays ?? Math.max(0, (Date.parse(release.publishedAt) - Date.parse(previous.publishedAt)) / 86400000),
      previousDate: previous.publishedAt,
    }
  })
})
const releaseWindowEnd = computed(() => {
  const metricsEnd = props.analysis.metrics.window.end
  if (metricsEnd) return Date.parse(metricsEnd)
  const latestRelease = yearReleases.value.map((release) => Date.parse(release.publishedAt)).filter(Number.isFinite).sort((a, b) => b - a)[0]
  return latestRelease ?? Date.parse(props.analysis.collectedAt ?? new Date().toISOString())
})
const recentFormalReleaseCount = computed(() => yearReleases.value.filter((release) => {
  const publishedAt = Date.parse(release.publishedAt)
  return !release.prerelease && Number.isFinite(publishedAt) && publishedAt >= releaseWindowEnd.value - 365 * 86400000 && publishedAt < releaseWindowEnd.value
}).length)
const cadenceItems = computed(() => {
  const days = cadenceRange.value === 'year' ? 365 : cadenceRange.value === 'threeYears' ? 365 * 3 : null
  const cutoff = days === null ? Number.NEGATIVE_INFINITY : releaseWindowEnd.value - days * 86400000
  return allCadenceItems.value.filter((item) => Date.parse(item.date) >= cutoff && Date.parse(item.date) < releaseWindowEnd.value)
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
const releaseTypeRows = computed(() => [
  ...(yearReleases.value.filter((release) => !release.prerelease).length ? [{ label: '正式版', value: yearReleases.value.filter((release) => !release.prerelease).length }] : []),
  ...(yearReleases.value.filter((release) => release.prerelease).length ? [{ label: '预发布版', value: yearReleases.value.filter((release) => release.prerelease).length }] : []),
])
const releaseIntervalHistogram = computed(() => histogram(cadenceValues.value, [
  { label: '≤ 7 天', max: 7 }, { label: '8–30 天', max: 30 }, { label: '31–90 天', max: 90 },
  { label: '91–180 天', max: 180 }, { label: '181–365 天', max: 365 }, { label: '> 365 天', max: Number.POSITIVE_INFINITY },
]))
const releaseIntervalSamples = computed(() => cadenceItems.value.map((item) => ({ group: '正式版间隔', value: item.days })))
const releaseHistogramSpec = computed<G2Spec>(() => ({
  type: 'interval', data: releaseIntervalHistogram.value,
  encode: { x: 'label', y: 'count' },
  style: { fill: '#5c8b91', fillOpacity: 0.82 },
  axis: { x: { labelFontSize: 9 }, y: { title: '间隔数量', gridLineDash: [3, 3] } },
  tooltip: { title: 'label', items: [{ field: 'count', name: '发布间隔数' }] },
}))

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
  <GdCard class="h-[360px] overflow-hidden" padding="sm" :gap="false">
    <div class="mb-1 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3 class="m-0 text-[15.5px] font-semibold">发布时间线</h3>
        <p class="mt-0.5 text-[12px] text-muted">按周、月或季度统计已采集的 Release · 日期范围默认近 90 天</p>
      </div>
    <span class="text-[11.5px] text-muted">近 365 天正式发布 {{ recentFormalReleaseCount }} 次</span>
    </div>
    <TimelineChart :releases="yearReleases" :height="220" />
    <div class="mt-1 flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted">
      <span>柱形按周、月或季度统计正式版与预发布版数量；采集不完整时，空档可能包含未采集的发布记录。</span>
      <span>具体版本与发布日期见下方记录表</span>
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
      <div v-else class="flex min-h-0 flex-1 items-center justify-center rounded-md bg-soft px-4 text-center text-[12px] text-muted">当前范围暂未形成可计算的正式发布间隔。</div>
      <p v-if="cadenceItems.length" class="mb-0 mt-1 text-[10.5px] text-muted">柱表示相邻已采集正式发布的天数间隔；采集不完整时区间可能跨过遗漏版本。点击柱查看 Release 说明。</p>
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

  <div class="grid gap-4 xl:grid-cols-3">
    <GdCard class="min-w-0" data-testid="release-type-donut-card">
      <div><h3 class="m-0 text-[15.5px] font-semibold">正式版与预发布版</h3><p class="mt-0.5 text-[12px] text-muted">当前本地可读取的 Release 类型构成</p></div>
      <DonutChart v-if="releaseTypeRows.length" :rows="releaseTypeRows" :total="yearReleases.length.toLocaleString('zh-CN')" center-label="Release" label="正式版与预发布版构成环形图" :height="270" />
      <div v-else class="flex h-[270px] items-center justify-center text-[12px] text-muted">暂无 Release 类型样本</div>
      <p class="m-0 text-[10.5px] text-muted">正式 {{ yearReleases.filter((release) => !release.prerelease).length }} 条 · 预发布 {{ yearReleases.filter((release) => release.prerelease).length }} 条 · {{ releaseCoverageNote }}</p>
    </GdCard>
    <GdCard class="min-w-0" data-testid="release-interval-histogram-card">
      <div><h3 class="m-0 text-[15.5px] font-semibold">发布间隔分布</h3><p class="mt-0.5 text-[12px] text-muted">相邻正式 Release 的间隔天数，按区间统计</p></div>
      <G2Chart v-if="cadenceValues.length" :spec="releaseHistogramSpec" label="正式 Release 间隔天数直方图" :height="270" />
      <div v-else class="flex h-[270px] items-center justify-center text-[12px] text-muted">暂无可计算的正式版间隔</div>
      <p class="m-0 text-[10.5px] text-muted">有效间隔 n={{ cadenceValues.length }} · P50 {{ median?.toLocaleString('zh-CN', { maximumFractionDigits: 1 }) ?? '—' }} 天。</p>
    </GdCard>
    <GdCard class="min-w-0" data-testid="release-interval-boxplot-card">
      <div><h3 class="m-0 text-[15.5px] font-semibold">发布间隔箱线图</h3><p class="mt-0.5 text-[12px] text-muted">整体正式版间隔分布；样本少于 5 时保留表格和统计值</p></div>
      <BoxPlotChart v-if="releaseIntervalSamples.length >= 5" :samples="releaseIntervalSamples" label="正式 Release 间隔箱线图" unit="间隔（天）" :height="270" />
      <div v-else class="flex h-[270px] items-center justify-center text-center text-[12px] text-muted">当前只有 {{ releaseIntervalSamples.length }} 个有效间隔；至少 5 个样本后显示箱线图。</div>
      <p class="m-0 text-[10.5px] text-muted">仅纳入有相邻发布时间的正式版间隔；未覆盖的版本间隔可能不完整。</p>
    </GdCard>
  </div>
</template>
