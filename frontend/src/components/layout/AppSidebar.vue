<script setup lang="ts">
import { useRoute } from 'vue-router'
import { primaryNavigation } from './navigation'

const route = useRoute()
</script>

<template>
  <aside class="sticky top-0 hidden h-screen w-[236px] shrink-0 flex-col border-r border-line bg-panel px-4 py-5 lg:flex">
    <div class="flex h-[38px] items-center gap-2.5 px-1.5">
      <span class="relative grid size-6 shrink-0 place-items-center overflow-hidden">
        <img
          src="/repovantage-icon.png"
          alt=""
          class="absolute left-1/2 top-1/2 size-11 max-w-none -translate-x-1/2 -translate-y-1/2 object-contain"
        />
      </span>
      <div class="leading-tight">
        <b class="text-[14.5px] font-semibold">RepoVantage</b>
        <span class="block text-[11px] text-muted">开源项目分析</span>
      </div>
    </div>

    <nav class="mt-7 flex flex-col gap-1">
      <RouterLink
        v-for="item in primaryNavigation"
        :key="item.key"
        :to="item.to"
        :aria-current="route.meta.nav === item.key ? 'page' : undefined"
        class="flex h-10 items-center gap-3 rounded-lg px-3 text-[13.5px] transition-[color,background-color] duration-200"
        :class="route.meta.nav === item.key ? 'bg-soft font-semibold text-ink' : 'text-muted hover:bg-track hover:text-ink'"
      >
        <component :is="item.icon" :size="18" :stroke-width="1.8" />
        {{ item.label }}
      </RouterLink>
    </nav>
  </aside>
</template>
