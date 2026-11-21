<script setup lang="ts">
import { Chart, type G2Spec } from '@antv/g2'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useUiStore } from '@/stores/ui'

const emit = defineEmits<{ select: [payload: { dataIndex: number; seriesName: string; name: string; value: unknown; datum: Record<string, unknown> }] }>()

const props = withDefaults(defineProps<{
  spec: G2Spec
  label: string
  height?: number
}>(), { height: 250 })

const host = ref<HTMLDivElement | null>(null)
const error = ref('')
const ui = useUiStore()
const { theme } = storeToRefs(ui)
let chart: InstanceType<typeof Chart> | null = null
let renderedTheme: string | null = null
let renderSequence = 0
let renderQueue = Promise.resolve()
let resizeObserver: ResizeObserver | null = null
let observedWidth = 0
let isMounted = false

type AxisConfig = Record<string, unknown>
type SpecNode = Record<string, unknown>

function collectXValues(node: unknown): unknown[] {
  if (!node || typeof node !== 'object' || Array.isArray(node)) return []
  const source = node as SpecNode
  const rows = Array.isArray(source.data) ? source.data as Record<string, unknown>[] : []
  const encode = source.encode && typeof source.encode === 'object' ? source.encode as Record<string, unknown> : {}
  const xField = encode.x
  const localValues = typeof xField === 'string' ? rows.map((row) => row[xField]) : []
  const childValues = Array.isArray(source.children) ? source.children.flatMap(collectXValues) : []
  return [...localValues, ...childValues]
}

function dateParts(value: unknown): { year: number; month: number; day?: number } | null {
  if (value instanceof Date && Number.isFinite(value.getTime())) {
    return { year: value.getUTCFullYear(), month: value.getUTCMonth() + 1, day: value.getUTCDate() }
  }
  if (typeof value !== 'string') return null
  const match = value.match(/^(\d{4})-(\d{2})(?:-(\d{2}))?(?:T.*)?$/)
  if (!match) return null
  const year = Number(match[1])
  const month = Number(match[2])
  const day = match[3] ? Number(match[3]) : undefined
  if (month < 1 || month > 12 || (day !== undefined && (day < 1 || day > 31))) return null
  return { year, month, ...(day === undefined ? {} : { day }) }
}

function formatDateTick(value: unknown, _index: number, tickValues?: unknown[]) {
  const parts = dateParts(value)
  if (!parts) return String(value ?? '')
  const ticks = Array.isArray(tickValues) ? tickValues : []
  const years = new Set(ticks.flatMap((tick) => {
    const date = dateParts(tick)
    return date ? [date.year] : []
  }))
  const prefix = years.size > 1 ? `${String(parts.year).slice(-2)}/` : ''
  const month = String(parts.month).padStart(2, '0')
  if (parts.day === undefined) return years.size > 1 ? `${String(parts.year).slice(-2)}/${month}` : `${parts.month}月`
  return `${prefix}${month}/${String(parts.day).padStart(2, '0')}`
}

function withAxisDensity(node: unknown, width: number): unknown {
  if (!node || typeof node !== 'object' || Array.isArray(node)) return node
  const source = node as SpecNode
  const result: SpecNode = { ...source }
  const axis = source.axis
  if (axis && typeof axis === 'object' && !Array.isArray(axis)) {
    const sourceAxes = axis as Record<string, unknown>
    const axes = { ...sourceAxes }
    const xAxis = sourceAxes.x
    if (xAxis && typeof xAxis === 'object' && !Array.isArray(xAxis)) {
      const config = xAxis as AxisConfig
      const userFilter = config.labelFilter
      const userFormatter = config.labelFormatter
      const maxLabels = Math.max(4, Math.min(16, Math.floor(Math.max(280, width - 36) / 68)))
      const xValues = collectXValues(source)
      const isDateAxis = xValues.length > 0 && xValues.every((value) => dateParts(value) !== null)
      axes.x = {
        ...config,
        ...(config.title === undefined ? { title: false } : {}),
        labelFormatter: userFormatter === undefined
          ? (value: unknown, index: number, ticks: unknown[]) => formatDateTick(value, index, ticks)
          : userFormatter,
        labelFilter: (value: unknown, index: number, tickValues?: unknown[]) => {
          const ticks = Array.isArray(tickValues) ? tickValues : []
          const passesUserFilter = typeof userFilter !== 'function' || userFilter(value, index, ticks)
          if (!passesUserFilter || ticks.length <= maxLabels) return passesUserFilter
          const stride = Math.ceil((ticks.length - 1) / (maxLabels - 1))
          return index === 0 || index === ticks.length - 1 || index % stride === 0
        },
        ...(isDateAxis ? { labelAutoRotate: false } : {}),
      }
    }
    result.axis = axes
  }
  if (Array.isArray(source.children)) result.children = source.children.map((child) => withAxisDensity(child, width))
  return result
}

