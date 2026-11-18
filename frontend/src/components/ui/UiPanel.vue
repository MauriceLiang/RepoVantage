<script setup lang="ts">
withDefaults(defineProps<{
  as?: 'div' | 'section' | 'article' | 'aside'
  tight?: boolean
}>(), { as: 'div', tight: false })
</script>

<template>
  <component :is="as" class="panel" :class="{ 'panel--tight': tight }">
    <slot />
  </component>
</template>
