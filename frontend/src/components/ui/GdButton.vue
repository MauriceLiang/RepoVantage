<script setup lang="ts">
import { LoaderCircle } from 'lucide-vue-next'

withDefaults(defineProps<{ variant?: 'primary' | 'outline' | 'ghost' | 'danger'; size?: 'sm' | 'md'; disabled?: boolean; loading?: boolean }>(), {
  variant: 'primary', size: 'md', disabled: false, loading: false,
})
</script>

<template>
  <button
    :disabled="disabled || loading"
    :aria-busy="loading"
    class="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-[var(--gd-radius-control)] font-medium transition-[color,background-color,border-color,opacity,transform,scale,box-shadow] duration-200 disabled:cursor-not-allowed"
    :class="[
      size === 'sm' ? 'h-7 px-2.5 text-[12px]' : 'h-[34px] px-3.5 text-[13px]',
      (variant === 'primary' || variant === 'danger') && 'bg-[var(--gd-primary-button)] text-white shadow-sm hover:bg-[var(--gd-primary-button-hover)] hover:shadow-md disabled:bg-[var(--gd-primary-button-disabled)] disabled:text-white disabled:shadow-none',
      variant === 'outline' && 'border border-line bg-panel hover:bg-soft disabled:opacity-45',
      variant === 'ghost' && 'text-muted hover:bg-track hover:text-ink disabled:opacity-45',
    ]"
  >
    <LoaderCircle v-if="loading" :size="14" class="shrink-0 animate-spin" aria-hidden="true" />
    <slot />
  </button>
</template>
