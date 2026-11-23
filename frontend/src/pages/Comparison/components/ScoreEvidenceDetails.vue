<script setup lang="ts">
import { computed } from 'vue'
import type { SelectionResult, SelectionMetric } from '@/services/types'
import type { SelectionMetricOption } from '../weightMath'

type Evidence = SelectionResult['ranking'][number]['evidence'][number]

const props = defineProps<{
  evidence: Evidence[]
  metrics: SelectionMetricOption[]
}>()

const metricLabels = computed(() => Object.fromEntries(props.metrics.map((metric) => [metric.key, metric.label])) as Record<SelectionMetric, string>)
const activeEvidence = computed(() => props.evidence.filter((item) => item.weight > 0))
const formatNumber = (value: number) => value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
const formatDate = (value: string | null) => value ? `${value.slice(0, 10)} UTC` : '不可用'
const evidenceValue = (item: Evidence) => item.missingPolicy === 'neutral_50' || item.value === null
  ? '中性 50 分（无有效样本）'
  : `${formatNumber(item.value)} ${item.unit}`
const evidenceState = (item: Evidence) => item.missingPolicy === 'neutral_50' || item.value === null
  ? '无有效样本'
  : item.quality === 'partial' ? '部分覆盖' : '实测'
</script>

<template>
  <div class="space-y-2.5 rounded-md bg-soft/30 p-3" data-testid="score-evidence-details">
    <div class="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
      <h5 class="m-0 text-[11.5px] font-semibold">指标贡献与证据</h5>
      <p class="m-0 text-[10.5px] text-muted">分数和贡献均为 0–100 量纲</p>
    </div>

    <div class="hidden overflow-x-auto rounded border border-line bg-panel sm:block" tabindex="0" aria-label="评分指标详情，可横向滚动">
      <table class="w-full min-w-[690px] table-fixed border-collapse text-left text-[11px]">
        <thead class="bg-soft/50 text-muted">
          <tr>
            <th scope="col" class="w-[22%] px-2.5 py-2 font-medium">指标</th>
            <th scope="col" class="w-[25%] px-2.5 py-2 font-medium">原始值</th>
            <th scope="col" class="w-[12%] px-2.5 py-2 text-right font-medium">权重</th>
            <th scope="col" class="w-[13%] px-2.5 py-2 text-right font-medium">单项分</th>
            <th scope="col" class="w-[13%] px-2.5 py-2 text-right font-medium">贡献分</th>
            <th scope="col" class="w-[15%] px-2.5 py-2 font-medium">状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in activeEvidence" :key="item.metric" class="border-t border-line align-top">
            <th scope="row" class="px-2.5 py-2 font-medium text-ink">
              {{ metricLabels[item.metric] ?? item.metric }}
              <span v-if="item.metric === 'release_interval_days'" class="block font-normal text-muted">近 365 天独立窗口</span>
            </th>
            <td class="px-2.5 py-2 font-mono tabular-nums text-ink">{{ evidenceValue(item) }}</td>
            <td class="px-2.5 py-2 text-right font-mono tabular-nums text-ink">{{ formatNumber(item.weight * 100) }}%</td>
            <td class="px-2.5 py-2 text-right font-mono tabular-nums text-ink">{{ formatNumber(item.normalized * 100) }}</td>
            <td class="px-2.5 py-2 text-right font-mono tabular-nums text-ink">{{ formatNumber(item.contribution) }}</td>
            <td class="px-2.5 py-2">
              <span :class="item.quality === 'partial' && item.missingPolicy === 'observed' ? 'text-warnfg' : 'text-muted'">{{ evidenceState(item) }}</span>
              <details class="mt-1">
                <summary class="cursor-pointer text-[10px] text-muted">样本与来源</summary>
                <dl class="mb-0 mt-1 space-y-0.5 text-[10px] leading-relaxed text-muted">
                  <div class="flex flex-wrap gap-x-1"><dt>有效样本</dt><dd class="m-0 font-mono">{{ item.validSamples }}</dd></div>
                  <div class="flex flex-wrap gap-x-1"><dt>覆盖</dt><dd class="m-0">{{ item.quality }}</dd></div>
                  <div class="flex flex-wrap gap-x-1"><dt>窗口</dt><dd class="m-0">{{ formatDate(item.windowStart) }} — {{ formatDate(item.windowEnd) }}</dd></div>
                  <div class="flex flex-wrap gap-x-1"><dt>来源类型</dt><dd class="m-0 break-all">{{ item.sourceKind ?? '不可用' }}</dd></div>
                  <div class="flex flex-wrap gap-x-1"><dt>运行 ID</dt><dd class="m-0 break-all font-mono">{{ item.sourceRunId ?? '不可用' }}</dd></div>
                </dl>
              </details>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="space-y-2 sm:hidden">
      <article v-for="item in activeEvidence" :key="item.metric" class="rounded border border-line bg-panel p-2.5">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <h6 class="m-0 text-[11.5px] font-medium">{{ metricLabels[item.metric] ?? item.metric }}</h6>
            <span v-if="item.metric === 'release_interval_days'" class="text-[10px] text-muted">近 365 天独立窗口</span>
          </div>
          <span class="shrink-0 text-[10.5px]" :class="item.quality === 'partial' && item.missingPolicy === 'observed' ? 'text-warnfg' : 'text-muted'">{{ evidenceState(item) }}</span>
        </div>
        <p class="mb-0 mt-1.5 break-words font-mono text-[11px] tabular-nums text-ink">{{ evidenceValue(item) }}</p>
        <dl class="mb-0 mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[10px] text-muted">
          <div><dt>权重</dt><dd class="m-0 font-mono tabular-nums text-ink">{{ formatNumber(item.weight * 100) }}%</dd></div>
          <div><dt>单项分</dt><dd class="m-0 font-mono tabular-nums text-ink">{{ formatNumber(item.normalized * 100) }}</dd></div>
          <div><dt>贡献分</dt><dd class="m-0 font-mono tabular-nums text-ink">{{ formatNumber(item.contribution) }}</dd></div>
          <div><dt>有效样本</dt><dd class="m-0 font-mono tabular-nums text-ink">{{ item.validSamples }}</dd></div>
        </dl>
        <details class="mt-2 border-t border-line pt-1.5">
          <summary class="cursor-pointer text-[10px] text-muted">样本与来源</summary>
          <dl class="mb-0 mt-1 space-y-1 break-words text-[10px] leading-relaxed text-muted">
            <div><dt>覆盖</dt><dd class="m-0">{{ item.quality }}</dd></div>
            <div><dt>窗口</dt><dd class="m-0">{{ formatDate(item.windowStart) }} — {{ formatDate(item.windowEnd) }}</dd></div>
            <div><dt>来源类型</dt><dd class="m-0">{{ item.sourceKind ?? '不可用' }}</dd></div>
            <div><dt>运行 ID</dt><dd class="m-0 font-mono">{{ item.sourceRunId ?? '不可用' }}</dd></div>
          </dl>
        </details>
      </article>
      <p v-if="activeEvidence.length === 0" class="m-0 text-[11px] text-muted">没有正权重指标的证据可展示。</p>
    </div>
  </div>
</template>
