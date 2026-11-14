<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

interface Option { value: string | number; label: string; disabled?: boolean; hint?: string }
const props = withDefaults(defineProps<{ modelValue: string | number; options: Option[]; size?: 'sm' | 'md' }>(), { size: 'md' })
const emit = defineEmits<{ 'update:modelValue': [value: string | number] }>()
const root = ref<HTMLDivElement | null>(null)
const indicator = ref({ x: 0, width: 0, visible: false })
let observer: ResizeObserver | null = null

async function positionIndicator() {
  await nextTick()
  const active = root.value?.querySelector<HTMLButtonElement>('[aria-pressed="true"]')
  if (!active) {
    indicator.value.visible = false
    return
  }
  indicator.value = { x: active.offsetLeft, width: active.offsetWidth, visible: true }
}

watch(() => [props.modelValue, props.options.length, props.size], positionIndicator)
onMounted(() => {
  void positionIndicator()
  if (root.value) {
    observer = new ResizeObserver(() => void positionIndicator())
    observer.observe(root.value)
  }
})
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div ref="root" class="relative flex shrink-0 gap-0.5 rounded-[var(--gd-radius-control)] bg-track p-[3px]" role="group">
    <span
      class="gd-segment-indicator absolute bottom-[3px] left-0 top-[3px] rounded-[6px] bg-panel shadow-sm"
      :class="indicator.visible ? 'opacity-100' : 'opacity-0'"
      :style="{ width: `${indicator.width}px`, transform: `translateX(${indicator.x}px)` }"
      aria-hidden="true"
    />
    <button
      v-for="option in options"
      :key="option.value"
      :disabled="option.disabled"
      :title="option.hint"
      :aria-label="option.label"
      :aria-pressed="modelValue === option.value"
      :data-value="option.value"
      class="relative z-[1] rounded-[6px] font-medium transition-colors duration-200 disabled:cursor-not-allowed disabled:opacity-45"
      :class="[
        size === 'sm' ? 'h-6 px-2 text-[11.5px]' : 'h-[26px] px-2.5 text-[12.5px]',
        modelValue === option.value ? 'text-ink' : 'text-muted hover:text-ink',
      ]"
      @click="emit('update:modelValue', option.value)"
    >
      {{ option.label }}
    </button>
  </div>
</template>
