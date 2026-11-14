<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowRight, Check, Plus, RotateCcw, SlidersHorizontal, X } from 'lucide-vue-next'
import type { EChartsOption } from 'echarts'
import ChartPanel from '../components/ChartPanel.vue'
import type { MetricKey, Repository } from '../data/mockData'

const props = defineProps<{ repositories: Repository[]; compareIds: string[]; weights: Record<MetricKey, number>; isDark: boolean }>()
const emit = defineEmits<{ updateCompare: [ids: string[]]; updateWeights: [weights: Record<MetricKey, number>]; openRepository: [repository: Repository] }>()

const weightKeys: MetricKey[] = ['commits', 'issueHours', 'prHours', 'releaseDays']
const metrics: { key: MetricKey; label: string; note: string; direction: 'high' | 'low'; color: string; unit: string }[] = [
  { key: 'commits', label: '每周 Commit', note: '越多越好', direction: 'high', color: 'var(--primary)', unit: '次 / 周' },
  { key: 'issueHours', label: 'Issue 关闭耗时', note: '越短越好', direction: 'low', color: 'var(--sky)', unit: '小时' },
  { key: 'prHours', label: 'PR 合并耗时', note: '越短越好', direction: 'low', color: 'var(--blue)', unit: '小时' },
  { key: 'releaseDays', label: 'Release 间隔', note: '越短越好', direction: 'low', color: 'var(--blue-deep)', unit: '天' },
]
const candidateIds = computed(() => props.compareIds.slice(0, 5))
const candidates = computed(() => candidateIds.value.map((id) => props.repositories.find((repository) => repository.id === id)).filter((repository): repository is Repository => Boolean(repository)))
const available = computed(() => props.repositories.filter((repository) => !candidateIds.value.includes(repository.id)))
const availableOptions = computed(() => available.value.map((repository) => ({ value: repository.id, label: repository.fullName })))
const addId = ref('')
const manualOpen = ref(false)
const manualDraft = ref<Record<MetricKey, number>>({ ...props.weights })
const manualError = ref('')
const axisColor = computed(() => props.isDark ? '#a0a8b0' : '#6e7781')
const gridColor = computed(() => props.isDark ? '#2b3238' : '#e8ebed')
const repoColors = ['#2563eb', '#0284c7', '#0ea5e9', '#1d4ed8', '#1e40af']

watch(() => props.weights, (weights) => { manualDraft.value = { ...weights } }, { deep: true })

function rawValue(repository: Repository, key: MetricKey) {
  if (key === 'commits') return repository.weeklyCommits
  if (key === 'issueHours') return repository.issueMedianHours
  if (key === 'prHours') return repository.prMedianHours
  return repository.releaseIntervalDays
}

function metricValue(repository: Repository, key: MetricKey) {
  const value = rawValue(repository, key)
  return `${key === 'commits' ? value.toFixed(1) : value.toFixed(1)} ${metrics.find((metric) => metric.key === key)?.unit}`
}

function metricScore(repository: Repository, metric: (typeof metrics)[number]) {
  const values = candidates.value.map((candidate) => rawValue(candidate, metric.key))
  const minimum = Math.min(...values)
  const maximum = Math.max(...values)
  if (maximum === minimum) return 50
  const normalized = metric.direction === 'high'
    ? (rawValue(repository, metric.key) - minimum) / (maximum - minimum)
    : (maximum - rawValue(repository, metric.key)) / (maximum - minimum)
  return normalized * 100
}

const ranking = computed(() => candidates.value.map((repository) => {
  const parts = Object.fromEntries(metrics.map((metric) => [metric.key, metricScore(repository, metric)])) as Record<MetricKey, number>
  const score = metrics.reduce((total, metric) => total + parts[metric.key] * props.weights[metric.key] / 100, 0)
  return { repository, score, parts }
}).sort((left, right) => right.score - left.score))
const totalWeight = computed(() => weightKeys.reduce((total, key) => total + props.weights[key], 0))
const topId = computed(() => ranking.value[0]?.repository.id ?? null)

