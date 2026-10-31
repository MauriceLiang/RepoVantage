<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { TimePoint } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { calendarOption } from './options'
import { chartTheme } from './theme'

const props = withDefaults(defineProps<{ points: TimePoint[]; windowStart?: string | null; windowEnd?: string | null; height?: number }>(), { height: 200 })
const ui = useUiStore()
const host = ref<HTMLDivElement | null>(null)
const width = ref(0)
let observer: ResizeObserver | null = null
const canRender = computed(() => {
  const start = props.windowStart ? Date.parse(props.windowStart) : NaN
  const end = props.windowEnd ? Date.parse(props.windowEnd) : NaN
  return (Number.isFinite(start) && Number.isFinite(end) && end > start) || props.points.some((point) => Number.isFinite(Date.parse(point.date)))
})
const option = computed(() => calendarOption(props.points, chartTheme(ui.isDark), props.windowStart, props.windowEnd, width.value))

onMounted(() => {
  if (!host.value) return
  width.value = host.value.clientWidth
  observer = new ResizeObserver(([entry]) => { width.value = entry.contentRect.width })
  observer.observe(host.value)
})
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div ref="host" class="min-w-0">
    <EChart v-if="canRender" :option="option" :height="height" />
    <div v-else class="flex items-center justify-center text-[11px] text-muted" :style="{ height: `${height}px` }">无法确定采集窗口，暂不绘制日历。</div>
  </div>
</template>
