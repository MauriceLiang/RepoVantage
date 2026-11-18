<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { ArrowUpRight, Info } from 'lucide-vue-next'
import type { G2Spec } from '@antv/g2'
import { getBrowserApiData } from '@/services/httpRepositoryDataSource'
import { useUiStore } from '@/stores/ui'
import G2Chart from '@/components/charts/G2Chart.vue'
import DecisionScatterG2 from '@/components/charts/DecisionScatterG2.vue'
import type { DecisionPoint } from '@/components/charts/DecisionScatterG2.vue'
import type { CapabilityEvidence, MetricEvidence, ScenarioCandidate, ScenarioDetail, ScenarioSummary, ScenarioViz, SelectionWeek } from '@/data/researchTypes'

interface CandidateDetailResponse {
  scenario: string
  candidate: ScenarioCandidate
  capabilities: CapabilityEvidence[]
  capability_evidence_status: 'reviewed' | 'not_reviewed'
  limitations: string[]
}

const ui = useUiStore()
const { theme } = storeToRefs(ui)
const isDark = computed(() => theme.value === 'dark')
const catalog = ref<ScenarioSummary[]>([])
const scenario = ref<ScenarioDetail | null>(null)
const viz = ref<ScenarioViz | null>(null)
const candidateDetail = ref<CandidateDetailResponse | null>(null)
const loading = ref(true)
const detailLoading = ref(false)
const error = ref('')
const selectedId = ref<number | null>(null)
const eligibilityFilter = ref('all')
const constraintFilter = ref('all')
const palette = ['#55b7f3', '#53c998', '#f2b35d', '#f17878']

const candidates = computed(() => (scenario.value?.candidates ?? []).filter((candidate) => candidate.role !== 'reference'))
const showNetHttpFilter = computed(() => scenario.value?.slug === 'go-http-api')
const filteredCandidates = computed(() => candidates.value.filter((candidate) => {
  const matchesEligibility = eligibilityFilter.value === 'all' || candidate.eligibility === eligibilityFilter.value
  const evidence = candidate.capabilities.find((item) => item.capability_key === 'net_http_middleware')
  const matchesConstraint = !showNetHttpFilter.value || constraintFilter.value === 'all' || (evidence?.status ?? 'unknown') === constraintFilter.value
  return matchesEligibility && matchesConstraint
}))
const selectedCandidate = computed(() => scenario.value?.candidates.find((candidate) => candidate.repository_id === selectedId.value) ?? null)
const selectedViz = computed(() => viz.value?.candidates.find((candidate) => candidate.repository_id === selectedId.value) ?? null)
const chartPoints = computed<DecisionPoint[]>(() => (viz.value?.candidates ?? []).flatMap((candidate) => {
  if (candidate.role === 'reference' || candidate.x?.value === null || candidate.y?.value === null || candidate.x?.value === undefined || candidate.y?.value === undefined) return []
  if (!['complete', 'true_zero'].includes(candidate.x.coverage_status) || !['complete', 'true_zero'].includes(candidate.y.coverage_status)) return []
  const netHttpStatus = candidate.capabilities.find((item) => item.capability_key === 'net_http_middleware')?.status ?? 'unknown'
  return [{ repository_id: candidate.repository_id, full_name: candidate.full_name, x: candidate.x.value, y: candidate.y.value, eligibility: candidate.eligibility,
    x_unit: candidate.x.unit, y_unit: candidate.y.unit, x_sample_count: candidate.x.sample_count, y_sample_count: candidate.y.sample_count,
    x_coverage_status: candidate.x.coverage_status, y_coverage_status: candidate.y.coverage_status,
    window_start: candidate.x.window_start, window_end_exclusive: candidate.x.window_end_exclusive, net_http_middleware_status: netHttpStatus }]
}))

const metricDefinitions = [
  { key: 'weekly_commit_mean', label: '周均 Commit', unit: '次 / 周' },
  { key: 'weekly_pr_open_mean', label: '周均新开 PR', unit: '个 / 周' },
  { key: 'issue_closed_median_days', label: 'Issue 关闭中位数', unit: '天' },
  { key: 'pr_merged_median_days', label: 'PR 合并中位数', unit: '天' },
  { key: 'release_interval_median_days', label: 'Release 间隔中位数', unit: '天' },
] as const

