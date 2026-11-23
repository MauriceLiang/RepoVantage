<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps<{
  min: number
  max: number
  startValue: number
  endValue: number
  rangeLabel: string
  startLabel: string
  endLabel: string
}>()
const emit = defineEmits<{
  'update:startValue': [value: number]
  'update:endValue': [value: number]
}>()

const rail = ref<HTMLDivElement | null>(null)
const draggingHandle = ref<'start' | 'end' | null>(null)
const draftStart = ref(props.startValue)
const draftEnd = ref(props.endValue)
const span = computed(() => Math.max(0, props.max - props.min))
const hasRange = computed(() => span.value > 0)
const startPercent = computed(() => span.value ? (draftStart.value - props.min) / span.value * 100 : 0)
const endPercent = computed(() => span.value ? (draftEnd.value - props.min) / span.value * 100 : 100)

watch(() => [props.min, props.max, props.startValue, props.endValue], ([min, max, start, end]) => {
  if (draggingHandle.value) return
  const lower = Number(min)
  const upper = Math.max(lower, Number(max))
  draftStart.value = Math.max(lower, Math.min(upper, Number(start)))
  draftEnd.value = Math.max(draftStart.value, Math.min(upper, Number(end)))
}, { immediate: true })

function syncDraftFromProps() {
  draftStart.value = props.startValue
  draftEnd.value = props.endValue
}

function setDraft(handle: 'start' | 'end', value: number) {
  const next = Math.max(props.min, Math.min(props.max, Math.round(value)))
  if (handle === 'start') draftStart.value = Math.min(next, draftEnd.value)
  else draftEnd.value = Math.max(next, draftStart.value)
}

function valueAtPointer(event: PointerEvent) {
  const bounds = rail.value?.getBoundingClientRect()
  if (!bounds || !bounds.width || !hasRange.value) return props.min
  return props.min + ((event.clientX - bounds.left) / bounds.width) * span.value
}

function beginHandleDrag(handle: 'start' | 'end', event: PointerEvent) {
  if (!hasRange.value) return
  event.preventDefault()
  syncDraftFromProps()
  draggingHandle.value = handle
  rail.value?.setPointerCapture(event.pointerId)
}

function beginTrackDrag(event: PointerEvent) {
  if (!hasRange.value) return
  event.preventDefault()
  syncDraftFromProps()
  const value = valueAtPointer(event)
  const handle = Math.abs(value - draftStart.value) <= Math.abs(value - draftEnd.value) ? 'start' : 'end'
  draggingHandle.value = handle
  setDraft(handle, value)
  rail.value?.setPointerCapture(event.pointerId)
}

function commitRange() {
  if (draftStart.value !== props.startValue) emit('update:startValue', draftStart.value)
  if (draftEnd.value !== props.endValue) emit('update:endValue', draftEnd.value)
}

function moveHandleDrag(event: PointerEvent) {
  if (draggingHandle.value) setDraft(draggingHandle.value, valueAtPointer(event))
}

function endHandleDrag(event: PointerEvent) {
  if (!draggingHandle.value) return
  const target = rail.value
  draggingHandle.value = null
  commitRange()
  if (target?.hasPointerCapture(event.pointerId)) target.releasePointerCapture(event.pointerId)
}

function moveHandleByKeyboard(handle: 'start' | 'end', event: KeyboardEvent) {
  const step = event.key === 'PageUp' || event.key === 'PageDown' ? Math.max(1, Math.round(span.value / 10)) : event.shiftKey ? 5 : 1
  syncDraftFromProps()
  let next = handle === 'start' ? draftStart.value : draftEnd.value
  if (event.key === 'ArrowRight' || event.key === 'ArrowUp' || event.key === 'PageUp') next += step
  else if (event.key === 'ArrowLeft' || event.key === 'ArrowDown' || event.key === 'PageDown') next -= step
  else if (event.key === 'Home') next = handle === 'start' ? props.min : draftStart.value
  else if (event.key === 'End') next = handle === 'start' ? draftEnd.value : props.max
  else return
  event.preventDefault()
  setDraft(handle, next)
  commitRange()
}
</script>

