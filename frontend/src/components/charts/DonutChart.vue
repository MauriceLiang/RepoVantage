<script setup lang="ts">
import { computed } from 'vue'
import type { G2Spec } from '@antv/g2'
import { useUiStore } from '@/stores/ui'
import G2Chart from './G2Chart.vue'

const props = withDefaults(defineProps<{
  rows: Array<{ label: string; value: number }>
  total: string
  centerLabel?: string
  label: string
  height?: number
  colors?: string[]
}>(), {
  centerLabel: '总计',
  height: 240,
  colors: () => ['#356fc7', '#56a58c', '#d1a34a', '#9c78bd', '#ce7189', '#74828e', '#aeb6bd'],
})
const ui = useUiStore()
const spec = computed<G2Spec>(() => ({
  type: 'interval',
  data: props.rows.filter((row) => row.value > 0),
  transform: [{ type: 'stackY' }],
  coordinate: { type: 'theta', innerRadius: 0.64, outerRadius: 0.9 },
  encode: { y: 'value', color: 'label' },
  scale: { color: { domain: props.rows.map((row) => row.label), range: props.colors } },
  style: { stroke: ui.isDark ? '#171b20' : '#ffffff', lineWidth: 1.5 },
  axis: false,
  legend: { color: { position: 'bottom', layout: { justifyContent: 'center' }, itemLabelFontSize: 10 } },
  tooltip: { title: 'label', items: [{ field: 'value', name: '数量' }] },
}))
</script>

<template>
  <div class="donut-chart" :style="{ height: `${height}px` }">
    <G2Chart :spec="spec" :label="label" :height="height" />
    <div class="donut-chart__center" aria-hidden="true"><strong>{{ total }}</strong><span>{{ centerLabel }}</span></div>
  </div>
</template>

<style scoped>
.donut-chart { position: relative; min-width: 0; }
.donut-chart__center { position: absolute; top: 44.5%; left: 50%; display: grid; width: 36%; place-items: center; transform: translate(-50%,-50%); pointer-events: none; }
.donut-chart__center strong { color: var(--ink); font-size: 21px; font-variant-numeric: tabular-nums; line-height: 1.1; }
.donut-chart__center span { margin-top: 3px; color: var(--muted); font-size: 10px; }
</style>
