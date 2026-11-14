<script setup lang="ts">
defineProps<{ label: string; value: string | number; note?: string }>()
</script>

<template>
  <div class="kpi">
    <div class="kpi-label"><slot name="icon" />{{ label }}</div>
    <div class="kpi-value"><slot name="value">{{ value }}</slot></div>
    <div v-if="note || $slots.note" class="kpi-note"><slot name="note">{{ note }}</slot></div>
  </div>
</template>