const scoreOption = computed<EChartsOption>(() => ({
  color: [repoColors[0]],
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (parameter: unknown) => {
    const item = (Array.isArray(parameter) ? parameter[0] : parameter) as { name?: string; value?: number }
    return `${item.name ?? ''}<br/>综合分：${Number(item.value ?? 0).toFixed(1)} / 100`
  } },
  grid: { top: 10, right: 18, bottom: 18, left: 112 },
  xAxis: { type: 'value', min: 0, max: 100, axisLabel: { color: axisColor.value, fontSize: 9 }, axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: gridColor.value, type: 'dashed' } } },
  yAxis: { type: 'category', data: ranking.value.map((row) => row.repository.name).reverse(), axisLabel: { color: axisColor.value, fontSize: 9, width: 100, overflow: 'truncate' }, axisLine: { show: false }, axisTick: { show: false } },
  series: [{ type: 'bar', data: ranking.value.map((row) => Number(row.score.toFixed(1))).reverse(), barMaxWidth: 18, itemStyle: { borderRadius: [0, 5, 5, 0] }, label: { show: true, position: 'right', color: axisColor.value, fontSize: 9, formatter: '{c}' } }],
}))

function roundUnit(value: number) { return Math.round(value * 10) }

function distributeWeight(key: MetricKey, rawTarget: number) {
  const targetUnits = Math.max(0, Math.min(1000, roundUnit(rawTarget)))
  const otherKeys = weightKeys.filter((item) => item !== key)
  const otherUnits = otherKeys.map((item) => roundUnit(props.weights[item]))
  const totalOtherUnits = otherUnits.reduce((total, value) => total + value, 0)
  const remainder = 1000 - targetUnits
  let assigned: number[]

  if (totalOtherUnits === 0) {
    assigned = otherKeys.map(() => Math.floor(remainder / otherKeys.length))
    for (let index = 0; index < remainder - assigned.reduce((total, value) => total + value, 0); index++) assigned[index] += 1
  } else {
    const exact = otherUnits.map((value) => remainder * value / totalOtherUnits)
    assigned = exact.map(Math.floor)
    let leftover = remainder - assigned.reduce((total, value) => total + value, 0)
    const order = exact.map((value, index) => ({ index, fraction: value - Math.floor(value) })).sort((left, right) => right.fraction - left.fraction)
    for (let index = 0; index < leftover; index++) assigned[order[index % order.length].index] += 1
  }

  const next = { ...props.weights, [key]: targetUnits / 10 } as Record<MetricKey, number>
  otherKeys.forEach((item, index) => { next[item] = assigned[index] / 10 })
  emit('updateWeights', next)
}

function applyManualWeights() {
  const total = weightKeys.reduce((sum, key) => sum + Number(manualDraft.value[key]), 0)
  if (weightKeys.some((key) => !Number.isFinite(manualDraft.value[key]) || manualDraft.value[key] < 0 || manualDraft.value[key] > 100)) {
    manualError.value = '每项权重需在 0–100 之间。'
    return
  }
  if (Math.abs(total - 100) > 0.01) {
    manualError.value = `当前合计 ${total.toFixed(1)}%，请调整到 100%。`
    return
  }
  manualError.value = ''
  emit('updateWeights', { ...manualDraft.value })
  manualOpen.value = false
}

function addCandidate() {
  if (!addId.value || candidateIds.value.length >= 5) return
  emit('updateCompare', [...candidateIds.value, addId.value])
  addId.value = ''
}

function removeCandidate(id: string) {
  emit('updateCompare', candidateIds.value.filter((item) => item !== id))
}

function presetEven() {
  const base = 25
  emit('updateWeights', { commits: base, issueHours: base, prHours: base, releaseDays: base })
}
</script>

