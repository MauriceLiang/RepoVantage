<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ArrowUpRight, Info, Search } from 'lucide-vue-next'
import { getBrowserApiData } from '@/services/httpRepositoryDataSource'
import { useUiStore } from '@/stores/ui'
import ChartPanel from '../components/ChartPanel.vue'
import ResearchAtlasG2 from '../components/ResearchAtlasG2.vue'
import type { AtlasBrushSelection, AtlasChartPoint, AtlasPoint, AtlasResponse, AtlasSelectionRange, AtlasViewMode } from '../data/researchTypes'
import type { EChartsOption } from 'echarts'

const ui = useUiStore()
const { theme } = storeToRefs(ui)
const isDark = computed(() => theme.value === 'dark')
const result = ref<AtlasResponse | null>(null)
const loading = ref(true)
const error = ref('')
const query = ref('')
const language = ref('全部语言')
const sampleRole = ref('全部样本角色')
const viewMode = ref<AtlasViewMode>('activity-mean')
const minimumCommitInput = ref<string | number>('')
const minimumPrInput = ref<string | number>('')
const selectedId = ref<number | null>(null)
const brushedRepositoryIds = ref<number[] | null>(null)
const brushSelection = ref<AtlasSelectionRange | null>(null)

const languages = computed(() => ['全部语言', ...new Set((result.value?.points ?? []).map((point) => point.language))])
const minimumCommit = computed(() => parseThreshold(minimumCommitInput.value))
const minimumPr = computed(() => parseThreshold(minimumPrInput.value))
const viewDescription = computed(() => {
  if (viewMode.value === 'activity-volatility') return '活动波动：每个坐标是 12 个完整 UTC 周计数的总体标准差，显示 log1p 值。'
  if (viewMode.value === 'pr-trend') return 'PR 增减趋势：X 为周均 Commit（log1p），Y 为新开 PR 周计数的最小二乘斜率（个 / 周²，线性轴）。'
  return '12 周活动均值：X/Y 为 12 个完整 UTC 周的周均 Commit 与新开 PR，显示 log1p 值。'
})

const visiblePoints = computed(() => (result.value?.points ?? []).filter((point) => {
  const matchesQuery = !query.value || point.full_name.toLowerCase().includes(query.value.trim().toLowerCase())
  const matchesLanguage = language.value === '全部语言' || point.language === language.value
  const matchesRole = sampleRole.value === '全部样本角色' || point.sample_role === sampleRole.value
  const matchesCommit = minimumCommit.value === null || point.weekly_commit_mean >= minimumCommit.value
  const matchesPr = minimumPr.value === null || point.weekly_pr_open_mean >= minimumPr.value
  return matchesQuery && matchesLanguage && matchesRole && matchesCommit && matchesPr
}))
const roleOptions = computed(() => ['全部样本角色', ...new Set((result.value?.points ?? []).map((point) => point.sample_role).filter((role): role is string => Boolean(role)))])
const chartPoints = computed<AtlasChartPoint[]>(() => visiblePoints.value.map((point) => {
  const commits = point.weekly_trace.map((week) => week.commits)
  const prs = point.weekly_trace.map((week) => week.prs_opened)
  let xValue: number
  let yValue: number
  let xLabel: string
  let yLabel: string
  let xValueLabel: string
  let yValueLabel: string
  let xPosition: number
  let yPosition: number

  if (viewMode.value === 'activity-volatility') {
    xValue = populationStandardDeviation(commits)
    yValue = populationStandardDeviation(prs)
    xLabel = 'log1p（周均 Commit 波动 σ）'
    yLabel = 'log1p（新开 PR 波动 σ）'
    xValueLabel = 'Commit 周计数标准差（次 / 周）'
    yValueLabel = '新开 PR 周计数标准差（个 / 周）'
    xPosition = Math.log1p(xValue)
    yPosition = Math.log1p(yValue)
  } else if (viewMode.value === 'pr-trend') {
    xValue = point.weekly_commit_mean
    yValue = linearSlope(prs)
    xLabel = 'log1p（12 周周均 Commit）'
    yLabel = '新开 PR 趋势斜率（个 / 周²，线性）'
    xValueLabel = '12 周周均 Commit（次 / 周）'
    yValueLabel = '新开 PR 趋势斜率（个 / 周²）'
    xPosition = Math.log1p(xValue)
    yPosition = yValue
  } else {
    xValue = point.weekly_commit_mean
    yValue = point.weekly_pr_open_mean
    xLabel = 'log1p（12 周周均 Commit）'
    yLabel = 'log1p（12 周周均新开 PR）'
    xValueLabel = '12 周周均 Commit（次 / 周）'
    yValueLabel = '12 周周均新开 PR（个 / 周）'
    xPosition = Math.log1p(xValue)
    yPosition = Math.log1p(yValue)
  }

  return {
    ...point,
    x_value: xValue,
    y_value: yValue,
    x_position: xPosition,
    y_position: yPosition,
    x_label: xLabel,
    y_label: yLabel,
    x_value_label: xValueLabel,
    y_value_label: yValueLabel,
  }
}))
const displayedPoints = computed(() => brushedRepositoryIds.value === null
  ? visiblePoints.value
  : visiblePoints.value.filter((point) => brushedRepositoryIds.value?.includes(point.repository_id)))
