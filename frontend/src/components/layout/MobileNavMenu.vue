<script setup lang="ts">
import { Menu, X } from 'lucide-vue-next'
import { DialogClose, DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle, DialogTrigger, VisuallyHidden } from 'reka-ui'
import { useRoute } from 'vue-router'
import { primaryNavigation } from './navigation'

const route = useRoute()
</script>

<template>
  <DialogRoot>
    <DialogTrigger as-child>
      <button type="button" class="grid size-9 shrink-0 place-items-center rounded-lg text-muted transition-colors hover:bg-track hover:text-ink lg:hidden" aria-label="打开主导航">
        <Menu :size="19" />
      </button>
    </DialogTrigger>
    <DialogPortal>
      <DialogOverlay class="mobile-nav-overlay fixed inset-0 z-40 bg-black/30" />
      <DialogContent class="mobile-nav-panel fixed inset-y-0 left-0 z-50 flex w-[min(82vw,300px)] flex-col border-r border-line bg-panel p-4 shadow-[12px_0_36px_rgb(0_0_0/0.12)]">
        <header class="flex items-center justify-between gap-3 border-b border-line pb-4">
          <DialogTitle class="flex items-center gap-2 text-[14px] font-semibold">
            <img src="/repovantage-icon.png" alt="" class="size-7 object-contain" />
            RepoVantage
          </DialogTitle>
          <VisuallyHidden><DialogDescription>选择要打开的页面</DialogDescription></VisuallyHidden>
          <DialogClose as-child>
            <button type="button" class="grid size-8 place-items-center rounded-lg text-muted transition-colors hover:bg-track hover:text-ink" aria-label="关闭主导航"><X :size="17" /></button>
          </DialogClose>
        </header>
        <nav class="mt-5 flex flex-col gap-1" aria-label="主导航">
          <DialogClose v-for="item in primaryNavigation" :key="item.key" as-child>
            <RouterLink
              :to="item.to"
              :aria-current="route.meta.nav === item.key ? 'page' : undefined"
              class="flex min-h-11 items-center gap-3 rounded-lg px-3 text-[14px] transition-[color,background-color] duration-200"
              :class="route.meta.nav === item.key ? 'bg-soft font-semibold text-ink' : 'text-muted hover:bg-track hover:text-ink'"
            >
              <component :is="item.icon" :size="19" :stroke-width="1.8" />
              {{ item.label }}
            </RouterLink>
          </DialogClose>
        </nav>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.mobile-nav-overlay[data-state='open'] { animation: mobile-overlay-in 220ms ease both; }
.mobile-nav-overlay[data-state='closed'] { animation: mobile-overlay-out 180ms ease both; }
.mobile-nav-panel[data-state='open'] { animation: mobile-panel-in 280ms var(--gd-ease-emphasized) both; }
.mobile-nav-panel[data-state='closed'] { animation: mobile-panel-out 200ms var(--gd-ease-standard) both; }
@keyframes mobile-overlay-in { from { opacity: 0; } to { opacity: 1; } }
@keyframes mobile-overlay-out { from { opacity: 1; } to { opacity: 0; } }
@keyframes mobile-panel-in { from { opacity: 0; transform: translateX(-12px); } to { opacity: 1; transform: translateX(0); } }
@keyframes mobile-panel-out { from { opacity: 1; transform: translateX(0); } to { opacity: 0; transform: translateX(-12px); } }
@media (prefers-reduced-motion: reduce) {
  .mobile-nav-overlay, .mobile-nav-panel { animation-duration: 0.01ms !important; }
}
</style>
