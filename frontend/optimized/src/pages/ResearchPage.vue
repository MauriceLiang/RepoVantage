<script setup lang="ts">
import { computed, ref } from 'vue'
import { Database, Info, Search } from 'lucide-vue-next'
import type { EChartsOption } from 'echarts'
import ChartPanel from '../components/ChartPanel.vue'
import type { Repository } from '../data/mockData'
import { formatNumber, researchCoverage } from '../data/mockData'

const props = defineProps<{ repositories: Repository[]; isDark: boolean }>()
defineEmits<{ openRepository: [repository: Repository] }>()
const query = ref('')
const languageFilter = ref('全部语言')
const axisColor = computed(() => props.isDark ? '#a0a8b0' : '#6e7781')
const gridColor = computed(() => props.isDark ? '#2b3238' : '#e8ebed')

const languageGroups = computed(() => {
  const groups = new Map<string, Repository[]>()
  props.repositories.forEach((repository) => {
    const group = groups.get(repository.language) ?? []
    group.push(repository)
    groups.set(repository.language, group)
  })
  return [...groups.entries()].map(([language, items]) => ({
    language,
    count: items.length,
    weeklyCommits: items.reduce((total, item) => total + item.weeklyCommits, 0) / items.length,
    issueHours: items.reduce((total, item) => total + item.issueMedianHours, 0) / items.length,
    activeWeeks: items.reduce((total, item) => total + item.activeWeeks, 0) / items.length,
  })).sort((left, right) => right.count - left.count)
})
const languages = computed(() => ['全部语言', ...languageGroups.value.map((group) => group.language)])
const languageOptions = computed(() => languages.value.map((label) => ({ value: label, label })))
const visibleRepositories = computed(() => props.repositories.filter((repository) => {
  const text = `${repository.fullName} ${repository.language}`.toLocaleLowerCase()
  return (!query.value || text.includes(query.value.trim().toLocaleLowerCase())) && (languageFilter.value === '全部语言' || repository.language === languageFilter.value)
}).slice(0, 10))
const completeCommitRepositories = computed(() => props.repositories.length)
const axis = computed(() => ({ color: axisColor.value, fontSize: 9 }))
const splitLine = computed(() => ({ lineStyle: { color: gridColor.value, type: 'dashed' as const } }))

const groupOption = computed<EChartsOption>(() => ({
  color: ['#2563eb', '#0284c7'],
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  legend: { top: 0, right: 3, textStyle: { color: axisColor.value, fontSize: 9 }, itemWidth: 9, itemHeight: 9 },
  grid: { top: 34, right: 10, bottom: 10, left: 82 },
  xAxis: { type: 'value', axisLabel: axis.value, axisLine: { show: false }, axisTick: { show: false }, splitLine: splitLine.value },
  yAxis: { type: 'category', data: languageGroups.value.slice(0, 8).map((group) => group.language).reverse(), axisLabel: axis.value, axisLine: { show: false }, axisTick: { show: false } },
  series: [
    { name: '仓库数', type: 'bar', data: languageGroups.value.slice(0, 8).map((group) => group.count).reverse(), barMaxWidth: 11, itemStyle: { borderRadius: [0, 3, 3, 0] } },
    { name: '周均 Commit', type: 'bar', data: languageGroups.value.slice(0, 8).map((group) => Number(group.weeklyCommits.toFixed(1))).reverse(), barMaxWidth: 11, itemStyle: { borderRadius: [0, 3, 3, 0] } },
  ],
}))

const scatterOption = computed<EChartsOption>(() => ({
  color: ['#0284c7'],
  tooltip: { trigger: 'item', formatter: (parameter: unknown) => {
    const item = parameter as { data?: number[] }
    const point = item.data ?? []
    return `周均 Commit：${Number(point[0] ?? 0).toFixed(1)} 次<br/>Issue 关闭中位数：${Number(point[1] ?? 0).toFixed(1)} 小时`
  } },
  grid: { top: 12, right: 18, bottom: 36, left: 48 },
  xAxis: { type: 'value', name: '周均 Commit（次）', nameLocation: 'middle', nameGap: 24, nameTextStyle: { color: axisColor.value, fontSize: 9 }, axisLabel: axis.value, axisLine: { lineStyle: { color: gridColor.value } }, splitLine: { show: false } },
  yAxis: { type: 'value', name: 'Issue 关闭（小时）', nameTextStyle: { color: axisColor.value, fontSize: 9 }, axisLabel: axis.value, axisLine: { show: false }, axisTick: { show: false }, splitLine: splitLine.value },
  series: [{ type: 'scatter', symbolSize: 6, data: props.repositories.map((repository) => [repository.weeklyCommits, repository.issueMedianHours]), itemStyle: { opacity: .45 } }],
}))

function percent(value: number, total: number) { return total > 0 ? value / total * 100 : 0 }
</script>