const selectedPoint = computed(() => displayedPoints.value.find((point) => point.repository_id === selectedId.value)
  ?? displayedPoints.value[0]
  ?? null)
const selectedChartPoint = computed(() => chartPoints.value.find((point) => point.repository_id === selectedPoint.value?.repository_id) ?? null)
const viewHasThreshold = computed(() => minimumCommit.value !== null || minimumPr.value !== null)

function parseThreshold(value: string | number): number | null {
  if (typeof value === 'string' && !value.trim()) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null
}

function populationStandardDeviation(values: number[]): number {
  if (values.length === 0) return 0
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length
  return Math.sqrt(values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length)
}

function linearSlope(values: number[]): number {
  if (values.length < 2) return 0
  const xMean = (values.length - 1) / 2
  const yMean = values.reduce((sum, value) => sum + value, 0) / values.length
  let covariance = 0
  let variance = 0
  values.forEach((value, index) => {
    const delta = index - xMean
    covariance += delta * (value - yMean)
    variance += delta ** 2
  })
  return variance === 0 ? 0 : covariance / variance
}

function clearBrush() {
  brushedRepositoryIds.value = null
  brushSelection.value = null
}
const trendOption = computed<EChartsOption>(() => {
  const trace = selectedPoint.value?.weekly_trace ?? []
  return {
    color: ['#55b7f3', '#53c998'],
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0, textStyle: { color: isDark.value ? '#bec8d0' : '#667480' } },
    grid: { top: 18, right: 15, bottom: 48, left: 44 },
    xAxis: { type: 'category', data: trace.map((week) => week.week_start.slice(5, 10)), axisLabel: { color: isDark.value ? '#bec8d0' : '#667480', fontSize: 10 } },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { color: isDark.value ? '#bec8d0' : '#667480', fontSize: 10 }, splitLine: { lineStyle: { color: isDark.value ? '#303942' : '#e6ebef', type: 'dashed' } } },
    series: [
      { name: 'Commit', type: 'line', data: trace.map((week) => week.commits), smooth: 0.18, symbolSize: 5, lineStyle: { width: 2.5 } },
      { name: '新开 PR', type: 'line', data: trace.map((week) => week.prs_opened), smooth: 0.18, symbolSize: 5, lineStyle: { width: 2.5 } },
    ],
  }
})

async function loadAtlas() {
  loading.value = true
  error.value = ''
  try {
    result.value = await getBrowserApiData<AtlasResponse>('/research/atlas')
    selectedId.value = result.value.points[0]?.repository_id ?? null
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '研究图谱加载失败'
  } finally {
    loading.value = false
  }
}

function selectPoint(point: AtlasPoint) {
  clearBrush()
  selectedId.value = point.repository_id
}

function handleBrush(selection: AtlasBrushSelection) {
  if (selection.reset) {
    clearBrush()
    return
  }
  brushedRepositoryIds.value = selection.repository_ids
  brushSelection.value = selection.selection
}

onMounted(() => { void loadAtlas() })

watch([viewMode, language, sampleRole, query, minimumCommitInput, minimumPrInput], () => {
  clearBrush()
  if (!visiblePoints.value.some((point) => point.repository_id === selectedId.value)) {
    selectedId.value = visiblePoints.value[0]?.repository_id ?? null
  }
})
</script>

