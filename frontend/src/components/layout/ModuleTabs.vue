<script setup lang="ts">
import { Info } from 'lucide-vue-next'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useUiStore } from '@/stores/ui'

const props = defineProps<{ repoId: string; active: string }>()
const ui = useUiStore()
const nav = ref<HTMLElement | null>(null)
const indicator = ref({ x: 0, width: 0, visible: false })
let observer: ResizeObserver | null = null
const tabs = [
  { key: 'overview', label: '概览' },
  { key: 'activity', label: '开发活动' },
  { key: 'issues', label: 'Issue' },
  { key: 'prs', label: 'PR' },
  { key: 'releases', label: '版本发布' },
  { key: 'analysis', label: '仓库分析' },
]

async function positionIndicator() {
  await nextTick()
  const active = nav.value?.querySelector<HTMLElement>('[aria-current="page"]')
  if (!active) {
    indicator.value.visible = false
    return
  }
  indicator.value = { x: active.offsetLeft, width: active.offsetWidth, visible: true }
}

watch(() => [props.repoId, props.active], positionIndicator)
onMounted(() => {
  void positionIndicator()
  if (nav.value) {
    observer = new ResizeObserver(() => void positionIndicator())
    observer.observe(nav.value)
  }
})
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div class="sticky top-14 z-20 flex h-11 items-center justify-between gap-3 border-b border-line bg-bg px-4 sm:px-7">
    <nav ref="nav" class="module-tabs-nav relative flex h-11 min-w-0 gap-5 overflow-x-auto sm:gap-[22px]" aria-label="仓库分析模块">
      <span
        class="module-tabs-indicator absolute bottom-0 left-0 h-0.5 rounded-full bg-ink"
        :class="indicator.visible ? 'opacity-100' : 'opacity-0'"
        :style="{ width: `${indicator.width}px`, transform: `translateX(${indicator.x}px)` }"
        aria-hidden="true"
      />
      <RouterLink
        v-for="tab in tabs"
        :key="tab.key"
        :to="`/repositories/${repoId}/${tab.key}`"
        class="flex h-11 shrink-0 items-center border-b-2 border-transparent text-[13px] text-muted transition-colors duration-200 hover:text-ink"
        :class="active === tab.key && 'font-semibold text-ink'"
      >
        {{ tab.label }}
      </RouterLink>
    </nav>
    <button class="hidden shrink-0 items-center gap-1 text-[12px] text-muted transition-colors hover:text-ink sm:flex" @click="ui.openDrawer('definitions', { metric: 'M01' })">
      <Info :size="13" /> 数据与口径
    </button>
  </div>
</template>

<style scoped>
.module-tabs-nav { scrollbar-width: none; }
.module-tabs-nav::-webkit-scrollbar { display: none; }
.module-tabs-indicator { transition: transform 300ms var(--gd-ease-emphasized), width 300ms var(--gd-ease-emphasized), opacity 140ms ease; }
</style>
