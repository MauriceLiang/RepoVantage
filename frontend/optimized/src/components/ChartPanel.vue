<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart, ScatterChart, TreemapChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'

echarts.use([BarChart, LineChart, PieChart, ScatterChart, TreemapChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const props = withDefaults(defineProps<{ option: EChartsOption; label: string; height?: number }>(), { height: 260 })
const root = ref<HTMLDivElement | null>(null)
let chart: ReturnType<typeof echarts.init> | null = null
let observer: ResizeObserver | null = null

onMounted(() => {
  if (!root.value) return
  const instance = echarts.init(root.value)
  chart = instance
  instance.setOption(props.option)
  observer = new ResizeObserver(() => instance.resize())
  observer.observe(root.value)
})

watch(() => props.option, (option) => chart?.setOption(option, { notMerge: true, lazyUpdate: true }), { deep: true })

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
  observer = null
  chart = null
})
</script>

<template>
  <div ref="root" class="chart-canvas" :style="{ height: `${height}px` }" role="img" :aria-label="label" />
</template>