<template>
  <div class="stack">
    <UiPageHeader title="研究分析" description="在同一批 Mock 仓库中查看分组差异、维护活动与数据覆盖。页面不切换样本，不会触发采集。">
      <template #title-extra><UiBadge tone="accent"><Database :size="11" />固定 300 仓库样例</UiBadge></template>
      <template #actions><span class="snapshot-label">观察窗口 <strong>12 个完整周</strong></span></template>
    </UiPageHeader>

    <div class="notice"><Info :size="13" style="vertical-align:-2px;margin-right:4px" />演示数据已固定为完整样例，仅用于体验筛选、图表和仓库跳转；不代表数据库测量值。</div>

    <section class="kpi-grid" aria-label="研究样本概览">
      <UiMetricCard label="样例仓库" :value="formatNumber(repositories.length)" note="全部进入本次分析" />
      <UiMetricCard label="周级记录" :value="formatNumber(repositories.length * 12)" note="仓库 × 12 周" />
      <UiMetricCard label="Commit 完整覆盖" :value="`${completeCommitRepositories} / ${repositories.length}`" note="最近 12 周样例" />
      <UiMetricCard label="可比较指标" :value="4" note="Commit、Issue、PR、Release" />
    </section>

    <section class="research-grid">
      <UiPanel as="article"><div class="panel-heading"><div><h2 class="panel-title">语言分组与活动</h2><p class="panel-description">横向比较各语言的样例仓库数与周均 Commit</p></div><UiBadge>前 8 组</UiBadge></div><ChartPanel :option="groupOption" label="各语言仓库数量和周均 Commit 对照图" :height="310" /></UiPanel>
      <UiPanel as="article"><div class="panel-heading"><div><h2 class="panel-title">维护活动关系</h2><p class="panel-description">每个点为一个仓库；坐标分别表示提交频率和 Issue 耗时</p></div><UiBadge>n={{ repositories.length }}</UiBadge></div><ChartPanel :option="scatterOption" label="周均 Commit 和 Issue 关闭耗时散点图" :height="310" /></UiPanel>
    </section>

    <section class="research-grid">
      <UiPanel as="article">
        <div class="panel-heading"><div><h2 class="panel-title">指标覆盖</h2><p class="panel-description">完整、部分与总记录数分别展示</p></div><UiBadge tone="success">样例无缺项</UiBadge></div>
        <div class="coverage-list">
          <div v-for="item in researchCoverage" :key="item.key" class="coverage-row">
            <div class="coverage-heading"><strong>{{ item.label }}</strong><span class="mono">{{ formatNumber(item.complete) }} / {{ formatNumber(item.total) }}（{{ percent(item.complete, item.total).toFixed(1) }}%）</span></div>
            <div class="progress-track" role="progressbar" :aria-label="`${item.label}完整覆盖率`" :aria-valuenow="Number(percent(item.complete, item.total).toFixed(1))" aria-valuemin="0" aria-valuemax="100"><div class="progress-fill" :style="{ width: `${percent(item.complete, item.total)}%` }" /></div>
            <div v-if="item.partial" class="small muted">另有 {{ formatNumber(item.partial) }} 条部分覆盖，图表会单独标记。</div>
          </div>
        </div>
        <p class="helper-note">覆盖率用于说明样例记录是否齐全，不是仓库质量分。</p>
      </UiPanel>
      <UiPanel as="article">
        <div class="panel-heading"><div><h2 class="panel-title">按语言查看仓库</h2><p class="panel-description">搜索或筛选后，点击仓库名称进入单仓分析</p></div></div>
        <div class="toolbar" style="margin-bottom:10px">
          <label class="search-field"><Search :size="13" /><UiInput v-model="query" type="search" aria-label="搜索研究仓库" placeholder="搜索仓库" /></label>
          <UiSelect v-model="languageFilter" label="研究语言筛选" :options="languageOptions" style="width:170px" />
        </div>
        <TransitionGroup name="research-result" tag="div" class="details-list">
          <button v-for="repository in visibleRepositories" :key="repository.id" class="detail-line" style="width:100%;border-right:0;border-left:0;border-top:0;text-align:left;background:transparent;cursor:pointer" @click="$emit('openRepository', repository)">
            <span><strong>{{ repository.fullName }}</strong><span class="small muted"> · {{ repository.language }}</span></span><span class="mono">{{ repository.weeklyCommits.toFixed(1) }} / 周</span>
          </button>
          <div v-if="!visibleRepositories.length" key="empty-research-results" class="empty-state" style="min-height:100px"><strong>没有匹配的仓库</strong><span>调整搜索或语言筛选。</span></div>
        </TransitionGroup>
        <p class="helper-note">显示前 10 个匹配结果；当前匹配 {{ formatNumber(repositories.filter((repository) => (!query || `${repository.fullName} ${repository.language}`.toLocaleLowerCase().includes(query.toLocaleLowerCase())) && (languageFilter === '全部语言' || repository.language === languageFilter)).length) }} 个。</p>
      </UiPanel>
    </section>
  </div>
</template>