const parallelDimensions = metricDefinitions.map((metric) => metric.key)
const parallelRows = computed(() => candidates.value.flatMap((candidate) => {
  const values = parallelDimensions.map((key) => candidate.metrics[key]?.value ?? null)
  if (values.some((value) => value === null)) return []
  return [{
    full_name: candidate.full_name,
    weekly_commit_mean: values[0]!,
    weekly_pr_open_mean: values[1]!,
    issue_closed_median_days: values[2]!,
    pr_merged_median_days: values[3]!,
    release_interval_median_days: values[4]!,
  }]
}))
const parallelExcludedCount = computed(() => candidates.value.length - parallelRows.value.length)
const parallelSpec = computed<G2Spec>(() => {
  const color = isDark.value ? '#bec8d0' : '#667480'
  return {
    type: 'line', coordinate: { type: 'parallel' }, data: parallelRows.value,
    encode: { position: parallelDimensions, color: 'full_name' },
    style: { lineWidth: 1.5, strokeOpacity: 0.52 },
    scale: { color: { range: palette } },
    axis: Object.fromEntries(['position', 'position1', 'position2', 'position3', 'position4'].map((key, index) => [key, {
      zIndex: 1, labelFill: color, labelFontSize: 9,
      title: `${metricDefinitions[index].label}（${metricDefinitions[index].unit}）`, titleFill: color, titleFontSize: 10,
    }])),
    legend: { color: { position: 'bottom', itemLabelFill: color, itemLabelFontSize: 9 } },
    interaction: { brushHighlight: true, tooltip: { series: false } },
    tooltip: { title: 'full_name', items: metricDefinitions.map((metric) => ({ field: metric.key, name: `${metric.label}（${metric.unit}）` })) },
  }
})
const activitySpec = computed<G2Spec>(() => {
  const weeks: SelectionWeek[] = selectedViz.value?.weekly_activity ?? []
  const data = weeks.flatMap((week) => [
    { week: week.week_start.slice(5, 10), series: 'Commit', value: week.commits },
    { week: week.week_start.slice(5, 10), series: '新开 PR', value: week.prs_opened },
  ])
  const color = isDark.value ? '#bec8d0' : '#667480'
  const gridColor = isDark.value ? '#303942' : '#e6ebef'
  return {
    type: 'line', data, encode: { x: 'week', y: 'value', color: 'series' },
    scale: { color: { domain: ['Commit', '新开 PR'], range: ['#55b7f3', '#53c998'] } },
    style: { lineWidth: 2.5, lineJoin: 'round' },
    axis: { x: { labelFill: color, labelFontSize: 9, lineStroke: gridColor }, y: { labelFill: color, labelFontSize: 9, gridStroke: gridColor, gridLineDash: [3, 3] } },
    legend: { color: { position: 'bottom', itemLabelFill: color } },
    tooltip: { title: 'week', items: [{ field: 'series', name: '指标' }, { field: 'value', name: '周计数' }] },
  }
})

async function selectCandidate(repositoryId: number) {
  if (!scenario.value) return
  selectedId.value = repositoryId
  detailLoading.value = true
  try {
    candidateDetail.value = await getBrowserApiData<CandidateDetailResponse>(`/selection/scenarios/${scenario.value.slug}/candidates/${repositoryId}`)
  } catch (cause) {
    candidateDetail.value = null
    error.value = cause instanceof Error ? cause.message : '候选证据加载失败'
  } finally {
    detailLoading.value = false
  }
}

async function loadScenario(slug: string) {
  loading.value = true
  error.value = ''
  scenario.value = null
  viz.value = null
  candidateDetail.value = null
  try {
    const [detail, chart] = await Promise.all([
      getBrowserApiData<ScenarioDetail>(`/selection/scenarios/${slug}`),
      getBrowserApiData<ScenarioViz>(`/selection/scenarios/${slug}/viz`),
    ])
    scenario.value = detail
    viz.value = chart
    constraintFilter.value = 'all'
    const first = detail.candidates.find((candidate) => candidate.role === 'compare')
    if (first) await selectCandidate(first.repository_id)
    eligibilityFilter.value = 'all'
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '选型场景加载失败'
  } finally {
    loading.value = false
  }
}