function scheduleRender() {
  renderQueue = renderQueue.then(() => renderChart())
}

async function renderChart() {
  await nextTick()
  const container = host.value
  if (!container || !isMounted) return
  const sequence = ++renderSequence
  const nextTheme = theme.value

  try {
    if (chart && renderedTheme !== nextTheme) {
      chart.destroy()
      chart = null
    }
    if (!chart) {
      chart = new Chart({
        container,
        autoFit: true,
        theme: nextTheme === 'dark' ? 'classicDark' : 'classic',
      })
      renderedTheme = nextTheme
      chart.on('element:click', (event: { data?: { data?: unknown; index?: number } }) => {
        const eventData = event.data?.data
        const datum = (Array.isArray(eventData) ? eventData[0] : eventData) as Record<string, unknown> | undefined
        if (!datum) return
        const rawIndex = datum.dataIndex ?? datum.sourceIndex ?? event.data?.index
        if (typeof rawIndex !== 'number' || !Number.isFinite(rawIndex)) return
        const dataIndex = rawIndex
        const seriesName = String(datum.seriesName ?? datum.series ?? datum.label ?? '')
        const name = String(datum.name ?? datum.fullName ?? datum.label ?? datum.date ?? datum.week ?? datum.metric ?? '')
        emit('select', { dataIndex, seriesName, name, value: datum.value ?? datum.plotted ?? datum.count ?? null, datum })
      })
    }
    chart.options(withAxisDensity(props.spec, container.clientWidth) as G2Spec)
    // `render()` can retain the previous canvas dimensions after a CSS-only
    // layout change (for example, a desktop-to-mobile grid breakpoint). Force
    // G2 to read the current host dimensions so the canvas cannot overflow its
    // responsive panel.
    await chart.forceFit()
    if (sequence === renderSequence) error.value = ''
  } catch (cause) {
    if (sequence === renderSequence) {
      error.value = cause instanceof Error ? cause.message : '图表暂时无法显示'
    }
  }
}

watch(() => props.spec, scheduleRender, { deep: true })
watch(theme, scheduleRender)
onMounted(() => {
  isMounted = true
  if (host.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver((entries) => {
      const width = Math.round(entries[0]?.contentRect.width ?? 0)
      if (Math.abs(width - observedWidth) < 24) return
      observedWidth = width
      if (isMounted) scheduleRender()
    })
    resizeObserver.observe(host.value)
  }
  scheduleRender()
})
onBeforeUnmount(() => {
  renderSequence += 1
  isMounted = false
  resizeObserver?.disconnect()
  resizeObserver = null
  chart?.destroy()
  chart = null
})
</script>

<template>
  <div class="g2-chart" :style="{ height: `${height}px` }">
    <div ref="host" class="g2-chart__canvas" role="img" :aria-label="label" />
    <p v-if="error" class="g2-chart__error" role="status">{{ error }}</p>
  </div>
</template>

<style scoped>
.g2-chart { position: relative; width: 100%; min-width: 0; }
.g2-chart__canvas { width: 100%; height: 100%; min-height: 120px; }
.g2-chart__error { position: absolute; inset: 0; display: grid; place-items: center; margin: 0; color: var(--muted, #77848e); font-size: 12px; }
</style>
