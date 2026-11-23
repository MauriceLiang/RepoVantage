<script setup lang="ts">
const props = withDefaults(defineProps<{
  modelValue?: string | number
  modelModifiers?: { number?: boolean }
  size?: 'sm' | 'md'
  invalid?: boolean
}>(), { modelValue: '', size: 'md', invalid: false })

const emit = defineEmits<{ 'update:modelValue': [value: string | number] }>()

function updateValue(event: Event) {
  const value = (event.target as HTMLInputElement).value
  if (!props.modelModifiers?.number || value === '') {
    emit('update:modelValue', value)
    return
  }
  const numericValue = Number(value)
  emit('update:modelValue', Number.isNaN(numericValue) ? value : numericValue)
}
</script>

<template>
  <input
    class="field"
    :class="[`field--${size}`, { 'field--invalid': invalid }]"
    :value="modelValue"
    :aria-invalid="invalid || undefined"
    @input="updateValue"
  />
</template>
