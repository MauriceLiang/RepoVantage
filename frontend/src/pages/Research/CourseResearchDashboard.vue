<script setup lang="ts">
import { BookOpen, Search } from 'lucide-vue-next'
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import GdBadge from '@/components/ui/GdBadge.vue'
import GdCard from '@/components/ui/GdCard.vue'
import { formatDate } from '@/lib/format'
import type { ResearchDataset } from '@/services/types'

const props = defineProps<{ data: ResearchDataset; compareIds: string[] }>()
const emit = defineEmits<{ compare: [repositoryId: string]; definitions: [] }>()
const repositorySearch = defineModel<string>('repositorySearch', { default: '' })

const languages = computed(() => [...(props.data.courseLanguageGroups ?? [])].sort((a, b) => b.repositoryCount - a.repositoryCount || a.language.localeCompare(b.language)))
const maxLanguageCount = computed(() => Math.max(0, ...languages.value.map((group) => group.repositoryCount)))
const maxCommitMean = computed(() => Math.max(0, ...languages.value.map((group) => group.weeklyCommitMean ?? 0)))
const repositories = computed(() => props.data.courseRepositories ?? [])
const filteredRepositories = computed(() => {
  const query = repositorySearch.value.trim().toLocaleLowerCase()
  return repositories.value.filter((repository) => !query || `${repository.fullName} ${repository.language}`.toLocaleLowerCase().includes(query))
})
const coverageRows = computed(() => {
  const coverage = props.data.courseSummary?.coverage
  return [
    { label: 'Commit 周记录', value: coverage?.commit_week_complete_or_true_zero ?? null, partial: null },
    { label: 'PR 创建周记录', value: coverage?.pr_opened_week_complete_or_true_zero ?? null, partial: null },
    { label: 'PR 合并周记录', value: coverage?.pr_merged_week_complete_or_true_zero ?? null, partial: coverage?.pr_merged_week_partial_concurrent_change ?? null },
  ]
})

function ratio(value: number | null, total: number | null | undefined) {
  return value === null || !total ? null : value / total * 100
}

function barWidth(value: number | null, total: number | null | undefined) {
  const percentage = ratio(value, total)
  return `${percentage === null ? 0 : Math.min(100, Math.max(0, percentage))}%`
}

function number(value: number | null | undefined) {
  return value === null || value === undefined ? '—' : value.toLocaleString('zh-CN')
}
</script>

