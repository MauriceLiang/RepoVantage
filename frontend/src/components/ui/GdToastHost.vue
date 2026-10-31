<script setup lang="ts">
import { useUiStore } from '@/stores/ui'
const ui = useUiStore()
</script>

<template>
  <Teleport to="body">
    <div class="pointer-events-none fixed left-1/2 top-16 z-[80] flex w-[min(90vw,520px)] -translate-x-1/2 flex-col items-center gap-2">
      <TransitionGroup name="toast">
        <div
          v-for="item in ui.toasts"
          :key="item.id"
          :class="['toast-card', `toast-${item.status}`]"
          :role="item.status === 'error' ? 'alert' : 'status'"
          aria-atomic="true"
        >
          {{ item.message }}
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-enter-active, .toast-leave-active { transition: all 0.18s ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(-6px); }
.toast-card { max-width: 100%; border: 1px solid transparent; border-radius: 0.5rem; padding: 0.625rem 0.875rem; text-align: center; font-size: 12.5px; line-height: 1.5; box-shadow: var(--gd-shadow); }
.toast-success { background: var(--gd-toast-success-bg); color: var(--gd-toast-success-fg); border-color: color-mix(in srgb, var(--gd-toast-success-fg) 24%, transparent); }
.toast-warning { background: var(--gd-warn-bg); color: var(--gd-warn-fg); border-color: color-mix(in srgb, var(--gd-warn-fg) 24%, transparent); }
.toast-error { background: var(--gd-toast-error-bg); color: var(--gd-toast-error-fg); border-color: color-mix(in srgb, var(--gd-toast-error-fg) 24%, transparent); }
</style>
