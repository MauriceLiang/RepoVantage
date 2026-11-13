<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import GdCard from '@/components/ui/GdCard.vue'
import EChart from '@/components/charts/EChart.vue'
import { chartTheme, fontFamily } from '@/components/charts/theme'
import type { RepositoryDashboardData, RepositorySummary } from '@/services/types'
import { useUiStore } from '@/stores/ui'

const props = defineProps<{
  repositories: RepositorySummary[]
  dashboard: RepositoryDashboardData
}>()

const ui = useUiStore()
const languageGroups = computed(() => [...(props.dashboard.courseLanguageGroups ?? [])]
  .sort((left, right) => right.repositoryCount - left.repositoryCount || left.language.localeCompare(right.language)))
const courseRepositories = computed(() => {
  const libraryProfiles = new Map(props.repositories.map((repo) => [repo.id, repo]))
  return (props.dashboard.courseRepositories ?? []).map((repo) => {
    const profile = libraryProfiles.get(repo.repositoryId)
    return {
      ...repo,
      stars: repo.stars ?? profile?.stars ?? null,
      forks: repo.forks ?? profile?.forks ?? null,
      createdAt: repo.createdAt ?? profile?.createdAt ?? null,
    }
  })
})
const dataAsOf = computed(() => {
  const value = props.dashboard.courseSummary?.dataAsOf
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? value.slice(0, 10) : new Intl.DateTimeFormat('zh-CN', { timeZone: 'UTC', year: 'numeric', month: '2-digit', day: '2-digit' }).format(date)
})
const validStars = computed(() => courseRepositories.value.filter((repo) => repo.stars !== null && repo.stars !== undefined))
const validScatter = computed(() => courseRepositories.value.filter((repo) => repo.stars !== null && repo.stars !== undefined && repo.forks !== null && repo.forks !== undefined))
const createdYearRows = computed(() => {
  const counts = new Map<number, number>()
  for (const repo of courseRepositories.value) {
    const year = Number(repo.createdAt?.slice(0, 4))
    if (Number.isInteger(year) && year >= 2000 && year <= 2100) counts.set(year, (counts.get(year) ?? 0) + 1)
  }
  return [...counts].sort(([left], [right]) => left - right)
})
const starsBuckets = computed(() => {
  const buckets = [
    { label: '< 100', min: 0, max: 100 },
    { label: '100–499', min: 100, max: 500 },
    { label: '500–999', min: 500, max: 1_000 },
    { label: '1k–4.9k', min: 1_000, max: 5_000 },
    { label: '5k–9.9k', min: 5_000, max: 10_000 },
    { label: '10k+', min: 10_000, max: Number.POSITIVE_INFINITY },
  ]
  return buckets.map((bucket) => ({
    label: bucket.label,
    count: validStars.value.filter((repo) => (repo.stars ?? -1) >= bucket.min && (repo.stars ?? -1) < bucket.max).length,
  }))
})
const activeWeekBuckets = computed(() => {
  const ranges = [
    { label: '0–2 周', min: 0, max: 3 },
    { label: '3–5 周', min: 3, max: 6 },
    { label: '6–8 周', min: 6, max: 9 },
    { label: '9–10 周', min: 9, max: 11 },
    { label: '11–12 周', min: 11, max: 13 },
  ]
  const rows = courseRepositories.value
  return ranges.map((range) => ({
    label: range.label,
    count: rows.filter((repo) => repo.activeWeeks !== null && repo.activeWeeks !== undefined && repo.activeWeeks >= range.min && repo.activeWeeks < range.max).length,
  }))
})
const t = computed(() => chartTheme(ui.isDark))
const tooltip = computed(() => ({
  trigger: 'axis' as const,
  backgroundColor: t.value.panel,
  borderColor: t.value.border,
  borderWidth: 1,
  textStyle: { color: t.value.ink, fontSize: 11, fontFamily },
  axisPointer: { type: 'shadow' as const },
}))
const axisLabel = computed(() => ({ color: t.value.muted, fontSize: 10, fontFamily }))
const axisLine = computed(() => ({ lineStyle: { color: t.value.grid } }))
const axisTick = { show: false }
const commonGrid = { left: 48, right: 18, top: 24, bottom: 34, containLabel: true }
function logAxisLabel(value: number) {
  if (value === 0) return '0'
  const approximate = 10 ** Math.round(value) - 1
  return approximate >= 1_000 ? `${Math.round(approximate / 1_000)}k` : `${Math.round(approximate)}`
}