<template>
  <div class="flex min-w-0 flex-col gap-[18px]">
    <GdCard data-testid="course-research-summary">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-2">
            <h2 class="m-0 text-[17px] font-semibold">默认仓库数据集</h2>
            <GdBadge variant="plain">历史快照</GdBadge>
          </div>
          <p class="mb-0 mt-1.5 text-[12.5px] leading-relaxed text-muted">来自本地已采集的 {{ number(data.repositoryCount) }} 个仓库，用于查看历史活动与数据覆盖。</p>
        </div>
        <button class="gd-link shrink-0 text-[12px]" @click="emit('definitions')">
          <BookOpen :size="14" /> 采样说明与局限
        </button>
      </div>

      <div class="grid grid-cols-2 gap-x-5 gap-y-4 border-y border-line py-4 lg:grid-cols-4">
        <div>
          <div class="text-[12px] text-muted">默认仓库</div>
          <div class="mt-1 text-[26px] font-semibold leading-tight tabular-nums">{{ number(data.repositoryCount) }}<span class="ml-1 text-[12px] font-normal text-muted">个</span></div>
          <div class="mt-1 text-[11px] text-muted">按当前本地数据展示</div>
        </div>
        <div>
          <div class="text-[12px] text-muted">仓库周记录</div>
          <div class="mt-1 text-[26px] font-semibold leading-tight tabular-nums">{{ number(data.courseSummary?.weeklyRecords) }}<span class="ml-1 text-[12px] font-normal text-muted">条</span></div>
          <div class="mt-1 text-[11px] text-muted">12 个完整 UTC 周</div>
        </div>
        <div>
          <div class="text-[12px] text-muted">Commit 完整覆盖</div>
          <div class="mt-1 text-[26px] font-semibold leading-tight tabular-nums">{{ number(data.courseSummary?.completeCommitRepositories) }} <span class="text-[14px] font-normal text-muted">/ {{ number(data.repositoryCount) }}</span></div>
          <div class="mt-1 text-[11px] text-muted">最近 12 周均有覆盖的仓库</div>
        </div>
        <div>
          <div class="text-[12px] text-muted">PR 创建覆盖</div>
          <div class="mt-1 text-[26px] font-semibold leading-tight tabular-nums">{{ number(coverageRows[1]?.value) }}<span class="mx-1 text-[14px] font-normal text-muted">/ {{ number(data.courseSummary?.weeklyRecords) }}</span></div>
          <div class="mt-1 text-[11px] text-muted">最近 12 周完整或确认无记录</div>
        </div>
      </div>

      <div class="grid gap-3 sm:grid-cols-3">
        <div class="rounded-md bg-soft/40 px-3 py-2.5">
          <div class="text-[11.5px] text-muted">Issue 关闭耗时</div>
          <div class="mt-1 font-mono text-[18px] font-semibold">{{ data.issueMedianDays === null ? '—' : `${data.issueMedianDays.toFixed(1)} 天` }}</div>
          <div class="mt-1 text-[11px] text-muted">{{ number(data.issueSample) }} 个仓库有结果</div>
        </div>
        <div class="rounded-md bg-soft/40 px-3 py-2.5">
          <div class="text-[11.5px] text-muted">PR 合并耗时</div>
          <div class="mt-1 font-mono text-[18px] font-semibold">{{ data.prMedianDays === null ? '—' : `${data.prMedianDays.toFixed(1)} 天` }}</div>
          <div class="mt-1 text-[11px] text-muted">{{ number(data.prSample) }} 个仓库有结果</div>
        </div>
        <div class="rounded-md bg-soft/40 px-3 py-2.5">
          <div class="text-[11.5px] text-muted">正式 Release 间隔</div>
          <div class="mt-1 font-mono text-[18px] font-semibold">{{ data.releaseMedianDays == null ? '—' : `${data.releaseMedianDays.toFixed(1)} 天` }}</div>
          <div class="mt-1 text-[11px] text-muted">{{ number(data.releaseSample) }} 个仓库有结果</div>
        </div>
      </div>
      <p class="m-0 text-[11px] leading-relaxed text-muted">数值为各仓库中位数的中位数；截至 {{ formatDate(data.courseSummary?.eventWindowEnd) }} UTC，Issue、PR 使用 90 天窗口，Release 使用 365 天窗口。部分覆盖按已观察样本计算。</p>

      <div class="flex flex-wrap items-center justify-between gap-x-5 gap-y-2 text-[12px] leading-relaxed text-muted">
        <p class="m-0">观察窗口 <span class="font-medium text-ink">{{ formatDate(data.courseSummary?.observationWindow.start) }} 至 {{ formatDate(data.courseSummary?.observationWindow.endExclusive) }}</span> <span class="whitespace-nowrap">（UTC，结束日期不含）</span></p>
        <p class="m-0">资料快照 {{ formatDate(data.courseSummary?.dataAsOf) }}</p>
      </div>
      <details class="text-[12px] leading-relaxed text-muted">
        <summary class="w-fit cursor-pointer font-medium text-ink">查看样本来源与范围</summary>
        <div class="mt-2 grid gap-1.5 sm:grid-cols-2">
          <p class="m-0"><span class="text-muted">采样来源：</span>{{ data.samplingSource }}</p>
          <p class="m-0"><span class="text-muted">采样规则：</span>{{ data.samplingRule }}</p>
          <p class="m-0"><span class="text-muted">数据集版本：</span>{{ data.datasetVersion ?? '—' }}</p>
          <p class="m-0">{{ data.isProbabilitySample ? '概率样本' : '非概率样本' }} · {{ data.populationScope }}</p>
        </div>
      </details>
    </GdCard>

    <div class="grid min-w-0 gap-[18px] lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
      <GdCard data-testid="course-language-distribution">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">语言分布与提交活动</h3>
          <p class="mb-0 mt-1 text-[12px] leading-relaxed text-muted">按语言比较仓库数量与每仓库周均 Commit；条形长度在各列内比较。</p>
        </div>
        <div v-if="languages.length" class="flex flex-col gap-2 divide-y divide-line">
          <div v-for="group in languages" :key="group.language" class="grid grid-cols-2 gap-x-4 gap-y-2 py-3 first:pt-1 last:pb-1 sm:grid-cols-[minmax(85px,0.75fr)_minmax(0,1fr)_minmax(0,1fr)] sm:items-center">
            <div class="col-span-2 truncate text-[12.5px] font-semibold sm:col-span-1" :title="group.language">{{ group.language }}</div>
            <div class="min-w-0">
              <div class="flex items-baseline justify-between gap-1 text-[11.5px]"><span class="text-muted">仓库</span><span class="whitespace-nowrap font-medium tabular-nums">{{ number(group.repositoryCount) }} <span class="font-normal text-muted">· {{ ratio(group.repositoryCount, data.repositoryCount)?.toFixed(1) ?? '—' }}%</span></span></div>
              <div class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-track" aria-hidden="true"><div class="h-full rounded-full bg-s1" :style="{ width: barWidth(group.repositoryCount, maxLanguageCount) }" /></div>
            </div>
            <div class="min-w-0">
              <div class="flex items-baseline justify-between gap-1 text-[11.5px]"><span class="whitespace-nowrap text-muted">周均 <span class="text-[11px]">n={{ number(group.commitSampleCount) }}</span></span><span class="font-medium tabular-nums">{{ group.weeklyCommitMean?.toFixed(2) ?? '—' }}</span></div>
              <div class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-track" aria-hidden="true"><div class="h-full rounded-full bg-s4" :style="{ width: barWidth(group.weeklyCommitMean, maxCommitMean) }" /></div>
            </div>
          </div>
        </div>
        <p v-else class="py-8 text-center text-[12px] text-muted">当前样本没有可展示的语言分组。</p>
        <p class="m-0 border-t border-line pt-3 text-[11.5px] leading-relaxed text-muted">仓库占比以当前 {{ number(data.repositoryCount) }} 个仓库为分母；周均值仅统计该语言组中 12 周 Commit 覆盖完整的仓库。</p>
      </GdCard>

      <GdCard data-testid="course-weekly-coverage">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">周记录覆盖</h3>
          <p class="mb-0 mt-1 text-[12px] leading-relaxed text-muted">完整或真实为零的周记录 / 全部仓库周记录</p>
        </div>
        <div class="flex flex-col gap-5 py-1">
          <div v-for="row in coverageRows" :key="row.label">
            <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <span class="text-[12.5px] font-medium">{{ row.label }}</span>
              <span class="text-[12px] tabular-nums"><strong class="font-semibold">{{ number(row.value) }}</strong><span class="text-muted"> / {{ number(data.courseSummary?.weeklyRecords) }}</span></span>
            </div>
            <div class="mt-2 h-2 overflow-hidden rounded-full bg-track" aria-hidden="true"><div class="h-full rounded-full bg-s1" :style="{ width: barWidth(row.value, data.courseSummary?.weeklyRecords) }" /></div>
            <div class="mt-1.5 flex flex-wrap justify-between gap-x-3 gap-y-1 text-[11px] text-muted">
              <span>{{ ratio(row.value, data.courseSummary?.weeklyRecords)?.toFixed(1) ?? '—' }}<template v-if="ratio(row.value, data.courseSummary?.weeklyRecords) !== null">%</template> 完整或真实为零</span>
              <span v-if="row.partial !== null && row.partial > 0">{{ number(row.partial) }} 条部分覆盖</span>
            </div>
          </div>
        </div>
        <p class="m-0 border-t border-line pt-3 text-[11.5px] leading-relaxed text-muted">部分覆盖不会计入完整记录；覆盖率描述数据完整性，不代表仓库表现。</p>
      </GdCard>
    </div>

    <GdCard data-testid="course-repositories">
      <div class="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">仓库列表</h3>
          <p class="mb-0 mt-1 text-[12px] text-muted">{{ number(filteredRepositories.length) }} / {{ number(repositories.length) }} 个仓库 · 查看概览或加入比较</p>
        </div>
        <label class="relative block w-full sm:w-60">
          <Search :size="14" class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" aria-hidden="true" />
          <input v-model="repositorySearch" aria-label="搜索课程仓库" placeholder="搜索名称或语言" class="h-9 w-full rounded-md border border-line bg-panel pl-9 pr-3 text-[12px]" />
        </label>
      </div>
      <p class="m-0 text-[11.5px] text-muted sm:hidden">左右滑动表格可查看完整指标和操作。</p>
      <div class="max-h-[390px] overflow-auto rounded-lg border border-line" role="region" aria-label="默认仓库列表，可横向滚动" tabindex="0">
        <table class="w-full min-w-[630px] border-collapse text-left text-[12px]">
          <thead class="sticky top-0 z-[1] bg-soft text-[11.5px] text-muted"><tr><th class="px-3 py-2.5 font-medium">仓库</th><th class="px-3 py-2.5 font-medium">语言</th><th class="px-3 py-2.5 font-medium">活跃周数</th><th class="px-3 py-2.5 font-medium">周均 Commit</th><th class="px-3 py-2.5 font-medium">操作</th></tr></thead>
          <tbody>
            <tr v-for="repository in filteredRepositories" :key="repository.repositoryId" class="border-t border-line">
              <td class="px-3 py-2.5 font-medium">{{ repository.fullName }}</td>
              <td class="px-3 py-2.5 text-muted">{{ repository.language }}</td>
              <td class="px-3 py-2.5 tabular-nums">{{ repository.activeWeeks === null ? '—' : `${repository.activeWeeks} / 12` }}</td>
              <td class="px-3 py-2.5 tabular-nums">{{ repository.weeklyCommitMean?.toFixed(2) ?? '—' }}</td>
              <td class="whitespace-nowrap px-3 py-2.5"><RouterLink :to="`/repositories/${repository.repositoryId}/overview`" class="gd-link">概览</RouterLink><button class="gd-link ml-3" :aria-label="`${compareIds.includes(repository.repositoryId) ? '已加入对比' : '加入对比'} ${repository.fullName}`" @click="emit('compare', repository.repositoryId)">{{ compareIds.includes(repository.repositoryId) ? '已加入' : '加入对比' }}</button></td>
            </tr>
            <tr v-if="!filteredRepositories.length"><td colspan="5" class="px-3 py-8 text-center text-muted">没有匹配的仓库。</td></tr>
          </tbody>
        </table>
      </div>
      <p class="m-0 text-[11.5px] leading-relaxed text-muted">活跃周指有 Commit 的完整周。可选择最多 5 个仓库进行比较。</p>
    </GdCard>
  </div>
</template>
