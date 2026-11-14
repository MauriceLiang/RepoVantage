<script setup lang="ts">
withDefaults(defineProps<{ variant?: 'default' | 'warn' | 'plain' | 'danger' }>(), { variant: 'default' })
const styles: Record<string, string> = {
  default: 'bg-soft text-ink/70',
  warn: 'bg-warnbg text-warnfg',
  plain: 'bg-soft text-muted',
  danger: 'bg-warnbg text-danger',
}
</script>

<template>
  <span class="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium transition-[color,background-color,border-color] duration-200" :class="styles[variant]">
    <slot />
  </span>
</template>
