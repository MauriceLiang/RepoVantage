<script setup lang="ts">
withDefaults(defineProps<{
  tone?: 'neutral' | 'accent' | 'success' | 'warning' | 'danger'
}>(), { tone: 'neutral' })
</script>

<template>
  <span class="badge" :class="tone === 'neutral' ? '' : `badge--${tone}`">
    <slot />
  </span>
</template>