const languageOption = computed<EChartsOption>(() => ({
  color: t.value.series,
  tooltip: { trigger: 'item', backgroundColor: t.value.panel, borderColor: t.value.border, textStyle: { color: t.value.ink, fontFamily } },
  title: {
    text: props.dashboard.repositoryCount.toLocaleString('zh-CN'),
    subtext: '个仓库',
    left: '36%',
    top: '42%',
    textAlign: 'center',
    itemGap: 1,
    textStyle: { color: t.value.ink, fontSize: 18, fontWeight: 600, fontFamily },
    subtextStyle: { color: t.value.muted, fontSize: 10.5, fontFamily },
  },
  legend: { type: 'scroll', orient: 'vertical', right: 4, top: 'middle', itemWidth: 9, itemHeight: 9, textStyle: { color: t.value.muted, fontSize: 10.5, fontFamily } },
  series: [{
    type: 'pie',
    radius: ['48%', '76%'],
    center: ['36%', '52%'],
    minAngle: 2,
    label: { show: false },
    itemStyle: { borderColor: t.value.panel, borderWidth: 2 },
    data: languageGroups.value.map((group) => ({ name: group.language, value: group.repositoryCount })),
  }],
}))

const starsOption = computed<EChartsOption>(() => ({
  grid: commonGrid,
  tooltip: tooltip.value,
  xAxis: { type: 'category', data: starsBuckets.value.map((bucket) => bucket.label), axisLabel: axisLabel.value, axisLine: { show: false }, axisTick },
  yAxis: { type: 'value', min: 0, axisLabel: axisLabel.value, axisLine: { show: false }, axisTick, splitLine: axisLine.value },
  series: [{ name: '仓库数', type: 'bar', barMaxWidth: 30, data: starsBuckets.value.map((bucket) => bucket.count), itemStyle: { color: t.value.series[0], borderRadius: [4, 4, 0, 0] } }],
}))

const scatterOption = computed<EChartsOption>(() => ({
  grid: { left: 58, right: 20, top: 24, bottom: 40 },
  tooltip: {
    trigger: 'item',
    backgroundColor: t.value.panel,
    borderColor: t.value.border,
    textStyle: { color: t.value.ink, fontSize: 11, fontFamily },
    formatter: (raw: unknown) => {
      const point = raw as { name?: string; value?: number[] }
      const value = point.value ?? []
      return `${point.name ?? '仓库'}<br/>Stars：${Number(value[2] ?? 0).toLocaleString('zh-CN')}<br/>Forks：${Number(value[3] ?? 0).toLocaleString('zh-CN')}`
    },
  },
  xAxis: {
    type: 'value', name: 'Stars · log₁₀(1+x)', nameLocation: 'middle', nameGap: 27,
    min: 0, interval: 1, axisLabel: { ...axisLabel.value, formatter: logAxisLabel },
    axisLine: { show: false }, axisTick, splitLine: axisLine.value,
  },
  yAxis: {
    type: 'value', name: 'Forks · log₁₀(1+x)', nameLocation: 'middle', nameGap: 42,
    min: 0, interval: 1, axisLabel: { ...axisLabel.value, formatter: logAxisLabel },
    axisLine: { show: false }, axisTick, splitLine: axisLine.value,
  },
  series: [{
    name: '仓库', type: 'scatter', symbolSize: 7,
    itemStyle: { color: t.value.series[3], opacity: 0.72 },
    data: validScatter.value.map((repo) => ({ name: repo.fullName, value: [Math.log10((repo.stars ?? 0) + 1), Math.log10((repo.forks ?? 0) + 1), repo.stars ?? 0, repo.forks ?? 0] })),
  }],
}))

