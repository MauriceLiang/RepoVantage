<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import type { SelectionMetric } from '@/services/types'
import type { MetricReadiness, SelectionMetricOption, SelectionWeights, WeightPreset } from '../weightMath'

const props = defineProps<{
  metrics: SelectionMetricOption[]
  weights: SelectionWeights
  readiness: Record<SelectionMetric, MetricReadiness>
  enabled: boolean
  updating: boolean
  preset: WeightPreset
}>()

const emit = defineEmits<{
  changeWeight: [payload: { metric: SelectionMetric; value: number }]
  selectPreset: [preset: Exclude<WeightPreset, 'custom'>]
}>()

const presets: Array<{ key: Exclude<WeightPreset, 'custom'>; label: string }> = [
  { key: 'balanced', label: '均衡' },
  { key: 'activity', label: '开发活跃' },
  { key: 'collaboration', label: '协作效率' },
  { key: 'release', label: '发布节奏' },
]

const drafts = reactive({} as Record<SelectionMetric, string>)
const errors = reactive<Partial<Record<SelectionMetric, string>>>({})
let editingMetric: SelectionMetric | null = null

const formatWeight = (value: number) => value.toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
const totalWeight = computed(() => props.metrics.reduce((sum, metric) => sum + props.weights[metric.key], 0))

watch(() => ({ ...props.weights }), (next) => {
  props.metrics.forEach(({ key }) => {
    if (editingMetric !== key) drafts[key] = formatWeight(next[key])
  })
}, { deep: true, immediate: true })

function onSliderInput(metric: SelectionMetric, event: Event) {
  const value = Number((event.target as HTMLInputElement).value)
  if (Number.isFinite(value)) emit('changeWeight', { metric, value })
}

function onDraftInput(metric: SelectionMetric, event: Event) {
  drafts[metric] = (event.target as HTMLInputElement).value
  delete errors[metric]
}

function commitInput(metric: SelectionMetric) {
  const raw = drafts[metric].trim()
  const value = raw === '' ? Number.NaN : Number(raw)
  if (!Number.isFinite(value) || value < 0 || value > 100) {
    errors[metric] = '请输入 0–100 的有效数值。'
    drafts[metric] = formatWeight(props.weights[metric])
    editingMetric = null
    return
  }

  errors[metric] = undefined
  drafts[metric] = formatWeight(value)
  editingMetric = null
  if (Math.abs(value - props.weights[metric]) > 0.000001) emit('changeWeight', { metric, value })
}

function cancelInput(metric: SelectionMetric, event: KeyboardEvent) {
  event.preventDefault()
  drafts[metric] = formatWeight(props.weights[metric])
  errors[metric] = undefined
  editingMetric = null
  ;(event.target as HTMLInputElement).blur()
}
</script>

