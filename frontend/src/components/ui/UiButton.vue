<script setup lang="ts">
import { LoaderCircle } from 'lucide-vue-next'

withDefaults(defineProps<{
  variant?: 'primary' | 'outline' | 'quiet' | 'danger'
  type?: 'button' | 'submit' | 'reset'
  disabled?: boolean
  loading?: boolean
}>(), {
  variant: 'outline',
  type: 'button',
  disabled: false,
  loading: false,
})
</script>

<template>
  <button
    class="button"
    :class="`button--${variant}`"
    :type="type"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
  >
    <LoaderCircle v-if="loading" class="button__spinner" :size="13" aria-hidden="true" />
    <slot />
  </button>
</template>