const createdOption = computed<EChartsOption>(() => ({
  grid: { ...commonGrid, left: 42, bottom: 42 },
  tooltip: tooltip.value,
  xAxis: { type: 'category', data: createdYearRows.value.map(([year]) => String(year)), axisLabel: { ...axisLabel.value, rotate: 35 }, axisLine: { show: false }, axisTick },
  yAxis: { type: 'value', min: 0, axisLabel: axisLabel.value, axisLine: { show: false }, axisTick, splitLine: axisLine.value },
  series: [{ name: '仓库数', type: 'bar', barMaxWidth: 24, data: createdYearRows.value.map(([, count]) => count), itemStyle: { color: t.value.series[1], borderRadius: [4, 4, 0, 0] } }],
}))

const languageCommitOption = computed<EChartsOption>(() => {
  const rows = [...languageGroups.value].filter((group) => group.weeklyCommitMean !== null).sort((a, b) => (a.weeklyCommitMean ?? 0) - (b.weeklyCommitMean ?? 0))
  return {
    grid: { left: 72, right: 20, top: 14, bottom: 22, containLabel: true },
    tooltip: { ...tooltip.value, formatter: (raw: unknown) => {
      const params = Array.isArray(raw) ? raw[0] as { name: string; value: number } : raw as { name: string; value: number }
      const group = rows.find((item) => item.language === params.name)
      return `${params.name}<br/>周均 Commit：${Number(params.value).toFixed(2)}<br/>完整覆盖仓库：${group?.commitSampleCount ?? 0} / ${group?.repositoryCount ?? 0}`
    } },
    xAxis: { type: 'value', min: 0, axisLabel: { ...axisLabel.value, formatter: (value: number) => value.toLocaleString('zh-CN') }, axisLine: { show: false }, axisTick, splitLine: axisLine.value },
    yAxis: { type: 'category', data: rows.map((group) => group.language), axisLabel: axisLabel.value, axisLine: { show: false }, axisTick },
    series: [{ name: '每仓库周均 Commit', type: 'bar', barMaxWidth: 19, data: rows.map((group) => group.weeklyCommitMean), itemStyle: { color: t.value.series[2], borderRadius: [0, 4, 4, 0] } }],
  }
})

const activeWeeksOption = computed<EChartsOption>(() => ({
  grid: commonGrid,
  tooltip: tooltip.value,
  xAxis: { type: 'category', data: activeWeekBuckets.value.map((bucket) => bucket.label), axisLabel: { ...axisLabel.value, interval: 0 }, axisLine: { show: false }, axisTick },
  yAxis: { type: 'value', min: 0, axisLabel: axisLabel.value, axisLine: { show: false }, axisTick, splitLine: axisLine.value },
  series: [{ name: '仓库数', type: 'bar', barMaxWidth: 30, data: activeWeekBuckets.value.map((bucket) => bucket.count), itemStyle: { color: t.value.series[4], borderRadius: [4, 4, 0, 0] } }],
}))

const stats = computed(() => [
  { label: '仓库', value: props.dashboard.repositoryCount.toLocaleString('zh-CN'), note: '默认历史样本' },
  { label: '编程语言', value: languageGroups.value.length.toLocaleString('zh-CN'), note: '按仓库主语言' },
  { label: 'Commit 周记录', value: (props.dashboard.courseSummary?.weeklyRecords ?? 0).toLocaleString('zh-CN'), note: '12 个完整 UTC 周' },
  { label: '资料快照', value: dataAsOf.value, note: '非实时 GitHub 数据' },
])
</script>