<template>
  <div class="stack">
    <UiPageHeader title="项目比较" description="同一组候选使用同一套归一化口径。调整权重后分数即时更新，不触发数据请求。">
      <template #title-extra><UiBadge tone="accent">Mock 指标</UiBadge></template>
      <template #actions><span class="snapshot-label">观察窗口 <strong>最近 90 天</strong></span></template>
    </UiPageHeader>

    <section class="comparison-top">
      <UiPanel>
        <div class="panel-heading"><div><h2 class="panel-title">比较候选 <span class="muted">{{ candidates.length }} / 5</span></h2><p class="panel-description">最多选择 5 个仓库；点击名称可查看单仓分析。</p></div><span class="badge">同一时间窗口</span></div>
        <TransitionGroup name="candidate" tag="div" class="candidate-list">
          <span v-for="(repository, index) in candidates" :key="repository.id" class="candidate-chip"><span class="language-dot" :style="{ background: repoColors[index] }" /><button class="repo-link" type="button" @click="emit('openRepository', repository)">{{ repository.fullName }}</button><button type="button" :aria-label="`移除 ${repository.fullName}`" @click="removeCandidate(repository.id)"><X :size="12" /></button></span>
          <span v-if="!candidates.length" key="empty-candidates" class="small muted">尚未选择候选仓库，请先从仓库页勾选。</span>
        </TransitionGroup>
        <div v-if="available.length && candidates.length < 5" class="toolbar" style="margin-top:13px">
          <UiSelect v-model="addId" label="添加比较仓库" placeholder="添加仓库…" :options="availableOptions" searchable search-placeholder="搜索仓库名称" style="width:min(480px, 100%)" />
          <UiButton variant="outline" :disabled="!addId" @click="addCandidate"><Plus :size="12" />添加候选</UiButton>
        </div>
      </UiPanel>
      <UiPanel>
        <div class="panel-heading"><div><h2 class="panel-title">分数口径</h2><p class="panel-description">对候选内各项指标做 0–100 归一化后加权。</p></div><SlidersHorizontal :size="15" class="muted" /></div>
        <div class="details-list">
          <div class="detail-line"><span class="muted">向好方向</span><strong>Commit 越多；耗时越短</strong></div>
          <div class="detail-line"><span class="muted">单项相同</span><strong>各候选记 50 分</strong></div>
          <div class="detail-line"><span class="muted">综合分</span><strong>单项归一化分 × 权重</strong></div>
        </div>
        <p class="helper-note">分数表示当前候选组内的相对排序，不是成功概率。</p>
      </UiPanel>
    </section>

    <UiPanel as="section">
      <div class="panel-heading"><div><h2 class="panel-title">权重设置</h2><p class="panel-description">总权重固定为 100%。拖动任一滑块，其他指标按当前比例自动分配剩余权重。</p></div><div class="toolbar"><UiBadge :tone="Math.abs(totalWeight - 100) < 0.01 ? 'success' : 'warning'">总权重 {{ totalWeight.toFixed(1) }}%</UiBadge><UiButton variant="quiet" @click="presetEven"><RotateCcw :size="12" />平均分配</UiButton><UiButton variant="outline" :aria-expanded="manualOpen" @click="manualOpen = !manualOpen"><SlidersHorizontal :size="12" />{{ manualOpen ? '收起手动输入' : '手动输入' }}</UiButton></div></div>
      <div class="weight-list">
        <label v-for="metric in metrics" :key="metric.key" class="weight-row">
          <span class="weight-title"><span class="language-dot" :style="{ background: metric.color }" />{{ metric.label }} <span class="muted">{{ metric.note }}</span></span>
          <input class="weight-range" type="range" min="0" max="100" step="0.1" :value="weights[metric.key]" :aria-label="`${metric.label}权重`" :aria-valuetext="`${weights[metric.key].toFixed(1)}%`" :style="{ '--fill': `${weights[metric.key]}%` }" @input="distributeWeight(metric.key, Number(($event.target as HTMLInputElement).value))" />
          <span class="weight-number mono">{{ weights[metric.key].toFixed(1) }}%</span>
        </label>
      </div>
      <UiPanel v-if="manualOpen" tight style="margin-top:11px;background:var(--surface-soft)">
        <div class="manual-grid">
          <label v-for="metric in metrics" :key="metric.key" class="manual-field">{{ metric.label }}（%）<UiInput v-model.number="manualDraft[metric.key]" class="mono" size="sm" type="number" min="0" max="100" step="0.1" /></label>
        </div>
        <div class="toolbar" style="justify-content:space-between;margin-top:10px"><span class="small" :style="{ color: manualError ? 'var(--red)' : 'var(--muted)' }">{{ manualError || `当前手动合计 ${weightKeys.reduce((sum, key) => sum + Number(manualDraft[key] || 0), 0).toFixed(1)}%` }}</span><UiButton variant="primary" @click="applyManualWeights"><Check :size="12" />应用权重</UiButton></div>
      </UiPanel>
    </UiPanel>

    <section class="weight-layout">
      <UiPanel>
        <div class="panel-heading"><div><h2 class="panel-title">综合排名</h2><p class="panel-description">当前权重下即时重算；单项贡献保留一位小数。</p></div><UiBadge>{{ metrics.filter((metric) => weights[metric.key] > 0).length }} 项参与评分</UiBadge></div>
        <template v-if="candidates.length >= 2">
          <TransitionGroup name="ranking-transition" tag="div" class="score-list">
            <UiPanel v-for="(row, index) in ranking" :key="row.repository.id" as="article" tight class="ranking-card" :data-rank="index + 1">
              <div class="panel-heading" style="align-items:center;margin-bottom:9px">
                <div class="repo-title-line"><UiBadge>{{ index + 1 }}</UiBadge><button class="repo-link" type="button" @click="emit('openRepository', row.repository)">{{ row.repository.fullName }}</button><UiBadge v-if="row.repository.id === topId" tone="success">当前领先</UiBadge></div>
                <div class="score-value mono" style="font-size:22px">{{ row.score.toFixed(1) }}<span class="muted" style="font-size:10px;font-weight:400"> /100</span></div>
              </div>
              <div class="score-track" role="progressbar" :aria-label="`${row.repository.fullName} 综合分`" :aria-valuenow="Number(row.score.toFixed(1))" aria-valuemin="0" aria-valuemax="100"><div class="score-fill" :style="{ width: `${row.score}%` }" /></div>
              <div class="metric-score-grid" style="margin-top:10px">
                <div v-for="metric in metrics" :key="metric.key" class="metric-score"><div class="metric-score-label"><span>{{ metric.label }}</span><span>权重 {{ weights[metric.key].toFixed(1) }}%</span></div><div class="metric-score-value mono">{{ metricValue(row.repository, metric.key) }}</div><div class="small muted" style="margin-top:4px">单项 {{ row.parts[metric.key].toFixed(1) }} · 贡献 {{ (row.parts[metric.key] * weights[metric.key] / 100).toFixed(1) }} 分</div></div>
              </div>
            </UiPanel>
          </TransitionGroup>
        </template>
        <div v-else class="empty-state"><strong>至少选择 2 个仓库</strong><span>可从仓库页勾选，也可以在上方添加候选。</span></div>
      </UiPanel>

      <UiPanel>
        <div class="panel-heading"><div><h2 class="panel-title">分数对照</h2><p class="panel-description">候选集合内 Min–Max 归一化</p></div><ArrowRight :size="14" class="muted" /></div>
        <ChartPanel v-if="ranking.length" :option="scoreOption" label="仓库综合分横向对照图" :height="Math.max(180, ranking.length * 46)" />
        <div v-else class="empty-state"><strong>添加候选后显示分数</strong><span>权重和分数会保持同步。</span></div>
        <div class="notice">缺失值在本 Mock 版本已用完整样例覆盖。所有分数以当前候选中的相对表现计算，权重调整只在浏览器本地生效。</div>
      </UiPanel>
    </section>
  </div>
</template>
