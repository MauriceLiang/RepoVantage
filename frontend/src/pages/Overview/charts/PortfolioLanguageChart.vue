<script setup lang="ts">
import { computed, ref } from 'vue'
import type { G2Spec } from '@antv/g2'
import type { LanguageDatum } from '@/lib/overviewChartData'
import G2Chart from '@/components/charts/G2Chart.vue'
import { useUiStore } from '@/stores/ui'

const props = defineProps<{
  rows: LanguageDatum[]
  total: number
  selectedLanguageKeys: string[]
  filteredCount: number
}>()
const emit = defineEmits<{ toggleLanguages: [languageKeys: string[]] }>()
const hoveredKey = ref<string | null>(null)
const ui = useUiStore()
const chartRows = computed(() => props.rows.map((row, dataIndex) => ({
  ...row,
  dataIndex,
  sourceIndex: dataIndex,
  value: row.count,
  focusOpacity: hoveredKey.value
    ? hoveredKey.value === row.key ? 1 : 0.22
    : !props.selectedLanguageKeys.length || row.languageKeys.some((language) => props.selectedLanguageKeys.includes(language)) ? 1 : 0.24,
})))
const colors = computed(() => props.rows.map((row) => row.color))
const spec = computed<G2Spec>(() => ({
  type: 'interval',
  data: chartRows.value.filter((row) => row.value > 0),
  transform: [{ type: 'stackY' }],
  coordinate: { type: 'theta', innerRadius: 0.69, outerRadius: 0.91 },
  encode: { y: 'value', color: 'key', opacity: 'focusOpacity' },
  scale: { color: { domain: props.rows.map((row) => row.key), range: colors.value } },
  style: { stroke: ui.isDark ? '#151518' : '#ffffff', lineWidth: 2 },
  axis: false,
  legend: false,
  tooltip: { title: 'label', items: [
    { field: 'count', name: '仓库数' },
    { field: 'percent', name: '占比', valueFormatter: (value: number) => `${Number(value).toFixed(1)}%` },
  ] },
  interaction: { elementHighlight: true, tooltip: { shared: false } },
}))

function selectRow(row: LanguageDatum) {
  emit('toggleLanguages', row.languageKeys)
}

function selectChartRow(payload: { datum: Record<string, unknown> }) {
  const key = payload.datum.key
  const row = props.rows.find((item) => item.key === key)
  if (row) selectRow(row)
}

function isSelected(row: LanguageDatum) {
  return row.languageKeys.length > 0 && row.languageKeys.every((language) => props.selectedLanguageKeys.includes(language))
}

function clearHoveredRow(event: MouseEvent) {
  if (event.currentTarget !== document.activeElement) hoveredKey.value = null
}
</script>

<template>
  <UiPanel as="article" class="chart-panel language-panel" aria-labelledby="overview-language-title">
    <div class="panel-heading">
      <div><h2 id="overview-language-title" class="panel-title">主语言构成</h2><p class="panel-description">前五种语言单独展示，其余合并；占比包含未知语言</p></div>
      <span class="chart-sample mono">{{ total }} 个仓库</span>
    </div>
    <p v-if="filteredCount !== total" class="chart-scope">当前筛选 {{ filteredCount }} / {{ total }}</p>
    <div v-if="rows.length" class="language-content">
      <div class="language-donut" @mouseleave="hoveredKey = null">
        <G2Chart :spec="spec" label="已加入仓库的主语言环形图，支持选择语言筛选" :height="230" @select="selectChartRow" />
        <div class="language-center" aria-hidden="true"><strong>{{ total.toLocaleString('zh-CN') }}</strong><span>仓库</span></div>
      </div>
      <div class="language-ranking" role="group" aria-label="语言数量和占比，选择一项筛选仓库">
        <button
          v-for="row in rows"
          :key="row.key"
          type="button"
          class="language-row"
          :class="{ 'is-selected': isSelected(row), 'is-dimmed': selectedLanguageKeys.length && !row.languageKeys.some((language) => selectedLanguageKeys.includes(language)) }"
          :aria-pressed="isSelected(row)"
          :title="`${row.label}: ${row.count} 个仓库，占 ${row.percent.toFixed(1)}%`"
          @mouseenter="hoveredKey = row.key"
          @focus="hoveredKey = row.key"
          @mouseleave="clearHoveredRow"
          @blur="hoveredKey = null"
          @click="selectRow(row)"
        >
          <span class="language-swatch" :style="{ backgroundColor: row.color }" />
          <span class="language-name">{{ row.label }}</span>
          <span class="language-count mono">{{ row.count }}</span>
          <span class="language-percent mono">{{ row.percent.toFixed(1) }}%</span>
          <span class="language-track" aria-hidden="true"><span :style="{ width: `${row.percent}%`, backgroundColor: row.color }" /></span>
        </button>
      </div>
    </div>
    <div v-else class="chart-empty">当前没有可显示的语言构成</div>
    <p class="chart-note">{{ selectedLanguageKeys.length ? '点击已选语言可取消；也可同时选择多个语言。' : '语言是仓库主语言快照，不表示项目内部文件比例。' }}</p>
  </UiPanel>
</template>

<style scoped>
.chart-panel { min-width: 0; }
.language-content { display: grid; min-width: 0; grid-template-columns: minmax(160px, .9fr) minmax(0, 1.1fr); align-items: center; gap: 12px; }
.language-donut { position: relative; min-width: 0; }
.language-center { position: absolute; inset: 0; display: grid; align-content: center; justify-items: center; pointer-events: none; }
.language-center strong { color: var(--ink); font-size: 22px; font-variant-numeric: tabular-nums; line-height: 1.1; }
.language-center span { margin-top: 4px; color: var(--muted); font-size: 10px; }
.language-ranking { display: grid; min-width: 0; gap: 3px; }
.language-row { display: grid; grid-template-columns: 8px minmax(0, 1fr) auto auto; align-items: center; gap: 7px; padding: 6px 7px; border: 1px solid transparent; border-radius: 7px; color: var(--ink); background: transparent; text-align: left; cursor: pointer; transition: background-color 140ms ease, opacity 140ms ease, border-color 140ms ease; }
.language-row:hover, .language-row:focus-visible { background: var(--surface-soft); }
.language-row.is-selected { border-color: color-mix(in srgb, var(--primary) 35%, var(--line)); background: var(--primary-soft); }
.language-row.is-dimmed { opacity: .58; }
.language-swatch { width: 8px; height: 8px; border-radius: 50%; }
.language-name { overflow: hidden; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.language-count, .language-percent { font-size: 10px; font-variant-numeric: tabular-nums; }
.language-percent { width: 40px; color: var(--muted); text-align: right; }
.language-track { grid-column: 2 / -1; height: 3px; overflow: hidden; border-radius: 5px; background: var(--surface-soft); }
.language-track span { display: block; height: 100%; min-width: 2px; border-radius: inherit; opacity: .8; }
.chart-scope { margin: 8px 0 0; color: var(--primary-ink); font-size: 10px; }
.chart-note { margin: 8px 0 0; color: var(--muted); font-size: 10px; line-height: 1.5; }
.chart-empty { display: grid; min-height: 170px; place-items: center; color: var(--muted); font-size: 11px; }
@media (max-width: 600px) { .language-content { grid-template-columns: minmax(120px, .8fr) minmax(0, 1.2fr); gap: 4px; } .language-row { gap: 5px; padding-inline: 3px; } }
@media (prefers-reduced-motion: reduce) { .language-row { transition: none; } }
</style>
