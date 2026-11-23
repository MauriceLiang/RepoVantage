<script setup lang="ts">
import { computed } from 'vue'
import type { G2Spec } from '@antv/g2'
import G2Chart from './G2Chart.vue'
import { storeToRefs } from 'pinia'
import { useUiStore } from '@/stores/ui'

const props = withDefaults(defineProps<{
  links: Array<{ source: string; target: string; value: number }>
  label: string
  height?: number
}>(), { height: 360 })
const { theme } = storeToRefs(useUiStore())
const spec = computed<G2Spec>(() => ({
  type: 'sankey',
  data: props.links,
  encode: { source: 'source', target: 'target', value: 'value' },
  layout: { nodeAlign: 'justify', nodePadding: 0.025, nodeWidth: 0.018, iterations: 24 },
  style: {
    labelSpacing: 3,
    labelFontSize: 9,
    nodeStrokeWidth: 1,
    linkFill: theme.value === 'dark' ? '#74828e' : '#7c8995',
    linkFillOpacity: 0.42,
  },
  tooltip: { title: (datum: { source?: string; target?: string; name?: string }) => datum.name ?? `${datum.source ?? ''} → ${datum.target ?? ''}` },
}))
</script>

<template><G2Chart :spec="spec" :label="label" :height="height" /></template>
