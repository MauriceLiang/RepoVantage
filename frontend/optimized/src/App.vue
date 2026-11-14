<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ChevronRight, ListChecks, Menu, Moon, Settings, Sun, X } from 'lucide-vue-next'
import { storeToRefs } from 'pinia'
import AboutRepoVantageDialog from '@/components/layout/AboutRepoVantageDialog.vue'
import EventDrawer from '@/components/common/EventDrawer.vue'
import GdToastHost from '@/components/ui/GdToastHost.vue'
import { useUiStore } from '@/stores/ui'
import NavigationSidebar from './components/NavigationSidebar.vue'

const route = useRoute()
const ui = useUiStore()
const { theme } = storeToRefs(ui)
const mobileNavOpen = ref(false)
const dataMode = import.meta.env.VITE_DATA_MODE === 'mock' ? 'mock' : 'http'

const currentTitle = computed(() => String(route.meta.title ?? '总览'))
const breadcrumb = computed(() => String(route.meta.crumb ?? '工作台'))
const activeNav = computed(() => String(route.meta.nav ?? 'overview'))
const breadcrumbTarget = computed(() => route.name === 'repository' ? '/repositories' : '/')

</script>

<template>
  <div class="app-layout" :data-theme="theme" :data-mode="dataMode" data-testid="app">
    <NavigationSidebar :active="activeNav" :data-mode="dataMode" @select="mobileNavOpen = false" />
    <div class="main-column">
      <header class="topbar">
        <div class="breadcrumb">
          <button class="icon-button mobile-menu-button" aria-label="打开导航" @click="mobileNavOpen = true"><Menu :size="17" /></button>
          <RouterLink :to="breadcrumbTarget" class="breadcrumb-link">{{ breadcrumb }}</RouterLink>
          <ChevronRight :size="13" />
          <span class="breadcrumb-current">{{ currentTitle }}</span>
        </div>
        <div class="topbar-actions">
          <AboutRepoVantageDialog />
          <RouterLink to="/tasks" class="topbar-task-link"><ListChecks :size="14" />任务</RouterLink>
          <RouterLink to="/settings" class="icon-button topbar-settings-link" aria-label="设置" title="设置"><Settings :size="16" /></RouterLink>
          <button class="icon-button" :title="theme === 'dark' ? '切换浅色主题' : '切换深色主题'" :aria-label="theme === 'dark' ? '切换浅色主题' : '切换深色主题'" @click="ui.toggleTheme()"><Sun v-if="theme === 'dark'" :size="15" /><Moon v-else :size="15" /></button>
          <button v-if="mobileNavOpen" class="icon-button mobile-close" aria-label="关闭导航" @click="mobileNavOpen = false"><X :size="16" /></button>
        </div>
      </header>

      <main class="main-content" :aria-label="currentTitle">
        <div class="page-stage-host">
          <RouterView v-slot="{ Component, route: viewRoute }">
            <Transition name="page-entry">
              <div :key="String(viewRoute.name ?? viewRoute.path)" class="page-stage">
                <component :is="Component" />
              </div>
            </Transition>
          </RouterView>
        </div>
      </main>
    </div>

    <Transition name="mobile-backdrop">
      <button v-if="mobileNavOpen" class="mobile-nav-backdrop" aria-label="关闭导航菜单" @click="mobileNavOpen = false" />
    </Transition>
    <Transition name="mobile-drawer">
      <NavigationSidebar v-if="mobileNavOpen" :active="activeNav" :data-mode="dataMode" mobile @select="mobileNavOpen = false" />
    </Transition>
  </div>
  <EventDrawer />
  <GdToastHost />
</template>