<template>
  <section class="space-y-2" aria-labelledby="comparison-weight-title" :aria-busy="updating">
    <div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <div class="flex min-w-0 flex-wrap items-center gap-2">
        <h4 id="comparison-weight-title" class="m-0 text-[13px] font-semibold">评价权重</h4>
        <span class="text-[10.5px] tabular-nums text-muted">合计 {{ formatWeight(totalWeight) }}% · 修改一项后其余按比例分摊</span>
      </div>
      <div class="flex flex-wrap items-center gap-1.5" role="group" aria-label="权重预设">
        <button
          v-for="item in presets"
          :key="item.key"
          type="button"
          :disabled="!enabled"
          :aria-pressed="preset === item.key"
          class="rounded-md border px-2.5 py-1.5 text-[11.5px] transition-colors motion-reduce:transition-none disabled:cursor-not-allowed disabled:opacity-45"
          :class="preset === item.key ? 'border-[var(--gd-primary-button)] bg-soft font-semibold text-ink' : 'border-line bg-panel text-muted hover:text-ink'"
          :data-testid="`weight-preset-${item.key}`"
          @click="emit('selectPreset', item.key)"
        >{{ item.label }}</button>
      </div>
    </div>
    <p v-if="updating" class="m-0 text-[10.5px] text-muted" role="status" aria-live="polite">正在读取可用指标数据…</p>

    <fieldset class="m-0 grid min-w-0 gap-1.5 border-0 p-0 sm:grid-cols-2" :disabled="!enabled">
      <legend class="sr-only">设置四项指标的综合评分权重</legend>
      <div
        v-for="metric in metrics"
        :key="metric.key"
        class="min-w-0 rounded-md border border-line bg-panel px-3 py-1.5"
        :data-testid="`weight-metric-${metric.key}`"
      >
        <div class="flex min-w-0 items-center justify-between gap-2">
          <div class="flex min-w-0 items-baseline gap-1.5">
            <label :for="`weight-value-${metric.key}`" class="truncate text-[12px] font-medium text-ink">{{ metric.label }}</label>
            <span class="shrink-0 text-[10px] text-muted">{{ metric.direction }}</span>
          </div>
          <div class="flex shrink-0 items-center gap-1">
            <input
              :id="`weight-value-${metric.key}`"
              :value="drafts[metric.key]"
              type="text"
              inputmode="decimal"
              autocomplete="off"
              spellcheck="false"
              maxlength="7"
              role="spinbutton"
              aria-valuemin="0"
              aria-valuemax="100"
              :aria-valuenow="props.weights[metric.key]"
              :aria-describedby="errors[metric.key] ? `weight-error-${metric.key}` : `weight-state-${metric.key}`"
              :aria-label="`${metric.label}百分比权重`"
              class="w-16 rounded border border-line bg-panel px-1.5 py-1 text-right font-mono text-[12px] tabular-nums text-ink outline-none focus-visible:border-[var(--gd-primary-button)] focus-visible:ring-2 focus-visible:ring-[var(--gd-primary-button)]/25 disabled:cursor-not-allowed disabled:opacity-50"
              :data-testid="`weight-input-${metric.key}`"
              @focus="editingMetric = metric.key"
              @input="onDraftInput(metric.key, $event)"
              @blur="commitInput(metric.key)"
              @keydown.enter.prevent="commitInput(metric.key)"
              @keydown.esc="cancelInput(metric.key, $event)"
            />
            <span class="text-[11px] text-muted">%</span>
          </div>
        </div>

        <div class="mt-1.5 flex min-w-0 items-center gap-2.5">
          <input
            type="range"
            min="0"
            max="100"
            step="any"
            :value="weights[metric.key]"
            :aria-label="`${metric.label}权重`"
            :aria-valuetext="`${formatWeight(weights[metric.key])}% 权重`"
            class="h-2 min-w-0 flex-1 cursor-pointer disabled:cursor-not-allowed"
            :style="{ accentColor: metric.color }"
            :data-testid="`weight-slider-${metric.key}`"
            @input="onSliderInput(metric.key, $event)"
          />
          <span class="max-w-[38%] shrink-0 truncate text-[9.5px] text-muted" :title="`${readiness[metric.key].ready}/${readiness[metric.key].total} 仓库有实测${readiness[metric.key].partial ? '，含部分覆盖' : readiness[metric.key].ready === 0 ? '，该项仅形成中性分' : ''}`">
            <template v-if="enabled">
              {{ readiness[metric.key].ready }}/{{ readiness[metric.key].total }} 实测<span v-if="readiness[metric.key].partial"> · 部分覆盖</span><span v-else-if="readiness[metric.key].ready === 0"> · 中性计分</span>
            </template>
            <template v-else>等待数据</template>
          </span>
        </div>

        <p v-if="errors[metric.key]" :id="`weight-error-${metric.key}`" class="mb-0 mt-1 text-[10.5px] text-warnfg" role="alert">{{ errors[metric.key] }}</p>
        <p v-else :id="`weight-state-${metric.key}`" class="sr-only">{{ enabled ? `${readiness[metric.key].ready}/${readiness[metric.key].total} 个仓库有实测数据${readiness[metric.key].partial ? '，含部分覆盖' : readiness[metric.key].ready === 0 ? '，该项只形成中性分' : ''}` : '等待指标数据' }}</p>
      </div>
    </fieldset>
  </section>
</template>