<template>
  <div class="optimized-page atlas-page">
    <header class="atlas-heading">
      <div>
        <div class="atlas-kicker">FROZEN COURSE RESEARCH · DESCRIPTIVE VIEW</div>
        <h1 class="page-title">300 仓库研究图谱</h1>
        <p class="page-description">用固定的 12 周 Commit 与新开 PR 记录查看样本分布。它用于研究探索，不是跨功能技术排名。</p>
      </div>
      <div class="atlas-heading-actions">
        <span v-if="result" class="snapshot-label">数据截止 <strong>{{ result.data_as_of?.slice(0, 10) }}</strong></span>
        <RouterLink class="button button--primary" to="/selection">进入技术选型 <ArrowUpRight :size="14" /></RouterLink>
      </div>
    </header>

    <div v-if="loading" class="panel atlas-state" role="status">正在读取冻结课程样本…</div>
    <div v-else-if="error" class="panel atlas-state atlas-state--error" role="alert"><strong>研究图谱暂不可用</strong><span>{{ error }}</span><button class="button button--outline" @click="loadAtlas">重新加载</button></div>
    <template v-else-if="result">
      <div class="atlas-meta-row">
        <span><strong>{{ result.point_count }}</strong> 个真实节点</span>
        <span>{{ result.weekly_record_count.toLocaleString('zh-CN') }} 条仓库周记录</span>
        <span>{{ result.observation_window.start.slice(0, 10) }} – {{ result.observation_window.end_exclusive.slice(0, 10) }} UTC</span>
        <span v-if="result.excluded_count" class="atlas-excluded"><Info :size="13" /> 排除 {{ result.excluded_count }} 个：{{ Object.entries(result.excluded_reasons).map(([key, value]) => `${key} ${value}`).join('，') }}</span>
      </div>

      <section class="atlas-layout" aria-label="300 仓库分布与联动详情">
        <article class="panel atlas-main-panel">
          <div class="atlas-panel-heading">
            <div><h2>12 周活动分布</h2><p>每个点对应一个样本仓库；颜色区分主要语言{{ visiblePoints.every((point) => point.stars !== null) ? '，点大小表示 Stars 快照' : '' }}。</p></div>
            <span class="atlas-count">{{ displayedPoints.length }} / {{ result.repository_count }}</span>
          </div>
          <div class="atlas-filters">
            <label class="atlas-search"><Search :size="15" /><input v-model="query" type="search" placeholder="搜索仓库名称" aria-label="搜索仓库名称" /></label>
            <label><span class="sr-only">研究视图</span><select v-model="viewMode" aria-label="研究视图"><option value="activity-mean">12 周活动均值</option><option value="activity-volatility">活动波动</option><option value="pr-trend">PR 增减趋势</option></select></label>
            <label><span class="sr-only">按语言筛选</span><select v-model="language" aria-label="按语言筛选"><option v-for="item in languages" :key="item">{{ item }}</option></select></label>
            <label><span class="sr-only">按样本角色筛选</span><select v-model="sampleRole" aria-label="按样本角色筛选"><option v-for="item in roleOptions" :key="item">{{ item }}</option></select></label>
          </div>
          <div class="atlas-activity-filters">
            <span class="atlas-filter-label">活动过滤</span>
            <label>周均 Commit ≥ <input v-model="minimumCommitInput" type="number" min="0" step="0.1" placeholder="不限" aria-label="最低周均 Commit" /></label>
            <label>周均新开 PR ≥ <input v-model="minimumPrInput" type="number" min="0" step="0.1" placeholder="不限" aria-label="最低周均新开 PR" /></label>
            <button v-if="viewHasThreshold" class="atlas-clear-filter" type="button" @click="minimumCommitInput = ''; minimumPrInput = ''">清除门槛</button>
            <span class="atlas-brush-hint">拖动图表框选缩放 · 双击恢复</span>
          </div>
          <p class="atlas-view-description" aria-live="polite">{{ viewDescription }}</p>
          <div class="atlas-chart-wrap">
            <ResearchAtlasG2 :points="chartPoints" :selected-id="selectedId" :is-dark="isDark" :brush-selection="brushSelection" @select="selectPoint" @brush="handleBrush" />
            <div v-if="!displayedPoints.length" class="atlas-empty-overlay">{{ brushedRepositoryIds ? '框选范围内没有仓库；双击图表恢复' : '没有符合当前筛选条件的仓库' }}</div>
          </div>
          <div class="atlas-footnote"><Info :size="13" /> 悬停查看坐标原值、数据窗口与覆盖；框选缩放，双击恢复。缺失项不补零。</div>
        </article>

        <aside class="atlas-side-column">
          <article class="panel atlas-selected-panel" aria-live="polite">
            <div class="atlas-panel-heading"><div><h2>选中样本</h2><p>点击图中节点或列表行查看实际记录。</p></div><span class="atlas-dot" /></div>
            <template v-if="selectedPoint">
              <div class="atlas-repo-title"><strong>{{ selectedPoint.full_name }}</strong><a :href="`https://github.com/${selectedPoint.full_name}`" target="_blank" rel="noreferrer" :aria-label="`在 GitHub 打开 ${selectedPoint.full_name}`"><ArrowUpRight :size="15" /></a></div>
              <div v-if="selectedChartPoint" class="atlas-measures">
                <div><span>{{ selectedChartPoint.x_value_label }}</span><strong>{{ selectedChartPoint.x_value.toFixed(2) }}</strong></div>
                <div><span>{{ selectedChartPoint.y_value_label }}</span><strong>{{ selectedChartPoint.y_value.toFixed(2) }}</strong></div>
              </div>
              <div class="atlas-detail-meta"><span>{{ selectedPoint.language }}</span><span>{{ selectedPoint.sample_role ?? '样本角色未知' }}</span><span>覆盖 {{ selectedPoint.coverage.commits }} / {{ selectedPoint.coverage.prs_opened }}</span></div>
            </template>
            <p v-else class="atlas-empty-copy">当前筛选没有可选节点。</p>
          </article>

          <article v-if="selectedPoint" class="panel atlas-trend-panel">
            <div class="atlas-panel-heading"><div><h2>12 周活动轨迹</h2><p>Commit 与新开 PR 每周计数</p></div></div>
            <ChartPanel :option="trendOption" label="选中仓库 12 周 Commit 和新开 PR 趋势" :height="230" />
          </article>

          <article class="panel atlas-list-panel">
            <div class="atlas-panel-heading"><div><h2>样本列表</h2><p>按周均 Commit 降序，最多显示 8 行。</p></div></div>
            <button v-for="point in [...displayedPoints].sort((left, right) => right.weekly_commit_mean - left.weekly_commit_mean).slice(0, 8)" :key="point.repository_id" class="atlas-list-row" :class="{ 'is-selected': point.repository_id === selectedPoint?.repository_id }" :aria-pressed="point.repository_id === selectedPoint?.repository_id" @click="selectPoint(point)">
              <span><strong>{{ point.full_name }}</strong><small>{{ point.language }} · {{ point.sample_role }}</small></span>
              <span class="atlas-list-value">{{ point.weekly_commit_mean.toFixed(1) }}<small>次 / 周</small></span>
            </button>
            <p v-if="!displayedPoints.length" class="atlas-empty-copy">调整筛选条件或清除框选后查看仓库。</p>
          </article>
        </aside>
      </section>
    </template>
  </div>
