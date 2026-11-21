<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { CSSProperties } from 'vue'
import { Folder, Gauge, ListChecks, Settings } from 'lucide-vue-next'

const props = defineProps<{ active: string; dataMode?: 'http' | 'mock'; mobile?: boolean }>()
const emit = defineEmits<{ select: [page: string] }>()
const sidebarRef = ref<HTMLElement | null>(null)
const indicatorReady = ref(false)
const indicatorStyle = ref<CSSProperties>({})
let resizeObserver: ResizeObserver | undefined

const items = [
  { id: 'overview', label: '概览', icon: Gauge, to: '/' },
  { id: 'repositories', label: '仓库', icon: Folder, to: '/repositories' },
]
const utilities = [
  { id: 'tasks', label: '任务中心', icon: ListChecks, to: '/tasks' },
  { id: 'settings', label: '设置', icon: Settings, to: '/settings' },
]

function updateIndicator() {
  const sidebar = sidebarRef.value
  const activeItem = sidebar?.querySelector<HTMLElement>('.nav-link--active')
  if (!sidebar || !activeItem) return

  const sidebarRect = sidebar.getBoundingClientRect()
  const itemRect = activeItem.getBoundingClientRect()
  const borderLeft = Number.parseFloat(getComputedStyle(sidebar).borderLeftWidth) || 0
  const borderTop = Number.parseFloat(getComputedStyle(sidebar).borderTopWidth) || 0
  indicatorStyle.value = {
    transform: `translate3d(${itemRect.left - sidebarRect.left - borderLeft}px, ${itemRect.top - sidebarRect.top - borderTop}px, 0)`,
    width: `${itemRect.width}px`,
    height: `${itemRect.height}px`,
  }
  indicatorReady.value = true
}

function scheduleIndicatorUpdate() {
  void nextTick(updateIndicator)
}

watch(() => props.active, scheduleIndicatorUpdate)

onMounted(() => {
  void nextTick(() => {
    updateIndicator()
    const sidebar = sidebarRef.value
    if (!sidebar || typeof ResizeObserver === 'undefined') return
    resizeObserver = new ResizeObserver(updateIndicator)
    resizeObserver.observe(sidebar)
    sidebar.querySelectorAll('.nav-link').forEach((item) => resizeObserver?.observe(item))
  })
})

onBeforeUnmount(() => resizeObserver?.disconnect())
</script>

<template>
  <aside ref="sidebarRef" :class="mobile ? 'mobile-nav' : 'sidebar'">
    <span v-if="indicatorReady" class="nav-active-indicator" :style="indicatorStyle" aria-hidden="true" />
    <div class="brand"><div class="brand-copy"><span class="brand-name">GitHub开源项目数据分析与技术选型辅助系统</span><span class="brand-caption">开源项目分析</span></div></div>
    <div class="nav-section-label">工作区</div>
    <nav class="nav-list" aria-label="主要导航">
      <UiNavItem v-for="item in items" :key="item.id" :id="item.id" :label="item.label" :icon="item.icon" :active="props.active === item.id" :to="item.to" @select="emit('select', $event)" />
    </nav>
    <div class="nav-section-label">管理</div>
    <nav class="nav-list" aria-label="管理导航">
      <UiNavItem v-for="item in utilities" :key="item.id" :id="item.id" :label="item.label" :icon="item.icon" :active="props.active === item.id" :to="item.to" @select="emit('select', $event)" />
    </nav>
    <div class="sidebar-bottom"><div class="sidebar-note"><span class="status-dot" />{{ props.dataMode === 'mock' ? '当前使用演示数据' : '连接本机数据服务' }}</div></div>
  </aside>
</template>
