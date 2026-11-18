<script setup lang="ts">
import { computed } from 'vue'
import type { G2Spec } from '@antv/g2'
import { useUiStore } from '@/stores/ui'
import G2Chart from './G2Chart.vue'

interface ScoreRow {
  id: string
  name: string
  score: number
  rank: number
  color: string
}

const props = withDefaults(defineProps<{ rows: ScoreRow[]; height?: number }>(), { height: 220 })
const ui = useUiStore()
const spec = computed<G2Spec>(() => {
  const axisColor = ui.isDark ? '#bec8d0' : '#667480'
  const gridColor = ui.isDark ? '#303942' : '#e6ebef'
  return {
    type: 'interval',
    data: props.rows,
    coordinate: { transform: [{ type: 'transpose' }] },
    encode: { x: 'name', y: 'score', color: 'name' },
    scale: {
      x: { domain: props.rows.map((row) => row.name) },
      y: { domainMin: 0, domainMax: 100 },
      color: { domain: props.rows.map((row) => row.name), range: props.rows.map((row) => row.color) },
    },
    style: { radiusTopRight: 4, radiusBottomRight: 4 },
    axis: {
      x: { labelFill: axisColor, labelFontSize: 10 },
      y: { labelFill: axisColor, labelFontSize: 10, title: '综合分 / 100', gridStroke: gridColor, gridLineDash: [3, 3] },
    },
    legend: false,
    tooltip: { title: 'name', items: [{ field: 'score', name: '综合分' }, { field: 'rank', name: '排名' }] },
  }
})
</script>

<template>
  <G2Chart :spec="spec" label="后端实际计算的仓库综合分横向对照，单位为分，范围 0 到 100" :height="height" />
</template>
