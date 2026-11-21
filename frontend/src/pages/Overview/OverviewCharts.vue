<script setup lang="ts">
import type { OverviewChartData } from '@/lib/overviewChartData'
import type { OverviewChartFilterState } from '@/composables/useOverviewChartFilters'
import PortfolioLanguageChart from './charts/PortfolioLanguageChart.vue'
import PortfolioStarsDistribution from './charts/PortfolioStarsDistribution.vue'
import PortfolioPopularityScatter from './charts/PortfolioPopularityScatter.vue'

const props = defineProps<{
  data: OverviewChartData
  filters: OverviewChartFilterState
  filteredIds: string[]
  filteredCount: number
}>()
const emit = defineEmits<{
  toggleLanguages: [languageKeys: string[]]
  toggleStarsBucket: [key: string]
  selectRepository: [id: string]
  clearSelectedRepository: []
  clearFilters: []
}>()

const starsLabels: Record<string, string> = {
  zero: '0 Stars', b1: '1–100 Stars', b2: '101–1k Stars', b3: '1k–10k Stars', b4: '10k–100k Stars', b5: '100k+ Stars',
}
const selectedRepository = () => props.data.repositories.find((repository) => repository.id === props.filters.selectedRepositoryId)
</script>

<template>
  <div class="overview-charts" data-testid="overview-visualizations">
    <div v-if="filters.languageKeys.length || filters.starsBucket || filters.selectedRepositoryId" class="overview-filter-bar" role="region" aria-label="当前图表筛选条件">
      <div class="overview-filter-summary"><strong>已筛选 {{ filteredCount }} / {{ data.repositories.length }} 个仓库</strong><span>图表互相联动；顶部指标仍按全部仓库统计</span></div>
      <div class="overview-filter-chips">
        <button v-if="filters.languageKeys.length" type="button" class="filter-chip" @click="emit('toggleLanguages', filters.languageKeys)">语言 · {{ filters.languageKeys.length }} 种 <span aria-hidden="true">×</span></button>
        <button v-if="filters.starsBucket" type="button" class="filter-chip" @click="emit('toggleStarsBucket', filters.starsBucket!)">{{ starsLabels[filters.starsBucket] ?? filters.starsBucket }} <span aria-hidden="true">×</span></button>
        <span v-if="filters.selectedRepositoryId && selectedRepository()" class="selected-repository-chip">已选 {{ selectedRepository()?.fullName }}<button type="button" aria-label="清除所选仓库" @click="emit('clearSelectedRepository')">×</button></span>
        <button type="button" class="clear-filters" @click="emit('clearFilters')">清除全部</button>
      </div>
    </div>
    <div v-else class="overview-filter-hint"><span>三种视角：语言构成、Stars 分层、Stars 与 Forks 关联</span><span>点击图例或数据点联动筛选图表</span></div>
    <div class="overview-chart-grid overview-chart-grid--top">
      <PortfolioLanguageChart :rows="data.languageRows" :total="data.repositories.length" :filtered-count="filteredCount" :selected-language-keys="filters.languageKeys" @toggle-languages="emit('toggleLanguages', $event)" />
      <PortfolioStarsDistribution :buckets="data.starsBuckets" :total="data.repositories.length" :valid-count="data.validStarsCount" :invalid-count="data.invalidStarsCount" :selected-bucket="filters.starsBucket" :filtered-count="filteredCount" @toggle-bucket="emit('toggleStarsBucket', $event)" />
    </div>
    <PortfolioPopularityScatter :points="data.popularityPoints" :total="data.repositories.length" :median-stars="data.popularityMedianStars" :median-forks="data.popularityMedianForks" :filtered-ids="filteredIds" :filtered-count="filteredCount" :selected-repository-id="filters.selectedRepositoryId" :overlap-groups="data.popularityOverlapGroups" @select-repository="emit('selectRepository', $event)" @clear-selection="emit('clearSelectedRepository')" />
  </div>
</template>

<style scoped>
.overview-charts { display: grid; gap: 12px; min-width: 0; }
.overview-chart-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; align-items: start; }
.overview-filter-bar { display: grid; gap: 8px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 9px; background: var(--surface); }
.overview-filter-summary { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; }
.overview-filter-summary strong { color: var(--ink); font-size: 11px; font-weight: 650; }
.overview-filter-summary > span, .overview-filter-hint > span { color: var(--muted); font-size: 10px; }
.overview-filter-chips { display: flex; flex-wrap: wrap; align-items: center; gap: 5px; }
.filter-chip, .selected-repository-chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 7px; border: 1px solid color-mix(in srgb, var(--primary) 32%, var(--line)); border-radius: 999px; color: var(--primary-ink); background: var(--primary-soft); font: inherit; font-size: 9.5px; }
.filter-chip { cursor: pointer; }
.filter-chip span { font-size: 13px; line-height: 1; }
.selected-repository-chip { max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.selected-repository-chip button { padding: 0 0 1px; border: 0; color: inherit; background: transparent; font: inherit; font-size: 13px; cursor: pointer; }
.clear-filters { margin-left: auto; padding: 4px 6px; border: 0; color: var(--muted); background: transparent; font: inherit; font-size: 9.5px; text-decoration: underline; text-underline-offset: 2px; cursor: pointer; }
.clear-filters:hover { color: var(--primary-ink); }
.overview-filter-hint { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 6px 14px; padding: 0 2px; }
@media (max-width: 1199px) { .overview-chart-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 860px) { .overview-chart-grid { grid-template-columns: 1fr; } }
</style>
