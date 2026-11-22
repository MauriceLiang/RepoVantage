<script setup lang="ts">
import { computed } from 'vue'
import { ChevronDown, ChevronRight } from 'lucide-vue-next'
import type { SelectionResult } from '@/services/types'
import type { SelectionMetricOption } from '../weightMath'
import ScoreEvidenceDetails from './ScoreEvidenceDetails.vue'

const props = defineProps<{
  result: SelectionResult | null
  metrics: SelectionMetricOption[]
  stale: boolean
  updating: boolean
  expandedRepositoryId: string | null
}>()

const emit = defineEmits<{ toggleDetails: [repositoryId: string] }>()

const rows = computed(() => props.result?.status === 'available' ? props.result.ranking : [])
const activeMetricCount = computed(() => Object.values(props.result?.weights ?? {}).filter((weight) => Number.isFinite(weight) && weight > 0).length)
const allNeutral = computed(() => rows.value.length > 0 && rows.value.every((row) =>
  row.evidence.filter((item) => item.weight > 0).every((item) => item.missingPolicy !== 'observed'),
))
const exactTieExists = computed(() => rows.value.some((row, index) => rows.value.slice(index + 1).some((other) => row.score === other.score)))
const displayedTieExists = computed(() => rows.value.some((row, index) => rows.value.slice(index + 1).some((other) =>
  row.score !== other.score && row.score.toFixed(1) === other.score.toFixed(1),
)))
const hasPartialCoverage = computed(() => rows.value.some((row) => row.evidence.some((item) => item.weight > 0 && item.missingPolicy === 'observed' && item.quality === 'partial')))
const formatScore = (value: number) => value.toFixed(1)
const observedCount = (row: SelectionResult['ranking'][number]) => row.evidence.filter((item) => item.weight > 0 && item.missingPolicy === 'observed').length
const partialCount = (row: SelectionResult['ranking'][number]) => row.evidence.filter((item) => item.weight > 0 && item.missingPolicy === 'observed' && item.quality === 'partial').length
const expanded = (id: string) => props.expandedRepositoryId === id
const detailsId = (id: string, surface: 'desktop' | 'mobile' = 'desktop') => `selection-evidence-${surface}-${encodeURIComponent(id)}`
const toggle = (id: string) => emit('toggleDetails', id)
const rankNumber = (index: number): number => index > 0 && rows.value[index]?.score === rows.value[index - 1]?.score ? rankNumber(index - 1) : index + 1

function formatWindow(window: SelectionResult['sharedWindow']) {
  return window ? `${window.start.slice(0, 10)} 至 ${window.end.slice(0, 10)} UTC` : '使用各仓库自身窗口，不代表同期表现'
}
</script>