<template>
  <section class="flex min-w-0 flex-col gap-3.5" aria-labelledby="repository-dashboard-title" data-testid="repository-dashboard">
    <div class="flex flex-wrap items-end justify-between gap-2">
      <div>
        <div class="flex flex-wrap items-center gap-2">
          <h2 id="repository-dashboard-title" class="m-0 text-[18px] font-semibold tracking-[-0.2px]">默认仓库数据看板</h2>
          <span class="rounded-full bg-soft px-2 py-0.5 text-[10.5px] text-muted">{{ props.dashboard.repositoryCount.toLocaleString('zh-CN') }} 个仓库</span>
        </div>
        <p class="mb-0 mt-1 text-[12px] text-muted">从仓库资料与 12 周完整 Commit 汇总中查看技术栈、关注度和活动分布。</p>
      </div>
    </div>

      <div class="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <div v-for="stat in stats" :key="stat.label" class="min-w-0 rounded-xl border border-line bg-panel px-3.5 py-3">
          <div class="text-[11px] text-muted">{{ stat.label }}</div>
          <div class="mt-1 truncate text-[20px] font-semibold leading-tight tabular-nums" :title="stat.value">{{ stat.value }}</div>
          <div class="mt-1 truncate text-[10.5px] text-muted">{{ stat.note }}</div>
        </div>
      </div>

      <div class="grid min-w-0 gap-3.5 md:grid-cols-2 2xl:grid-cols-3">
        <GdCard class="min-w-0 overflow-hidden" data-testid="dashboard-language-chart">
          <div><h3 class="m-0 text-[14px] font-semibold">编程语言构成</h3><p class="mb-0 mt-1 text-[11px] text-muted">{{ props.dashboard.repositoryCount }} 个仓库的主语言分布</p></div>
          <EChart v-if="languageGroups.length" :option="languageOption" :height="225" />
          <p v-else class="py-8 text-center text-[12px] text-muted">暂无语言分布数据。</p>
        </GdCard>

        <GdCard class="min-w-0 overflow-hidden" data-testid="dashboard-stars-chart">
          <div><h3 class="m-0 text-[14px] font-semibold">Stars 关注度分布</h3><p class="mb-0 mt-1 text-[11px] text-muted">按 Stars 区间统计仓库数量</p></div>
          <EChart v-if="validStars.length" :option="starsOption" :height="225" />
          <p v-else class="py-8 text-center text-[12px] text-muted">暂无 Stars 数据。</p>
        </GdCard>

        <GdCard class="min-w-0 overflow-hidden" data-testid="dashboard-stars-forks-chart">
          <div><h3 class="m-0 text-[14px] font-semibold">Stars 与 Forks 关系</h3><p class="mb-0 mt-1 text-[11px] text-muted">对数坐标压缩长尾；悬停可查看仓库与原始数量</p></div>
          <EChart v-if="validScatter.length" :option="scatterOption" :height="225" />
          <p v-else class="py-8 text-center text-[12px] text-muted">暂无可配对的 Stars/Forks 数据。</p>
        </GdCard>

        <GdCard class="min-w-0 overflow-hidden" data-testid="dashboard-created-year-chart">
          <div><h3 class="m-0 text-[14px] font-semibold">仓库创建年份</h3><p class="mb-0 mt-1 text-[11px] text-muted">按 GitHub 仓库创建时间统计</p></div>
          <EChart v-if="createdYearRows.length" :option="createdOption" :height="225" />
          <p v-else class="py-8 text-center text-[12px] text-muted">暂无创建时间数据。</p>
        </GdCard>

        <GdCard class="min-w-0 overflow-hidden" data-testid="dashboard-language-commits-chart">
          <div><h3 class="m-0 text-[14px] font-semibold">各语言周均 Commit</h3><p class="mb-0 mt-1 text-[11px] text-muted">只纳入 12 周 Commit 覆盖完整的仓库</p></div>
          <EChart v-if="languageGroups.some((group) => group.weeklyCommitMean !== null)" :option="languageCommitOption" :height="225" />
          <p v-else class="py-8 text-center text-[12px] text-muted">暂无完整周均 Commit 数据。</p>
        </GdCard>

        <GdCard class="min-w-0 overflow-hidden" data-testid="dashboard-active-weeks-chart">
          <div><h3 class="m-0 text-[14px] font-semibold">12 周活动连续性</h3><p class="mb-0 mt-1 text-[11px] text-muted">每周至少 1 次 Commit 计为活跃周</p></div>
          <EChart v-if="courseRepositories.length" :option="activeWeeksOption" :height="225" />
          <p v-else class="py-8 text-center text-[12px] text-muted">暂无仓库周活动汇总。</p>
        </GdCard>
      </div>
      <p class="m-0 text-[10.5px] leading-relaxed text-muted">资料来源：本地 300 仓库历史数据集。周均 Commit 与活跃周基于 {{ (props.dashboard.courseSummary?.completeCommitRepositories ?? 0).toLocaleString('zh-CN') }} 个 12 周完整样本；Stars、Forks 和创建时间取资料快照（{{ dataAsOf }} UTC）。</p>
  </section>
</template>
