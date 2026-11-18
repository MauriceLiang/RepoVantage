<script setup lang="ts">
import type { Component } from 'vue'

defineProps<{ id: string; label: string; icon: Component; active: boolean; to?: string }>()
const emit = defineEmits<{ select: [id: string] }>()
</script>

<template>
  <RouterLink
    v-if="to"
    :to="to"
    class="nav-link"
    :class="{ 'nav-link--active': active }"
    :aria-current="active ? 'page' : undefined"
    @click="emit('select', id)"
  >
    <span class="nav-icon"><component :is="icon" :size="17" :stroke-width="1.8" /></span>
    {{ label }}
  </RouterLink>
  <button
    v-else
    type="button"
    class="nav-link"
    :class="{ 'nav-link--active': active }"
    :aria-current="active ? 'page' : undefined"
    @click="emit('select', id)"
  >
    <span class="nav-icon"><component :is="icon" :size="17" :stroke-width="1.8" /></span>
    {{ label }}
  </button>
</template>
