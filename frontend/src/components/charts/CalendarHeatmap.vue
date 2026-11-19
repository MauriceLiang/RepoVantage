<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { TimePoint } from '@/services/types'
import { useUiStore } from '@/stores/ui'

interface CalendarCell {
  date: string
  week: number
  day: number
  point?: TimePoint
  commitCount: number | null
  intensity: number
  state: 'missing' | 'partial' | 'zero' | 'complete'
}
const props = withDefaults(defineProps<{ points: TimePoint[]; windowStart?: string | null; windowEnd?: string | null; height?: number; metricLabel?: string }>(), { height: 200, metricLabel: 'Commit' })
const ui = useUiStore()
const calendar = computed(() => {
  const validDates = props.points.map((point) => point.date).filter((date) => Number.isFinite(Date.parse(`${date.slice(0, 10)}T00:00:00Z`))).sort()
  const startTime = props.windowStart ? Date.parse(props.windowStart) : NaN
  const endTime = props.windowEnd ? Date.parse(props.windowEnd) : NaN
  const start = Number.isFinite(startTime) ? startTime : validDates.length ? Date.parse(`${validDates[0]}T00:00:00Z`) : NaN
  const end = Number.isFinite(endTime) && Number.isFinite(startTime) && endTime > startTime
    ? endTime
    : validDates.length ? Date.parse(`${validDates.at(-1)}T00:00:00Z`) + 86400000 : NaN
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return { weeks: 0, cells: [] as CalendarCell[], months: [] as { week: number; label: string }[] }

  const monday = new Date(start)
  const weekday = (monday.getUTCDay() + 6) % 7
  monday.setUTCDate(monday.getUTCDate() - weekday)
  const firstMonday = monday.getTime()
  const weeks = Math.ceil((end - firstMonday) / (7 * 86400000))
  const byDate = new Map(props.points.map((point) => [point.date.slice(0, 10), point]))
  const values = props.points.flatMap((point) => [point.value, point.observedValue]).filter((value): value is number => typeof value === 'number' && value >= 0)
  const max = Math.max(1, ...values)
  const cells: CalendarCell[] = []
  const months = new Map<number, string>()
  for (let week = 0; week < weeks; week += 1) {
    const weekDate = new Date(firstMonday + week * 7 * 86400000)
    const label = weekDate.toLocaleDateString('zh-CN', { timeZone: 'UTC', month: 'short' })
    const previous = week > 0 ? new Date(firstMonday + (week - 1) * 7 * 86400000) : null
    if (!previous || previous.getUTCMonth() !== weekDate.getUTCMonth()) months.set(week, label)
    for (let day = 0; day < 7; day += 1) {
      const time = firstMonday + (week * 7 + day) * 86400000
      if (time < start || time >= end) continue
      const date = new Date(time).toISOString().slice(0, 10)
      const point = byDate.get(date)
      const observed = point?.value ?? point?.observedValue ?? null
      const intensity = observed === null ? 0 : Math.min(4, Math.max(1, Math.ceil(observed / max * 4)))
      const state = !point || (point.value === null && point.observedValue == null)
        ? 'missing'
        : point.value === null ? 'partial' : point.value === 0 ? 'zero' : 'complete'
      cells.push({ date, week, day, point, commitCount: observed, intensity, state })
    }
  }
  return { weeks, cells, months: [...months].map(([week, label]) => ({ week, label })) }
})
const themePalette = computed(() => ui.isDark
  ? ['#252b31', '#274233', '#31573d', '#3c7548', '#4c9958']
  : ['#edf0f2', '#d9eadc', '#afd3b4', '#79b681', '#3f9251'])
const maxCommitCount = computed(() => Math.max(0, ...calendar.value.cells.flatMap((cell) => cell.commitCount === null ? [] : [cell.commitCount])))
const sliderMax = computed(() => Math.max(1, maxCommitCount.value))
const minimumCommitCount = ref(0)
const maximumCommitCount = ref(0)
const selectedRange = computed(() => ({
  min: Math.min(minimumCommitCount.value, maximumCommitCount.value),
  max: Math.max(minimumCommitCount.value, maximumCommitCount.value),
}))
const archivedDays = computed(() => calendar.value.cells.filter((cell) => cell.commitCount !== null).length)
const matchingDays = computed(() => calendar.value.cells.filter((cell) => cell.commitCount !== null && !isFilteredOut(cell)).length)

watch(maxCommitCount, (maximum) => {
  minimumCommitCount.value = 0
  maximumCommitCount.value = maximum
}, { immediate: true })

function isFilteredOut(cell: CalendarCell) {
  if (cell.commitCount === null) return false
  return cell.commitCount < selectedRange.value.min || cell.commitCount > selectedRange.value.max
}

function setMinimumCommitCount(event: Event) {
  const value = Number((event.target as HTMLInputElement).value)
  minimumCommitCount.value = Math.min(value, selectedRange.value.max)
}

function setMaximumCommitCount(event: Event) {
  const value = Number((event.target as HTMLInputElement).value)
  maximumCommitCount.value = Math.max(value, selectedRange.value.min)
}

function resetCommitRange() {
  minimumCommitCount.value = 0
  maximumCommitCount.value = maxCommitCount.value
}