<template>
  <div class="number-range-slider" role="group" :aria-label="`${rangeLabel}，可拖动两端滑块调整`">
    <span class="number-range-slider__value"><span>{{ startLabel }}</span><strong>{{ draftStart }}</strong></span>
    <div
      ref="rail"
      class="number-range-slider__rail"
      @pointerdown="beginTrackDrag"
      @pointermove="moveHandleDrag"
      @pointerup="endHandleDrag"
      @pointercancel="endHandleDrag"
      @lostpointercapture="endHandleDrag"
    >
      <div class="number-range-slider__track" aria-hidden="true" />
      <div class="number-range-slider__selection" aria-hidden="true" :style="{ left: `${startPercent}%`, width: `${endPercent - startPercent}%` }" />
      <button
        type="button"
        role="slider"
        class="number-range-slider__thumb number-range-slider__thumb--start"
        :style="{ left: `${startPercent}%` }"
        :aria-label="`${rangeLabel}${startLabel}`"
        :aria-valuemin="min"
        :aria-valuemax="draftEnd"
        :aria-valuenow="draftStart"
        :disabled="!hasRange"
        @pointerdown.stop="beginHandleDrag('start', $event)"
        @keydown="moveHandleByKeyboard('start', $event)"
      />
      <button
        type="button"
        role="slider"
        class="number-range-slider__thumb number-range-slider__thumb--end"
        :style="{ left: `${endPercent}%` }"
        :aria-label="`${rangeLabel}${endLabel}`"
        :aria-valuemin="draftStart"
        :aria-valuemax="max"
        :aria-valuenow="draftEnd"
        :disabled="!hasRange"
        @pointerdown.stop="beginHandleDrag('end', $event)"
        @keydown="moveHandleByKeyboard('end', $event)"
      />
    </div>
    <span class="number-range-slider__value"><span>{{ endLabel }}</span><strong>{{ draftEnd }}</strong></span>
    <div class="number-range-slider__limits" aria-hidden="true"><span>{{ min }}</span><span>{{ max }}</span></div>
  </div>
</template>

<style scoped>
.number-range-slider { display:grid; width:100%; grid-template-columns:max-content minmax(56px,1fr) max-content; align-items:center; column-gap:8px; min-width:0; color:var(--muted); font-size:10px; }
.number-range-slider__value { display:flex; align-items:baseline; gap:4px; white-space:nowrap; }
.number-range-slider__value strong { color:var(--ink); font-size:10.5px; font-weight:600; font-variant-numeric:tabular-nums; }
.number-range-slider__rail { position:relative; height:var(--range-slider-rail-height); margin:0 8px; touch-action:none; user-select:none; cursor:pointer; }
.number-range-slider__track, .number-range-slider__selection { position:absolute; top:calc((var(--range-slider-rail-height) - var(--range-slider-track-height)) / 2); height:var(--range-slider-track-height); border-radius:999px; }
.number-range-slider__track { inset-inline:0; background:var(--line); }
.number-range-slider__selection { background:var(--primary,#2563eb); }
.number-range-slider__thumb { position:absolute; z-index:1; top:calc((var(--range-slider-rail-height) - var(--range-slider-thumb-size)) / 2); width:var(--range-slider-thumb-size); height:var(--range-slider-thumb-size); padding:0; border:2px solid var(--surface); border-radius:50%; background:var(--primary,#2563eb); box-shadow:0 0 0 1px var(--line), 0 1px 3px rgb(20 25 30 / 20%); transform:translateX(-50%); cursor:grab; }
.number-range-slider__thumb:active { cursor:grabbing; }
.number-range-slider__thumb:focus-visible { outline:2px solid var(--primary,#2563eb); outline-offset:3px; }
.number-range-slider__thumb:disabled { cursor:not-allowed; opacity:.55; }
.number-range-slider__limits { grid-column:2; display:flex; justify-content:space-between; margin:0 8px; color:var(--muted); font-size:9px; font-variant-numeric:tabular-nums; }
</style>
