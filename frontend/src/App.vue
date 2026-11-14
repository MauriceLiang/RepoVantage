<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import AppTopbar from '@/components/layout/AppTopbar.vue'
import EventDrawer from '@/components/common/EventDrawer.vue'
import GdToastHost from '@/components/ui/GdToastHost.vue'

const router = useRouter()
const dataMode = import.meta.env.VITE_DATA_MODE === 'mock' ? 'mock' : 'http'
const navigationLoading = ref(false)
let showTimer: ReturnType<typeof setTimeout> | undefined
let finishTimer: ReturnType<typeof setTimeout> | undefined
let shownAt = 0
let pendingPath = ''

function clearTimer(timer: ReturnType<typeof setTimeout> | undefined) {
  if (timer) clearTimeout(timer)
}

function finishNavigation() {
  clearTimer(showTimer)
  showTimer = undefined
  if (!navigationLoading.value) return

  const remaining = Math.max(0, 220 - (Date.now() - shownAt))
  finishTimer = setTimeout(() => {
    navigationLoading.value = false
    finishTimer = undefined
  }, remaining)
}

const removeBeforeEach = router.beforeEach((to) => {
  clearTimer(showTimer)
  clearTimer(finishTimer)
  pendingPath = to.fullPath

  if (navigationLoading.value) {
    shownAt = Date.now()
    return
  }
  showTimer = setTimeout(() => {
    navigationLoading.value = true
    shownAt = Date.now()
    showTimer = undefined
  }, 100)
})
const removeAfterEach = router.afterEach((to) => {
  if (to.fullPath === pendingPath) finishNavigation()
})
const removeOnError = router.onError((_error, to) => {
  if (to.fullPath === pendingPath) finishNavigation()
})

onBeforeUnmount(() => {
  clearTimer(showTimer)
  clearTimer(finishTimer)
  removeBeforeEach()
  removeAfterEach()
  removeOnError()
})
</script>

<template>
  <div class="flex min-h-screen" data-testid="app" :data-mode="dataMode">
    <AppSidebar />
    <div class="flex min-w-0 flex-1 flex-col">
      <AppTopbar />
      <div class="route-transition-stage mx-auto w-full max-w-[1360px]" :aria-busy="navigationLoading">
        <RouterView v-slot="{ Component, route }">
          <Transition name="route-page">
            <div :key="route.name === 'repository' ? 'repository-analysis' : String(route.name ?? route.path)" class="route-page min-w-0">
              <component :is="Component" />
            </div>
          </Transition>
        </RouterView>
      </div>
    </div>
  </div>
  <Transition name="route-progress">
    <div v-if="navigationLoading" class="route-progress" role="status" aria-live="polite">
      <span class="route-progress__bar" aria-hidden="true" />
      <span class="sr-only">正在切换页面…</span>
    </div>
  </Transition>
  <EventDrawer />
  <GdToastHost />
</template>
