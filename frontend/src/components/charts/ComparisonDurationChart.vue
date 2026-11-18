<script setup lang="ts">
import { computed } from 'vue'
import type { G2Spec } from '@antv/g2'
import { useUiStore } from '@/stores/ui'
import G2Chart from './G2Chart.vue'

interface ComparisonDurationItem {
  label: string
  color: string
  issueP50: number | null
  issueSample: number
  issueQuality: string
  prP50: number | null
  prSample: number
  prQuality: string
}
const props = withDefaults(defineProps<{ items: ComparisonDurationItem[]; height?: number }>(), { height: 260 })
const ui = useUiStore()
const spec = computed<G2Spec>(() => {
  const data = props.items.flatMap((item) => [
    ...(item.issueP50 === null ? [] : [{ metric: 'Issue 关闭 P50', repository: item.label, days: item.issueP50, sample: item.issueSample, quality: item.issueQuality }]),
    ...(item.prP50 === null ? [] : [{ metric: 'PR 合并 P50', repository: item.label, days: item.prP50, sample: item.prSample, quality: item.prQuality }]),
  ])
  const axisColor = ui.isDark ? '#bec8d0' : '#667480'
  const gridColor = ui.isDark ? '#303942' : '#e6ebef'
  return {
    type: 'interval', data, transform: [{ type: 'dodgeX' }],
    coordinate: { transform: [{ type: 'transpose' }] },
    encode: { x: 'metric', y: 'days', color: 'repository' },
    scale: {
      color: { domain: props.items.map((item) => item.label), range: props.items.map((item) => item.color) },
      y: { domainMin: 0 },
    },
    style: { radiusTopRight: 3, radiusBottomRight: 3 },
    axis: {
      x: { labelFill: axisColor, labelFontSize: 10, title: false },
      y: { labelFill: axisColor, labelFontSize: 10, title: '天', gridStroke: gridColor, gridLineDash: [3, 3] },
    },
    legend: { color: { position: 'bottom', itemLabelFill: axisColor, itemLabelFontSize: 9 } },
    tooltip: { title: 'repository', items: [
      { field: 'metric', name: '指标' }, { field: 'days', name: 'P50（天）' },
      { field: 'sample', name: '有效样本数' }, { field: 'quality', name: '覆盖状态' },
    ] },
  }
})
</script>

<template><G2Chart :spec="spec" label="仓库 Issue 和 PR 处理耗时 P50 对比图，悬停显示样本数及覆盖状态" :height="height" /></template>