</template>

<style scoped>
.atlas-page { display: grid; gap: 14px; }
.atlas-heading { display:flex; align-items:flex-end; justify-content:space-between; gap:24px; }
.atlas-kicker { margin-bottom:7px; color:var(--primary-ink); font-size:10px; font-weight:700; letter-spacing:.11em; }
.atlas-heading-actions { display:flex; align-items:center; gap:9px; flex:0 0 auto; }
.atlas-meta-row { display:flex; flex-wrap:wrap; align-items:center; gap:8px 18px; color:var(--muted); font-size:11px; }
.atlas-meta-row strong { color:var(--ink); font-size:14px; }
.atlas-excluded { display:inline-flex; align-items:center; gap:5px; color:var(--amber); }
.atlas-layout { display:grid; grid-template-columns:minmax(0, 2.15fr) minmax(280px, .85fr); gap:14px; align-items:start; }
.atlas-main-panel { min-height:680px; }
.atlas-side-column { display:grid; gap:14px; }
.atlas-panel-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:12px; }
.atlas-panel-heading h2 { margin:0; font-size:14px; font-weight:650; }
.atlas-panel-heading p { margin:4px 0 0; color:var(--muted); font-size:11px; line-height:1.5; }
.atlas-count { padding:5px 8px; border:1px solid var(--line); border-radius:6px; color:var(--muted); font-size:11px; white-space:nowrap; }
.atlas-filters { display:flex; align-items:center; gap:8px; }
.atlas-search { display:flex; min-height:34px; flex:1; align-items:center; gap:7px; padding:0 10px; border:1px solid var(--line); border-radius:7px; color:var(--muted); background:var(--bg); }
.atlas-search input { width:100%; border:0; outline:none; color:var(--ink); background:transparent; font-size:11.5px; }
.atlas-filters select { height:34px; max-width:150px; padding:0 8px; border:1px solid var(--line); border-radius:7px; color:var(--ink); background:var(--surface); font-size:11px; }
.atlas-activity-filters { display:flex; flex-wrap:wrap; align-items:center; gap:7px 11px; margin-top:8px; color:var(--muted); font-size:10.5px; }
.atlas-activity-filters label { display:flex; align-items:center; gap:5px; white-space:nowrap; }
.atlas-activity-filters input { width:76px; height:29px; padding:0 6px; border:1px solid var(--line); border-radius:6px; color:var(--ink); background:var(--surface); font-size:10.5px; }
.atlas-filter-label { color:var(--ink); font-weight:650; }
.atlas-clear-filter { padding:3px 5px; border:0; color:var(--primary-ink); background:transparent; font-size:10px; cursor:pointer; }
.atlas-brush-hint { margin-left:auto; }
.atlas-view-description { margin:7px 0 0; color:var(--muted); font-size:10.5px; line-height:1.45; }
.atlas-chart-wrap { position:relative; height:min(62vh, 610px); min-height:480px; margin-top:7px; }
.atlas-empty-overlay { position:absolute; inset:0; display:grid; place-items:center; color:var(--muted); background:color-mix(in srgb,var(--surface) 70%,transparent); }
.atlas-footnote { display:flex; align-items:flex-start; gap:6px; margin-top:7px; color:var(--muted); font-size:10.5px; line-height:1.5; }
.atlas-dot { width:8px; height:8px; margin:5px 4px 0; border-radius:50%; background:var(--primary); box-shadow:0 0 0 4px var(--primary-soft); }
.atlas-repo-title { display:flex; align-items:center; justify-content:space-between; gap:9px; margin:16px 0 10px; font-size:16px; }
.atlas-repo-title strong { overflow-wrap:anywhere; }
.atlas-repo-title a { display:grid; width:28px; height:28px; flex:0 0 auto; place-items:center; border:1px solid var(--line); border-radius:6px; color:var(--muted); }
.atlas-measures { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
.atlas-measures div { display:grid; gap:7px; padding:11px; border:1px solid var(--line); border-radius:8px; background:var(--surface-soft); }
.atlas-measures span,.atlas-detail-meta { color:var(--muted); font-size:10.5px; }
.atlas-measures strong { font-size:22px; font-variant-numeric:tabular-nums; }
.atlas-detail-meta { display:flex; flex-wrap:wrap; gap:6px 11px; margin-top:10px; }
.atlas-list-row { display:flex; width:100%; min-height:52px; align-items:center; justify-content:space-between; gap:10px; padding:7px 6px; border:0; border-top:1px solid var(--line); color:var(--ink); background:transparent; text-align:left; cursor:pointer; }
.atlas-list-row:hover,.atlas-list-row.is-selected { background:var(--primary-soft); }
.atlas-list-row span:first-child { min-width:0; }
.atlas-list-row strong,.atlas-list-row small { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.atlas-list-row strong { font-size:11px; }
.atlas-list-row small { margin-top:3px; color:var(--muted); font-size:9.5px; }
.atlas-list-value { flex:0 0 auto; font-size:12px; font-variant-numeric:tabular-nums; text-align:right; }
.atlas-list-value small { margin-top:2px; }
.atlas-empty-copy { color:var(--muted); font-size:11px; }
.atlas-state { display:grid; min-height:180px; place-content:center; gap:12px; color:var(--muted); text-align:center; }
.atlas-state--error strong { color:var(--ink); }
@media (max-width:1100px) { .atlas-layout { grid-template-columns:minmax(0,1.6fr) minmax(250px,1fr); } }
@media (max-width:1250px) { .atlas-filters { flex-wrap:wrap; } .atlas-search { min-width:200px; flex-basis:100%; } }
@media (max-width:850px) { .atlas-heading { align-items:flex-start; flex-direction:column; } .atlas-layout { grid-template-columns:minmax(0,1fr); } .atlas-main-panel { min-height:560px; } .atlas-chart-wrap { min-height:410px; height:55vh; } }
@media (prefers-reduced-motion:reduce) { *,*::before,*::after { scroll-behavior:auto !important; transition-duration:.01ms !important; animation-duration:.01ms !important; } }
</style>
