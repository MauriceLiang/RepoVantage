<script setup lang="ts">
import * as echarts from 'echarts/core'
import { BarChart, CustomChart, HeatmapChart, LineChart, ScatterChart } from 'echarts/charts'
import { CalendarComponent, DataZoomComponent, GridComponent, LegendComponent, MarkLineComponent, MarkPointComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

echarts.use([BarChart, CustomChart, LineChart, ScatterChart, HeatmapChart, GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, MarkPointComponent, VisualMapComponent, CalendarComponent, DataZoomComponent, CanvasRenderer])

const props = withDefaults(defineProps<{ option: EChartsOption; height?: number; hideTooltipOnSelect?: boolean }>(), { height: 240, hideTooltipOnSelect: false })
const emit = defineEmits<{
  select: [payload: { dataIndex: number; seriesName: string; name: string; value: unknown }]
  dataZoom: [payload: { start?: number; end?: number; startValue?: number | string; endValue?: number | string }]
}>()
const el = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let observer: ResizeObserver | null = null

onMounted(() => {
  if (!el.value) return
  chart = echarts.init(el.value, undefined, { renderer: 'canvas' })
  chart.setOption(props.option)
  chart.on('click', (params) => {
    if (typeof params.dataIndex !== 'number') return
    if (props.hideTooltipOnSelect) chart?.dispatchAction({ type: 'hideTip' })
    emit('select', { dataIndex: params.dataIndex, seriesName: String(params.seriesName ?? ''), name: String(params.name ?? ''), value: params.value })
  })
  chart.on('datazoom', (event) => {
    const payload = event as {
      start?: number; end?: number; startValue?: number | string; endValue?: number | string
      batch?: { start?: number; end?: number; startValue?: number | string; endValue?: number | string }[]
    }
    const range = payload.batch?.[0] ?? payload
    emit('dataZoom', { start: range.start, end: range.end, startValue: range.startValue, endValue: range.endValue })
  })
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(el.value)
})

watch(() => props.option, (option) => chart?.setOption(option, true), { deep: true })
watch(() => props.height, () => chart?.resize())

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
  chart = null
})

defineExpose({ chart })
</script>

<template>
  <div ref="el" :style="{ height: `${height}px`, width: '100%' }" />
</template>
