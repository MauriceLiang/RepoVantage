<script setup lang="ts">
import { computed } from 'vue'

type ContributionRow = { label: string; value: number; color: string }

const props = defineProps<{
  rows: ContributionRow[]
  total: number
  mode: 'ranked' | 'summary'
  label: string
}>()

const displayRows = computed(() => props.mode === 'ranked'
  ? [...props.rows].sort((left, right) => right.value - left.value)
  : props.rows)
const activeRows = computed(() => displayRows.value.filter((row) => row.value > 0))

function percentage(value: number) {
  if (props.total <= 0) return 0
  return Math.round((value / props.total) * 100)
}

function barWidth(value: number) {
  return Math.min(100, Math.max(0, (value / Math.max(props.total, 1)) * 100))
}
</script>

<template>
  <div v-if="mode === 'ranked'" class="grid content-start gap-3" role="list" :aria-label="label">
    <div v-for="row in displayRows" :key="row.label" class="grid gap-1.5" role="listitem">
      <div class="flex min-w-0 items-baseline gap-2 text-[11px]">
        <span class="size-2 shrink-0 translate-y-[-1px] rounded-full" :style="{ backgroundColor: row.color }" aria-hidden="true" />
        <span class="min-w-0 flex-1 truncate font-medium" :title="row.label">{{ row.label }}</span>
        <span class="shrink-0 font-mono tabular-nums">{{ row.value.toLocaleString('zh-CN') }}</span>
        <span class="w-10 shrink-0 text-right text-muted tabular-nums">{{ percentage(row.value) }}%</span>
      </div>
      <div class="h-2 overflow-hidden rounded-full bg-soft" aria-hidden="true">
        <span class="block h-full rounded-full" :style="{ width: `${barWidth(row.value)}%`, backgroundColor: row.color }" />
      </div>
    </div>
  </div>

  <div v-else class="flex h-full min-h-[112px] flex-col justify-center gap-3" :aria-label="label">
    <div class="grid grid-cols-3 divide-x divide-line rounded-lg border border-line">
      <div v-for="row in displayRows" :key="row.label" class="min-w-0 px-3 py-2.5 first:pl-3 last:pr-3">
        <div class="flex min-w-0 items-center gap-1.5 text-[10.5px] text-muted">
          <span class="size-2 shrink-0 rounded-full" :style="{ backgroundColor: row.color }" aria-hidden="true" />
          <span class="truncate" :title="row.label">{{ row.label }}</span>
        </div>
        <div class="mt-1 flex items-baseline gap-1.5">
          <strong class="text-[18px] font-semibold leading-none tabular-nums">{{ row.value.toLocaleString('zh-CN') }}</strong>
          <span class="text-[10px] text-muted tabular-nums">{{ percentage(row.value) }}%</span>
        </div>
      </div>
    </div>
    <div v-if="activeRows.length > 1" class="flex h-2.5 overflow-hidden rounded-full bg-soft" role="img" :aria-label="`${label}分类比例`">
      <span v-for="row in activeRows" :key="row.label" class="h-full first:rounded-l-full last:rounded-r-full" :style="{ width: `${barWidth(row.value)}%`, backgroundColor: row.color }" :title="`${row.label}：${row.value.toLocaleString('zh-CN')}（${percentage(row.value)}%）`" />
    </div>
  </div>
</template>
