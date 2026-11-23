<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  minDate: string
  maxDate: string
  startDate: string
  endDate: string
  rangeLabel?: string
  resetDays?: number
}>(), { rangeLabel: '日期范围', resetDays: 90 })
const emit = defineEmits<{
  'update:startDate': [date: string]
  'update:endDate': [date: string]
}>()

const DAY = 86_400_000
const sliderRail = ref<HTMLDivElement | null>(null)
const draggingHandle = ref<'start' | 'end' | null>(null)
const minTimestamp = computed(() => props.minDate ? Date.parse(`${props.minDate}T00:00:00Z`) : 0)
const maxTimestamp = computed(() => props.maxDate ? Date.parse(`${props.maxDate}T00:00:00Z`) : 0)
const sliderMax = computed(() => props.minDate && props.maxDate
  ? Math.max(0, Math.round((maxTimestamp.value - minTimestamp.value) / DAY))
  : 0)
const committedStartOffset = computed(() => props.startDate ? Math.round((Date.parse(`${props.startDate}T00:00:00Z`) - minTimestamp.value) / DAY) : 0)
const committedEndOffset = computed(() => props.endDate ? Math.round((Date.parse(`${props.endDate}T00:00:00Z`) - minTimestamp.value) / DAY) : sliderMax.value)
const draftStartOffset = ref(0)
const draftEndOffset = ref(0)
const startPercent = computed(() => sliderMax.value ? draftStartOffset.value / sliderMax.value * 100 : 0)
const endPercent = computed(() => sliderMax.value ? draftEndOffset.value / sliderMax.value * 100 : 100)
const draftStartDate = computed(() => props.minDate && props.startDate ? dateAtOffset(draftStartOffset.value) : '')
const draftEndDate = computed(() => props.minDate && props.endDate ? dateAtOffset(draftEndOffset.value) : '')
const hasRange = computed(() => Boolean(props.minDate && props.maxDate && sliderMax.value > 0))

watch([committedStartOffset, committedEndOffset], ([start, end]) => {
  if (draggingHandle.value) return
  draftStartOffset.value = start
  draftEndOffset.value = end
}, { immediate: true })

function dateAtOffset(offset: number) {
  return new Date(minTimestamp.value + offset * DAY).toISOString().slice(0, 10)
}

function setDraftHandleOffset(handle: 'start' | 'end', value: number) {
  const offset = Math.max(0, Math.min(sliderMax.value, Math.round(value)))
  if (handle === 'start') draftStartOffset.value = Math.min(offset, draftEndOffset.value)
  else draftEndOffset.value = Math.max(offset, draftStartOffset.value)
}

function commitRange() {
  const nextStart = dateAtOffset(draftStartOffset.value)
  const nextEnd = dateAtOffset(draftEndOffset.value)
  if (nextStart !== props.startDate) emit('update:startDate', nextStart)
  if (nextEnd !== props.endDate) emit('update:endDate', nextEnd)
}

function offsetAtPointer(event: PointerEvent) {
  const rail = sliderRail.value
  if (!rail || sliderMax.value === 0) return 0
  const bounds = rail.getBoundingClientRect()
  return Math.max(0, Math.min(sliderMax.value, ((event.clientX - bounds.left) / bounds.width) * sliderMax.value))
}

function beginHandleDrag(handle: 'start' | 'end', event: PointerEvent) {
  if (!hasRange.value) return
  event.preventDefault()
  draftStartOffset.value = committedStartOffset.value
  draftEndOffset.value = committedEndOffset.value
  draggingHandle.value = handle
  sliderRail.value?.setPointerCapture(event.pointerId)
}

function beginTrackDrag(event: PointerEvent) {
  if (!hasRange.value) return
  draftStartOffset.value = committedStartOffset.value
  draftEndOffset.value = committedEndOffset.value
  const offset = offsetAtPointer(event)
  const handle = Math.abs(offset - draftStartOffset.value) <= Math.abs(offset - draftEndOffset.value) ? 'start' : 'end'
  draggingHandle.value = handle
  setDraftHandleOffset(handle, offset)
  sliderRail.value?.setPointerCapture(event.pointerId)
}

function moveHandleDrag(event: PointerEvent) {
  if (draggingHandle.value) setDraftHandleOffset(draggingHandle.value, offsetAtPointer(event))
}

function endHandleDrag(event: PointerEvent) {
  if (!draggingHandle.value) return
  const rail = sliderRail.value
  draggingHandle.value = null
  commitRange()
  if (rail?.hasPointerCapture(event.pointerId)) rail.releasePointerCapture(event.pointerId)
}

function moveHandleByKeyboard(handle: 'start' | 'end', event: KeyboardEvent) {
  const step = event.key === 'PageUp' || event.key === 'PageDown' ? 30 : event.shiftKey ? 7 : 1
  draftStartOffset.value = committedStartOffset.value
  draftEndOffset.value = committedEndOffset.value
  let next = handle === 'start' ? draftStartOffset.value : draftEndOffset.value
  if (event.key === 'ArrowRight' || event.key === 'ArrowUp' || event.key === 'PageUp') next += step
  else if (event.key === 'ArrowLeft' || event.key === 'ArrowDown' || event.key === 'PageDown') next -= step
  else if (event.key === 'Home') next = handle === 'start' ? 0 : draftStartOffset.value
  else if (event.key === 'End') next = handle === 'start' ? draftEndOffset.value : sliderMax.value
  else return
  event.preventDefault()
  setDraftHandleOffset(handle, next)
  commitRange()
}

