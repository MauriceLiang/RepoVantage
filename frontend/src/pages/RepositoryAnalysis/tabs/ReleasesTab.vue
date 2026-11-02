<script setup lang="ts">
import { computed } from 'vue'
import ReleaseCadenceChart from '@/components/charts/ReleaseCadenceChart.vue'
import TimelineChart from '@/components/charts/TimelineChart.vue'
import { coveredCommitPoints } from '@/components/charts/comboHelpers'
import KpiStrip from '@/components/common/KpiStrip.vue'
import GdCard from '@/components/ui/GdCard.vue'
import type { RepositoryAnalysis } from '@/services/types'
import { useReleaseDrawer } from '@/composables/useReleaseDrawer'

const props = defineProps<{ analysis: RepositoryAnalysis }>()
const { openRelease } = useReleaseDrawer(() => props.analysis.repository.id)

const yearReleases = computed(() => props.analysis.releases)
const commitPoints = computed(() => {
  const points = props.analysis.commits.series[0]?.points ?? []
  return props.analysis.chartData ? coveredCommitPoints(points, props.analysis.chartData.commitWeekly) : points
})
const cadenceItems = computed(() => yearReleases.value
  .filter((release) => !release.prerelease && release.intervalDays !== null)
  .map((release) => {
    const interval = props.analysis.chartData?.releaseIntervals.find((item) => item.id === release.tag)
    return { tag: release.tag, date: release.publishedAt, days: release.intervalDays as number, previousDate: interval?.previousPublishedAt ?? null, commitCount: interval?.commitCount ?? null, reason: interval?.reason ?? null }
  }))
const identifierLabel = computed(() => yearReleases.value[0]?.identifierType === 'release_id' ? 'Release ID' : '版本')
const sorted = computed(() => [...yearReleases.value].sort((a, b) => +new Date(b.publishedAt) - +new Date(a.publishedAt)))
const median = computed(() => {
  const days = cadenceItems.value.map((r) => r.days).sort((a, b) => a - b)
  if (!days.length) return null
  const middle = Math.floor(days.length / 2)
  return days.length % 2 ? days[middle] : (days[middle - 1] + days[middle]) / 2
})

function openReleaseByTag(tag: string) {
  const release = yearReleases.value.find((item) => item.tag === tag)
  if (release) void openRelease(release)
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
    <GdCard class="h-[420px] overflow-hidden">
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">相邻发布间隔</h3>
          <p class="mt-0.5 text-[12px] text-muted">近 365 天已采集的正式 Release · 按发布时间排序</p>
        </div>
        <span class="font-mono text-[11.5px] text-muted">n={{ cadenceItems.length }} · P50 {{ median?.toLocaleString('en-US', { maximumFractionDigits: 1 }) ?? '—' }} 天</span>
      </div>
      <ReleaseCadenceChart v-if="cadenceItems.length" :items="cadenceItems" :height="290" @select="openReleaseByTag" />
      <div v-else class="flex min-h-0 flex-1 items-center justify-center rounded-md bg-soft px-4 text-center text-[12px] text-muted">相邻间隔至少需要 2 次正式发布；当前没有可比较的连续版本。</div>
      <p class="m-0 text-[11px] text-muted">柱为已观察的发布间隔；折线为两次发布间的提交数（含前次、不含本次，UTC），仅在 Commit 完整覆盖该区间时显示。点击查看版本说明。</p>
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
