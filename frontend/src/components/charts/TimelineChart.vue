<script setup lang="ts">
import { computed } from 'vue'
import type { ReleaseRecord, TimePoint } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { timelineOption } from './options'
import { chartTheme } from './theme'

const props = withDefaults(defineProps<{ releases: ReleaseRecord[]; commits?: TimePoint[]; height?: number; compact?: boolean }>(), { commits: () => [], height: 150, compact: false })
const emit = defineEmits<{ select: [release: ReleaseRecord] }>()
const ui = useUiStore()
const option = computed(() => timelineOption(props.releases, chartTheme(ui.isDark), props.compact, props.commits))

function select(payload: { dataIndex: number; seriesName: string }) {
  if (payload.seriesName !== '正式发布' && payload.seriesName !== '预发布') return
  const prerelease = payload.seriesName === '预发布'
  const release = props.releases.filter((item) => item.prerelease === prerelease)[payload.dataIndex]
  if (release) emit('select', release)
}
</script>

<template>
  <EChart :option="option" :height="height" @select="select" />
</template>