function resetRange() {
  if (!props.minDate || !props.maxDate) return
  const latest = maxTimestamp.value
  const nextStart = Math.max(minTimestamp.value, latest - props.resetDays * DAY)
  draftStartOffset.value = Math.round((nextStart - minTimestamp.value) / DAY)
  draftEndOffset.value = sliderMax.value
  commitRange()
}
</script>

<template>
  <div class="date-range-slider" data-testid="date-range-slider">
    <div class="date-range-slider__values">
      <span><span class="date-range-slider__label">起始日期</span><strong>{{ draftStartDate || '—' }}</strong></span>
      <span><span class="date-range-slider__label">结束日期</span><strong>{{ draftEndDate || '—' }}</strong></span>
      <button type="button" :disabled="!minDate || !maxDate" @click="resetRange">重置近 {{ resetDays }} 天</button>
    </div>
    <div
      ref="sliderRail"
      class="date-range-slider__rail"
      role="group"
      :aria-label="`${rangeLabel}，可拖动两端滑块调整`"
      @pointerdown="beginTrackDrag"
      @pointermove="moveHandleDrag"
      @pointerup="endHandleDrag"
      @pointercancel="endHandleDrag"
      @lostpointercapture="endHandleDrag"
    >
      <div class="date-range-slider__track" aria-hidden="true" />
      <div class="date-range-slider__selection" aria-hidden="true" :style="{ left: `${startPercent}%`, width: `${endPercent - startPercent}%` }" />
      <button
        type="button"
        role="slider"
        class="date-range-slider__thumb date-range-slider__thumb--start"
        :style="{ left: `${startPercent}%` }"
        aria-label="时间范围起始日期"
        :aria-valuemin="0"
        :aria-valuemax="draftEndOffset"
        :aria-valuenow="draftStartOffset"
        :aria-valuetext="draftStartDate || '无日期'"
        :disabled="!hasRange"
        @pointerdown.stop="beginHandleDrag('start', $event)"
        @keydown="moveHandleByKeyboard('start', $event)"
      />
      <button
        type="button"
        role="slider"
        class="date-range-slider__thumb date-range-slider__thumb--end"
        :style="{ left: `${endPercent}%` }"
        aria-label="时间范围结束日期"
        :aria-valuemin="draftStartOffset"
        :aria-valuemax="sliderMax"
        :aria-valuenow="draftEndOffset"
        :aria-valuetext="draftEndDate || '无日期'"
        :disabled="!hasRange"
        @pointerdown.stop="beginHandleDrag('end', $event)"
        @keydown="moveHandleByKeyboard('end', $event)"
      />
    </div>
    <div class="date-range-slider__limits" aria-hidden="true"><span>{{ minDate || '—' }}</span><span>{{ maxDate || '—' }}</span></div>
  </div>
</template>

<style scoped>
.date-range-slider { display:grid; gap:4px; min-width:0; color:var(--muted); font-size:10px; }
.date-range-slider__values { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:6px 14px; }
.date-range-slider__values > span { display:flex; align-items:baseline; gap:5px; white-space:nowrap; }
.date-range-slider__values strong { color:var(--ink); font-size:10.5px; font-weight:600; font-variant-numeric:tabular-nums; }
.date-range-slider__label { color:var(--muted); }
.date-range-slider__values button { border:0; background:transparent; color:var(--accent,#2e8fcb); text-decoration:underline; cursor:pointer; }
.date-range-slider__values button:disabled { cursor:not-allowed; opacity:.55; }
.date-range-slider__rail { position:relative; height:24px; margin:0 10px; touch-action:none; user-select:none; cursor:pointer; }
.date-range-slider__track, .date-range-slider__selection { position:absolute; top:10px; height:4px; border-radius:999px; }
.date-range-slider__track { inset-inline:0; background:var(--line); }
.date-range-slider__selection { background:var(--primary,#2563eb); }
.date-range-slider__thumb { position:absolute; z-index:1; top:3px; width:18px; height:18px; padding:0; border:2px solid var(--surface); border-radius:50%; background:var(--primary,#2563eb); box-shadow:0 0 0 1px var(--line), 0 1px 3px rgb(20 25 30 / 20%); transform:translateX(-50%); cursor:grab; }
.date-range-slider__thumb:active { cursor:grabbing; }
.date-range-slider__thumb:focus-visible { outline:2px solid var(--primary,#2563eb); outline-offset:3px; }
.date-range-slider__thumb:disabled { cursor:not-allowed; opacity:.55; }
.date-range-slider__limits { display:flex; justify-content:space-between; color:var(--muted); font-size:9px; font-variant-numeric:tabular-nums; }
</style>
