<script setup lang="ts">
withDefaults(defineProps<{ modelValue: string; placeholder?: string; invalid?: boolean; size?: 'sm' | 'md' }>(), {
  placeholder: '', invalid: false, size: 'md',
})
defineEmits<{ 'update:modelValue': [value: string]; enter: [] }>()
</script>

<template>
  <div
    class="flex items-center gap-2 rounded-[var(--gd-radius-control)] border bg-panel px-3 transition-[border-color,box-shadow,background-color] duration-200"
    :class="[size === 'sm' ? 'h-[38px]' : 'h-11', invalid ? 'border-danger ring-3 ring-danger/12' : 'border-line focus-within:border-s1/55 focus-within:shadow-sm']"
  >
    <slot name="icon" />
    <input
      :value="modelValue"
      :placeholder="placeholder"
      class="h-full min-w-0 flex-1 bg-transparent text-[13.5px] outline-none placeholder:text-muted"
      @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      @keydown.enter="$emit('enter')"
    />
    <slot name="trailing" />
  </div>
</template>