<template>
  <section class="space-y-2" aria-labelledby="comparison-ranking-title" :aria-busy="updating">
    <div class="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
      <div>
        <div class="flex flex-wrap items-center gap-2">
          <h4 id="comparison-ranking-title" class="m-0 text-[13px] font-semibold">综合排名</h4>
          <span class="text-[10.5px] text-muted">{{ rows.length || result?.ranking.length || 0 }} 个候选</span>
        </div>
        <p v-if="result" class="mb-0 mt-1 text-[10.5px] text-muted">{{ formatWindow(result.sharedWindow) }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-1.5 text-[10.5px]" aria-live="polite">
        <span v-if="updating" class="rounded-full bg-soft px-2 py-1 text-muted">{{ stale ? '上次结果 · 更新中' : '正在计算' }}</span>
        <span v-else-if="stale" class="rounded-full bg-warnbg px-2 py-1 text-warnfg">上次结果</span>
        <span v-else-if="result?.status === 'available'" class="rounded-full bg-soft px-2 py-1 text-muted">规则相对分</span>
      </div>
    </div>

    <template v-if="result?.status === 'available'">
      <p v-if="allNeutral" class="m-0 rounded-md bg-warnbg px-3 py-2 text-[11px] leading-relaxed text-warnfg" role="status">
        当前缺少可区分的实测证据，分数来自中性基准；排名顺序不代表实际表现优劣。
      </p>
      <p v-if="!allNeutral && exactTieExists" class="m-0 text-[10.5px] text-muted" role="status">同分仓库并列展示；同分行序保留后端顺序，不代表实际表现优劣。</p>
      <p v-if="!allNeutral && hasPartialCoverage" class="m-0 text-[10.5px] leading-relaxed text-muted" role="status">部分指标仅反映已观察样本，比较结果应结合覆盖情况解读。</p>
      <p v-if="displayedTieExists" class="m-0 text-[10.5px] text-muted">有仓库显示分数相同；行顺序保留后端精确分值排序。</p>

      <div class="overflow-hidden rounded-md border border-line bg-panel">
        <table class="hidden w-full table-fixed border-collapse text-left text-[11.5px] sm:table" aria-label="仓库综合评分排名">
          <thead class="bg-soft/40 text-[10.5px] text-muted">
            <tr>
              <th scope="col" class="w-[3.5rem] px-3 py-1 font-medium">名次</th>
              <th scope="col" class="px-3 py-1 font-medium">仓库</th>
              <th scope="col" class="w-[13rem] px-3 py-1 font-medium">综合分</th>
              <th scope="col" class="w-[6.5rem] px-3 py-1 font-medium">实测</th>
              <th scope="col" class="w-[5.5rem] px-3 py-1 text-right font-medium">证据</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(row, index) in rows" :key="row.id">
              <tr class="border-t border-line" :data-testid="`selection-score-${row.id}`">
                <td class="px-3 py-1 font-mono tabular-nums text-muted">{{ rankNumber(index) }}</td>
                <th scope="row" class="max-w-0 px-3 py-1 text-left font-medium text-ink">
                  <span class="block truncate" :title="row.name">{{ row.name }}</span>
                </th>
                <td class="px-3 py-1">
                  <div class="flex items-center gap-2.5">
                    <strong class="w-[3.25rem] shrink-0 text-right font-mono text-[15px] font-semibold tabular-nums text-ink">{{ formatScore(row.score) }}</strong>
                    <div class="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-track" role="progressbar" :aria-label="`${row.name} 综合分`" :aria-valuenow="Math.max(0, Math.min(100, row.score))" aria-valuemin="0" aria-valuemax="100">
                      <div class="h-full rounded-full bg-[var(--gd-primary-button)] transition-[width] duration-200 motion-reduce:transition-none" :style="{ width: `${Math.max(0, Math.min(100, row.score))}%` }" />
                    </div>
                    <span class="shrink-0 text-[10px] text-muted">/100</span>
                  </div>
                </td>
                <td class="px-3 py-1 font-mono tabular-nums text-ink">
                  <span>{{ activeMetricCount ? `${observedCount(row)}/${activeMetricCount}` : '—' }}</span>
                  <span v-if="partialCount(row)" class="ml-1 text-[10px] text-muted">部分</span>
                </td>
                <td class="px-3 py-1 text-right">
                  <button
                    type="button"
                    class="inline-flex items-center gap-1 rounded px-1.5 py-1 text-[10.5px] text-muted outline-none hover:bg-soft hover:text-ink focus-visible:ring-2 focus-visible:ring-[var(--gd-primary-button)]"
                    :aria-expanded="expanded(row.id)"
                    :aria-controls="detailsId(row.id)"
                    :aria-label="`${expanded(row.id) ? '收起' : '展开'} ${row.name} 的指标证据`"
                    :data-testid="`selection-details-toggle-${row.id}`"
                    @click="toggle(row.id)"
                  >
                    <component :is="expanded(row.id) ? ChevronDown : ChevronRight" :size="14" aria-hidden="true" />
                    {{ expanded(row.id) ? '收起' : '详情' }}
                  </button>
                </td>
              </tr>
              <tr v-if="expanded(row.id)" :id="detailsId(row.id)" class="border-t border-line bg-soft/20">
                <td colspan="5" class="px-3 py-2.5">
                  <ScoreEvidenceDetails :evidence="row.evidence" :metrics="metrics" />
                </td>
              </tr>
            </template>
          </tbody>
        </table>

        <ul class="m-0 list-none divide-y divide-line p-0 sm:hidden" aria-label="仓库综合评分排名">
          <li v-for="(row, index) in rows" :key="row.id" class="px-3 py-2.5" :data-mobile-score-id="row.id">
            <div class="flex min-w-0 items-start gap-2">
              <span class="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-soft font-mono text-[10px] tabular-nums text-muted">{{ rankNumber(index) }}</span>
              <div class="min-w-0 flex-1">
                <div class="flex min-w-0 items-baseline justify-between gap-2">
                  <span class="min-w-0 truncate text-[11.5px] font-medium text-ink" :title="row.name">{{ row.name }}</span>
                  <span class="shrink-0 font-mono text-[15px] font-semibold tabular-nums text-ink">{{ formatScore(row.score) }}<span class="ml-0.5 text-[9px] font-normal text-muted">/100</span></span>
                </div>
                <div class="mt-1.5 flex items-center gap-2">
                  <div class="h-1 min-w-0 flex-1 overflow-hidden rounded-full bg-track" role="progressbar" :aria-label="`${row.name} 综合分`" :aria-valuenow="Math.max(0, Math.min(100, row.score))" aria-valuemin="0" aria-valuemax="100">
                    <div class="h-full rounded-full bg-[var(--gd-primary-button)] transition-[width] duration-200 motion-reduce:transition-none" :style="{ width: `${Math.max(0, Math.min(100, row.score))}%` }" />
                  </div>
                  <span class="shrink-0 text-[10px] tabular-nums text-muted">实测 {{ activeMetricCount ? `${observedCount(row)}/${activeMetricCount}` : '—' }}<span v-if="partialCount(row)" class="ml-0.5">· 部分覆盖</span></span>
                  <button type="button" class="shrink-0 rounded px-1.5 py-0.5 text-[10px] text-muted outline-none hover:bg-soft hover:text-ink focus-visible:ring-2 focus-visible:ring-[var(--gd-primary-button)]" :aria-expanded="expanded(row.id)" :aria-controls="detailsId(row.id, 'mobile')" :aria-label="`${expanded(row.id) ? '收起' : '展开'} ${row.name} 的指标证据`" :data-testid="`selection-mobile-details-toggle-${row.id}`" @click="toggle(row.id)">{{ expanded(row.id) ? '收起' : '详情' }}</button>
                </div>
              </div>
            </div>
            <div v-if="expanded(row.id)" :id="detailsId(row.id, 'mobile')" class="mt-2">
              <ScoreEvidenceDetails :evidence="row.evidence" :metrics="metrics" />
            </div>
          </li>
        </ul>
      </div>
    </template>

    <div v-else-if="result?.status === 'insufficient_data'" class="rounded-md bg-warnbg px-3 py-2.5 text-[11px] leading-relaxed text-warnfg" role="status">
      当前数据不足，暂不能生成可用排名；请检查候选范围与可用的指标数据。
      <ul v-if="result.excluded.length" class="mb-0 mt-1 list-disc pl-4">
        <li v-for="item in result.excluded" :key="item.id">{{ item.name }}：{{ item.reasons.join('；') }}</li>
      </ul>
    </div>
    <div v-else-if="updating" class="space-y-2" role="status" aria-live="polite" aria-label="正在计算仓库综合排名">
      <div class="h-8 animate-pulse rounded bg-track/50 motion-reduce:animate-none" />
      <div class="h-8 animate-pulse rounded bg-track/50 motion-reduce:animate-none" />
    </div>

    <div v-if="result?.status === 'available' && result.excluded.length" class="rounded-md bg-warnbg px-3 py-2 text-[10.5px] leading-relaxed text-warnfg" data-testid="selection-excluded">
      <p class="m-0 font-medium">未参与排名</p>
      <p v-for="item in result.excluded" :key="item.id" class="m-0 mt-0.5 break-words">{{ item.name }}：{{ item.reasons.join('；') }}</p>
    </div>

  </section>
</template>