const cellSize = computed(() => Math.max(14, Math.min(34, Math.floor((props.height - 50) / 7))))
function cellStyle(cell: CalendarCell) {
  if (cell.state === 'missing') return { background: themePalette.value[0] }
  if (isFilteredOut(cell)) return { background: themePalette.value[0], opacity: 0.38 }
  if (cell.state === 'partial') return { background: 'color-mix(in srgb, #d58b31 30%, var(--surface-soft))', outline: '1px dashed #d58b31' }
  return { background: themePalette.value[cell.state === 'zero' ? 0 : cell.intensity] }
}
function cellLabel(cell: CalendarCell) {
  const point = cell.point
  const filteredLabel = isFilteredOut(cell) ? `，低于或高于当前 ${props.metricLabel} 数范围` : ''
  if (!point) return `${cell.date}：未采集${filteredLabel}`
  if (point.value !== null) return `${cell.date}：${point.value} 个${point.quality ? `，${point.quality}` : ''}${filteredLabel}`
  if (point.observedValue !== null && point.observedValue !== undefined) return `${cell.date}：已观察 ${point.observedValue} 个，覆盖不完整${filteredLabel}`
  return `${cell.date}：${point.quality ?? '数据缺失'}${filteredLabel}`
}
</script>

<template>
  <div v-if="calendar.weeks" class="calendar-heatmap">
    <div class="calendar-filter">
      <div class="calendar-filter__summary">
        <strong>{{ metricLabel }}数 {{ selectedRange.min }}–{{ selectedRange.max }} 个</strong>
        <span>匹配 {{ matchingDays }} / {{ archivedDays }} 个有数据的日期</span>
        <button v-if="selectedRange.min > 0 || selectedRange.max < maxCommitCount" type="button" @click="resetCommitRange">重置</button>
      </div>
      <div class="calendar-filter__sliders">
        <label><span>最少 {{ minimumCommitCount }}</span><input type="range" min="0" :max="sliderMax" :value="minimumCommitCount" :aria-label="`最少每日 ${metricLabel} 数`" @input="setMinimumCommitCount" /></label>
        <label><span>最多 {{ maximumCommitCount }}</span><input type="range" min="0" :max="sliderMax" :value="maximumCommitCount" :aria-label="`最多每日 ${metricLabel} 数`" @input="setMaximumCommitCount" /></label>
      </div>
    </div>
    <div class="calendar-scroll" role="grid" :aria-label="`UTC 日历热力图，筛选 ${selectedRange.min} 到 ${selectedRange.max} 个每日 ${metricLabel}；颜色深浅表示数量，虚线框表示部分覆盖`" :style="{ maxHeight: `${height}px`, '--calendar-cell-size': `${cellSize}px` }">
      <div class="calendar-weekdays" aria-hidden="true"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div>
      <div class="calendar-body" :style="{ gridTemplateColumns: `repeat(${calendar.weeks}, var(--calendar-cell-size))`, minWidth: `${calendar.weeks * cellSize + (calendar.weeks - 1) * 3}px` }">
        <span v-for="month in calendar.months" :key="month.week" class="calendar-month" :style="{ gridColumn: month.week + 1 }">{{ month.label }}</span>
        <span v-for="cell in calendar.cells" :key="cell.date" role="gridcell" class="calendar-cell" :class="[`calendar-cell--${cell.state}`, isFilteredOut(cell) && 'calendar-cell--filtered']" :style="{ gridColumn: cell.week + 1, gridRow: cell.day + 2, ...cellStyle(cell) }" :aria-label="cellLabel(cell)" :title="cellLabel(cell)" />
      </div>
    </div>
  </div>
  <div v-else class="calendar-empty" :style="{ minHeight: `${height}px` }">无法确定采集窗口，暂不绘制日历。</div>
</template>

<style scoped>
.calendar-heatmap { display:flex; min-width:0; flex-direction:column; gap:7px; }
.calendar-filter { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:5px 12px; color:var(--muted); font-size:10px; }
.calendar-filter__summary { display:flex; flex-wrap:wrap; align-items:center; gap:4px 9px; }
.calendar-filter__summary strong { color:var(--ink); font-weight:600; }
.calendar-filter__summary button { border:0; padding:0; color:var(--primary-ink); background:transparent; font-size:10px; text-decoration:underline; cursor:pointer; }
.calendar-filter__sliders { display:flex; flex:1 1 260px; justify-content:flex-end; gap:10px; max-width:520px; }
.calendar-filter__sliders label { display:flex; min-width:100px; flex:1; align-items:center; gap:6px; white-space:nowrap; }
.calendar-filter__sliders input { width:100%; min-width:44px; height:14px; margin:0; accent-color:var(--green); cursor:pointer; }
.calendar-scroll { display:grid; grid-template-columns:18px minmax(0,1fr); gap:7px; overflow:auto; padding:3px; width:100%; }
.calendar-weekdays { display:grid; grid-template-rows:repeat(7,var(--calendar-cell-size)); gap:3px; color:var(--muted); font-size:10px; text-align:center; }
.calendar-body { display:grid; grid-template-rows:16px repeat(7,var(--calendar-cell-size)); grid-auto-flow:column; gap:3px; }
.calendar-cell { aspect-ratio:1; }
.calendar-month { align-self:end; color:var(--muted); font-size:10px; white-space:nowrap; }
.calendar-cell--filtered { outline-color:color-mix(in srgb,var(--line) 50%,transparent); }
.calendar-cell--partial { outline:1px dashed #d58b31 !important; }
.calendar-empty { display:grid; place-items:center; color:var(--muted); font-size:11px; }
@media (max-width: 640px) { .calendar-filter__sliders { flex-basis:100%; max-width:none; } }
</style>