function metricValue(candidate: ScenarioCandidate | null, key: string) {
  const metric = candidate?.metrics[key]
  if (!metric || metric.value === null) return '—'
  return metric.value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function metricStatus(metric: MetricEvidence | undefined) {
  if (!metric) return '未采集'
  if (metric.value === null) return metric.sample_count === 0 ? '无可计算样本' : '样本不足'
  if (metric.sample_count !== null && metric.sample_count < 5) return '证据不足'
  if (metric.sample_count !== null && metric.sample_count < 10) return '探索性'
  return metric.coverage_status === 'complete' ? '完整窗口' : metric.coverage_status
}

function capabilityStatusLabel(status: CapabilityEvidence['status']) {
  return ({ supported: '已证实支持', unsupported: '不支持', conditional: '有条件支持', unknown: '未知' } as const)[status]
}

function statusLabel(candidate: ScenarioCandidate) {
  if (candidate.metric_collection_status === 'pending_collection') return '待采集'
  if (candidate.eligibility === 'conditional') return '条件候选'
  if (candidate.eligibility === 'unknown') return '待核验'
  return candidate.metrics_ready ? '窗口完整' : '部分指标可用'
}

function openRepository(candidate: ScenarioCandidate | null) {
  if (candidate) window.open(candidate.html_url, '_blank', 'noopener,noreferrer')
}

onMounted(async () => {
  try {
    const result = await getBrowserApiData<{ scenarios: ScenarioSummary[] }>('/selection/scenarios')
    catalog.value = result.scenarios
    await loadScenario('go-http-api')
  } catch (cause) {
    loading.value = false
    error.value = cause instanceof Error ? cause.message : '选型场景目录加载失败'
  }
})
</script>

<template>
  <div class="app-page selection-page">
    <header class="selection-heading">
      <div>
        <h1 class="page-title">技术选型工作台</h1>
        <p class="page-description">先按项目场景和硬约束缩小范围，再并排查看同窗维护证据。页面不生成 GitHub 总分或默认冠军。</p>
      </div>
      <div class="selection-heading-actions">
        <RouterLink class="button button--outline" to="/selection/candidates">浏览 20 个同类仓库 <ArrowUpRight :size="14" /></RouterLink>
      </div>
    </header>

    <div class="scenario-tabs" role="tablist" aria-label="技术选型场景">
      <button v-for="item in catalog" :key="item.slug" class="scenario-tab" role="tab" :aria-selected="scenario?.slug === item.slug" @click="loadScenario(item.slug)">
        <span>{{ item.title }}</span><small>{{ item.ready_count }} 项完整 · {{ item.pending_count }} 项待采</small>
      </button>
    </div>

    <div v-if="loading" class="panel selection-state" role="status">正在读取版本化候选与来源窗口…</div>
    <div v-else-if="error && !scenario" class="panel selection-state selection-state--error" role="alert"><strong>选型数据暂不可用</strong><span>{{ error }}</span><button class="button button--outline" @click="loadScenario('go-http-api')">重新加载</button></div>
    <template v-else-if="scenario">
      <section class="scenario-brief">
        <div><h2>{{ scenario.title }}</h2><p>{{ scenario.purpose }}</p></div>
        <div class="snapshot-stamp"><span>快照</span><strong>{{ scenario.version }}</strong><span>截至 {{ scenario.as_of?.slice(0, 10) }}</span></div>
      </section>

      <div class="selection-toolbar">
        <div class="constraint-list"><span class="toolbar-label">先核对硬约束</span><span v-for="constraint in scenario.hard_constraints" :key="constraint" class="constraint-chip">{{ constraint }}</span></div>
        <label v-if="showNetHttpFilter" class="eligibility-control"><span>net/http 中间件</span><select v-model="constraintFilter"><option value="all">全部状态</option><option value="supported">已证实支持</option><option value="conditional">有条件支持</option><option value="unsupported">不支持</option><option value="unknown">未知</option></select></label>
        <label class="eligibility-control"><span>资格状态</span><select v-model="eligibilityFilter"><option value="all">全部候选</option><option value="eligible">可纳入候选</option><option value="conditional">条件候选</option><option value="ineligible">不满足条件</option><option value="unknown">待核验</option></select></label>
      </div>

      <div class="selection-note"><Info :size="14" /><span>当前快照来自 <strong>{{ scenario.source_datasets.join('、') }}</strong>。活动窗口 {{ scenario.window_policy.activity?.start.slice(0, 10) }} – {{ scenario.window_policy.activity?.end_exclusive.slice(0, 10) }} UTC；Release 单独观察 365 天。指标描述活动，不推断性能、质量或安全。</span></div>

      <section class="selection-main-grid">
        <article class="panel selection-canvas-panel">
          <div class="selection-panel-heading"><div><h3>同场景活动对照</h3><p>X/Y 为同一个 12 周 UTC 窗口的周均 Commit 与新开 PR，坐标使用 log1p；点位只画有真实窗口值的候选。</p></div><span class="data-count">{{ chartPoints.length }} 个有效节点</span></div>
          <div v-if="chartPoints.length" class="decision-chart"><DecisionScatterG2 :points="chartPoints" :selected-id="selectedId" :is-dark="isDark" @select="selectCandidate" /></div>
          <div v-else class="selection-empty">该场景没有覆盖完整且可绘制的活动指标。</div>
          <div class="candidate-list" aria-label="同场景候选列表">
            <button v-for="candidate in filteredCandidates" :key="candidate.repository_id" class="candidate-row" :class="{ 'candidate-row--active': selectedId === candidate.repository_id }" :aria-pressed="selectedId === candidate.repository_id" @click="selectCandidate(candidate.repository_id)">
              <span class="candidate-color" :style="{ background: palette[candidates.findIndex((item) => item.repository_id === candidate.repository_id) % palette.length] }" />
              <span class="candidate-name"><strong>{{ candidate.full_name }}</strong><small>{{ candidate.language }} · {{ candidate.inclusion_reason }}</small></span>
              <span class="candidate-status" :class="`candidate-status--${candidate.eligibility}`">{{ statusLabel(candidate) }}</span>
              <span v-if="candidate.role === 'supplement'" class="candidate-pending">指标待采</span>
            </button>
          </div>
        </article>

        <aside class="selection-detail-column">
          <article class="panel candidate-evidence-panel" aria-live="polite">
            <div class="selection-panel-heading"><div><h3>候选证据</h3><p>资格判断与数据可比性分别显示。</p></div><span class="evidence-mark" /></div>
            <div v-if="detailLoading" class="detail-loading">正在加载候选证据…</div>
            <template v-else-if="selectedCandidate">
              <div class="candidate-title-line"><strong>{{ selectedCandidate.full_name }}</strong><button class="icon-button" :aria-label="`在 GitHub 打开 ${selectedCandidate.full_name}`" @click="openRepository(selectedCandidate)"><ArrowUpRight :size="15" /></button></div>
              <p class="candidate-description">{{ selectedCandidate.description || selectedCandidate.inclusion_reason }}</p>
              <div class="evidence-status-row"><span>资格：<strong>{{ statusLabel(selectedCandidate) }}</strong></span><span>数据：<strong>{{ selectedCandidate.metrics_ready ? '完整可描述比较' : selectedCandidate.metric_collection_status === 'pending_collection' ? '待采集' : '部分维度有值' }}</strong></span></div>
              <div class="metric-evidence-grid">
                <div v-for="definition in metricDefinitions" :key="definition.key" class="metric-evidence">
                  <span>{{ definition.label }}</span><strong>{{ metricValue(selectedCandidate, definition.key) }}</strong>
                  <small>{{ selectedCandidate.metrics[definition.key]?.unit ?? definition.unit }} · n={{ selectedCandidate.metrics[definition.key]?.sample_count ?? '—' }}</small>
                  <em>{{ metricStatus(selectedCandidate.metrics[definition.key]) }}</em>
                </div>
              </div>
              <div class="evidence-source"><span>来源</span><a v-for="url in selectedCandidate.evidence_refs" :key="url" :href="url" target="_blank" rel="noreferrer">官方仓库记录 <ArrowUpRight :size="11" /></a><span class="muted">{{ selectedCandidate.metrics.weekly_commit_mean?.source_dataset ?? '无历史指标' }}</span></div>
              <div v-if="candidateDetail?.capabilities.length" class="capability-evidence-list">
                <div v-for="capability in candidateDetail.capabilities" :key="capability.capability_key" class="capability-evidence-item">
                  <div><strong>{{ capability.capability_key === 'net_http_middleware' ? '标准 net/http 中间件' : capability.capability_key }}</strong><span :class="`capability-status--${capability.status}`">{{ capabilityStatusLabel(capability.status) }}</span></div>
                  <p>{{ capability.rationale }}</p>
                  <small>{{ capability.applicable_version }} · 核验于 {{ capability.source_checked_at.slice(0, 10) }}</small>
                  <a :href="capability.evidence_url" target="_blank" rel="noreferrer">查看官方证据 <ArrowUpRight :size="11" /></a>
                </div>
              </div>
              <div v-else class="capability-unreviewed">该候选的功能/兼容性约束尚未核验；未知不代表不支持。</div>
              <div class="evidence-limits"><Info :size="13" /><span>{{ candidateDetail?.limitations[0] ?? '没有完整覆盖的指标保持空值，不会转成 0。' }}</span></div>
            </template>
            <div v-else class="selection-empty">选择候选以查看指标样本量与来源。</div>
          </article>
          <article class="conditional-advice"><span>条件化判断</span><p>活动快照不能替代项目的运行时、部署、许可和团队约束核验；当前证据不足以给出无条件推荐。</p></article>
        </aside>
      </section>

      <section class="selection-lower-grid">
        <article class="panel parallel-panel">
          <div class="selection-panel-heading"><div><h3>多维证据并列</h3><p>各轴保留自身原始单位；只有五项指标均有值的候选进入图表，其他候选仍显示在右侧原始证据表。Release 间隔不设默认优劣方向。</p></div></div>
          <G2Chart :spec="parallelSpec" label="完整指标候选的平行坐标；缺失指标候选保留在证据表中，不补零" :height="335" />
          <div class="parallel-note">{{ parallelExcludedCount }} 个候选因指标缺失未绘入平行坐标，仍保留原始证据。Issue / PR 耗时 n&lt;5 为证据不足；5–9 为探索性；n≥10 才满足描述性比较门槛，且仍须查看覆盖状态。</div>
        </article>
        <article class="panel activity-panel">
          <div class="selection-panel-heading"><div><h3>维护活动轨迹</h3><p>{{ selectedCandidate?.full_name ?? '选择一个候选' }} · 完整 12 周 UTC 记录</p></div></div>
          <G2Chart v-if="selectedViz?.weekly_activity?.length" :spec="activitySpec" label="选中候选的 12 周 Commit 与新开 PR 趋势" :height="288" />
          <div v-else class="selection-empty selection-empty--trend">{{ selectedCandidate?.metric_collection_status === 'pending_collection' ? '该候选尚未采集指标，时间轨迹留空。' : '此候选没有可用的完整 12 周活动轨迹。' }}</div>
        </article>
      </section>
    </template>
  </div>
</template>

<style scoped>
.selection-page { display:grid; gap:14px; }
.selection-heading { display:flex; align-items:flex-end; justify-content:space-between; gap:18px; }
.selection-heading-actions { display:flex; flex-wrap:wrap; align-items:center; justify-content:flex-end; gap:8px; }
.scenario-tabs { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:7px; }
.scenario-tab { display:grid; gap:5px; min-width:0; padding:10px 12px; border:1px solid var(--line); border-radius:8px; color:var(--muted); background:var(--surface); text-align:left; cursor:pointer; }
.scenario-tab[aria-selected="true"] { border-color:color-mix(in srgb,var(--primary) 52%,var(--line)); color:var(--ink); background:var(--primary-soft); box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--primary) 12%,transparent); }
.scenario-tab span { overflow:hidden; font-size:11.5px; font-weight:650; text-overflow:ellipsis; white-space:nowrap; }
.scenario-tab small { color:var(--muted); font-size:9.5px; }
.scenario-brief { display:flex; align-items:center; justify-content:space-between; gap:20px; padding:13px 15px; border-left:3px solid var(--primary); border-radius:0 8px 8px 0; background:var(--surface-soft); }
.scenario-brief h2 { margin:0; font-size:15px; }
.scenario-brief p { margin:5px 0 0; color:var(--muted); font-size:11px; line-height:1.5; }
.snapshot-stamp { display:grid; gap:2px; flex:0 0 auto; color:var(--muted); font-size:9.5px; text-align:right; }
.snapshot-stamp strong { color:var(--ink); font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:10px; }
.selection-toolbar { display:flex; align-items:center; justify-content:space-between; gap:14px; }
.constraint-list { display:flex; flex-wrap:wrap; align-items:center; gap:6px; }
.toolbar-label { margin-right:4px; color:var(--muted); font-size:10px; }
.constraint-chip { padding:5px 8px; border:1px solid var(--line); border-radius:999px; color:var(--ink); background:var(--surface); font-size:9.5px; }
.eligibility-control { display:flex; align-items:center; gap:7px; flex:0 0 auto; color:var(--muted); font-size:10px; }
.eligibility-control select { height:30px; padding:0 7px; border:1px solid var(--line); border-radius:6px; color:var(--ink); background:var(--surface); font-size:10px; }
.selection-note { display:flex; align-items:flex-start; gap:7px; padding:8px 10px; border:1px solid color-mix(in srgb,var(--primary) 22%,var(--line)); border-radius:7px; color:var(--muted); background:var(--primary-soft); font-size:10px; line-height:1.5; }
.selection-note svg { flex:0 0 auto; margin-top:1px; color:var(--primary-ink); }
.selection-note strong { color:var(--ink); }
.selection-main-grid { display:grid; grid-template-columns:minmax(0,1.55fr) minmax(280px,.85fr); gap:14px; align-items:start; }
.selection-canvas-panel,.candidate-evidence-panel { min-width:0; }
.selection-detail-column { display:grid; gap:10px; }
.selection-panel-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:10px; }
.selection-panel-heading h3 { margin:0; font-size:13px; font-weight:650; }
.selection-panel-heading p { margin:4px 0 0; color:var(--muted); font-size:10px; line-height:1.5; }
.data-count { padding:4px 7px; border:1px solid var(--line); border-radius:6px; color:var(--muted); font-size:9px; white-space:nowrap; }
.decision-chart { height:350px; }
.candidate-list { display:grid; gap:2px; margin-top:4px; }
.candidate-row { display:flex; width:100%; min-height:46px; align-items:center; gap:9px; padding:6px 8px; border:1px solid transparent; border-top-color:var(--line); border-radius:6px; color:var(--ink); background:transparent; text-align:left; cursor:pointer; }
.candidate-row:hover,.candidate-row--active { border-color:color-mix(in srgb,var(--primary) 24%,var(--line)); background:var(--primary-soft); }
.candidate-color { width:8px; height:8px; flex:0 0 auto; border-radius:50%; }
.candidate-name { display:grid; min-width:0; flex:1; gap:3px; }
.candidate-name strong { font-size:10.5px; }
.candidate-name small { overflow:hidden; color:var(--muted); font-size:9px; text-overflow:ellipsis; white-space:nowrap; }
.candidate-status,.candidate-pending { flex:0 0 auto; padding:4px 6px; border-radius:5px; color:var(--muted); background:var(--surface-soft); font-size:9px; }
.candidate-status--eligible { color:var(--green); }
.candidate-status--conditional { color:var(--amber); }
.candidate-status--unknown { color:var(--muted); }
.candidate-pending { color:#d78d33; background:color-mix(in srgb,#f2b35d 15%,var(--surface)); }
.evidence-mark { width:8px; height:8px; margin:4px; border-radius:50%; background:var(--primary); box-shadow:0 0 0 4px var(--primary-soft); }
.candidate-title-line { display:flex; align-items:center; justify-content:space-between; gap:8px; margin:14px 0 5px; }
.candidate-title-line strong { overflow-wrap:anywhere; font-size:15px; }
.candidate-description { margin:0 0 10px; color:var(--muted); font-size:10px; line-height:1.55; }
.evidence-status-row { display:flex; flex-wrap:wrap; gap:6px 13px; color:var(--muted); font-size:9.5px; }
.evidence-status-row strong { color:var(--ink); font-weight:600; }
.metric-evidence-grid { display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-top:11px; }
.metric-evidence { display:grid; gap:4px; min-width:0; padding:8px; border:1px solid var(--line); border-radius:7px; background:var(--surface-soft); }
.metric-evidence span { overflow:hidden; color:var(--muted); font-size:9px; text-overflow:ellipsis; white-space:nowrap; }
.metric-evidence strong { font-size:16px; font-variant-numeric:tabular-nums; }
.metric-evidence small { color:var(--muted); font-size:8.5px; }
.metric-evidence em { color:var(--primary-ink); font-size:8.5px; font-style:normal; }
.evidence-source { display:flex; flex-wrap:wrap; align-items:center; gap:6px 9px; margin-top:10px; color:var(--muted); font-size:9px; }
.evidence-source a { display:inline-flex; align-items:center; gap:3px; color:var(--primary-ink); }
.muted { color:var(--muted); }
.capability-evidence-list { display:grid; gap:6px; margin-top:10px; }
.capability-evidence-item { display:grid; gap:4px; padding:8px; border:1px solid var(--line); border-radius:7px; background:var(--surface-soft); }
.capability-evidence-item > div { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:8px; }
.capability-evidence-item strong { font-size:10px; }
.capability-evidence-item p { margin:0; color:var(--muted); font-size:9px; line-height:1.5; }
.capability-evidence-item small { color:var(--muted); font-size:8px; }
.capability-evidence-item a { display:inline-flex; align-items:center; gap:3px; width:max-content; color:var(--primary-ink); font-size:9px; }
.capability-status--supported { color:var(--green); font-size:9px; }
.capability-status--conditional { color:var(--amber); font-size:9px; }
.capability-status--unsupported { color:var(--red); font-size:9px; }
.capability-status--unknown { color:var(--muted); font-size:9px; }
.capability-unreviewed { margin-top:10px; padding:8px; border:1px dashed var(--line); border-radius:7px; color:var(--muted); font-size:9px; line-height:1.5; }
.evidence-limits { display:flex; align-items:flex-start; gap:5px; margin-top:9px; padding-top:8px; border-top:1px solid var(--line); color:var(--muted); font-size:9px; line-height:1.5; }
.evidence-limits svg { flex:0 0 auto; margin-top:1px; }
.conditional-advice { padding:10px 12px; border:1px solid var(--line); border-radius:8px; background:var(--surface-soft); }
.conditional-advice > span { color:var(--primary-ink); font-size:9px; font-weight:700; letter-spacing:.04em; }
.conditional-advice p { margin:5px 0 0; color:var(--muted); font-size:9.5px; line-height:1.5; }
.selection-lower-grid { display:grid; grid-template-columns:minmax(0,1.2fr) minmax(0,1fr); gap:14px; }
.parallel-panel,.activity-panel { min-width:0; }
.parallel-note { margin-top:4px; color:var(--muted); font-size:9px; line-height:1.45; }
.selection-empty { display:grid; min-height:180px; place-items:center; padding:18px; color:var(--muted); font-size:11px; text-align:center; }
.selection-empty--trend { min-height:250px; }
.selection-state { display:grid; min-height:180px; place-content:center; gap:12px; color:var(--muted); text-align:center; }
.selection-state--error strong { color:var(--ink); }
.detail-loading { padding:38px 12px; color:var(--muted); font-size:10px; text-align:center; }
@media (max-width:1120px) { .selection-main-grid { grid-template-columns:minmax(0,1.15fr) minmax(260px,.85fr); } }
@media (max-width:850px) { .selection-heading { align-items:flex-start; flex-direction:column; } .scenario-tabs { grid-template-columns:repeat(2,minmax(0,1fr)); } .selection-main-grid,.selection-lower-grid { grid-template-columns:minmax(0,1fr); } .selection-toolbar { align-items:flex-start; flex-direction:column; } .decision-chart { height:320px; } }
@media (prefers-reduced-motion:reduce) { *,*::before,*::after { scroll-behavior:auto !important; transition-duration:.01ms !important; animation-duration:.01ms !important; } }
</style>
