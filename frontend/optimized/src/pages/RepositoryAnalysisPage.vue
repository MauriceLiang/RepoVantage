<script setup lang="ts">
import { computed } from 'vue'
import { Activity, ArrowLeft, CalendarDays, GitCommitHorizontal, GitFork, GitPullRequest, Star } from 'lucide-vue-next'
import type { EChartsOption } from 'echarts'
import ChartPanel from '../components/ChartPanel.vue'
import type { Repository } from '../data/mockData'
import { repositoryWeeklyActivity, weekLabels, formatNumber } from '../data/mockData'

const props = defineProps<{ repository: Repository; tab: string; isDark: boolean }>()
const emit = defineEmits<{ updateTab: [tab: string]; back: [] }>()
const axisColor = computed(() => props.isDark ? '#a0a8b0' : '#6e7781')
const gridColor = computed(() => props.isDark ? '#2b3238' : '#e8ebed')
const weeklyData = computed(() => repositoryWeeklyActivity(props.repository))

const activityOption = computed<EChartsOption>(() => ({
  color: ['#2563eb'],
  tooltip: { trigger: 'axis', axisPointer: { type: 'line' } },
  grid: { top: 18, right: 18, bottom: 32, left: 38 },
  xAxis: { type: 'category', data: weekLabels, boundaryGap: false, axisLabel: { color: axisColor.value, fontSize: 9 }, axisLine: { lineStyle: { color: gridColor.value } }, axisTick: { show: false } },
  yAxis: { type: 'value', min: 0, axisLabel: { color: axisColor.value, fontSize: 9 }, axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: gridColor.value, type: 'dashed' } } },
  series: [{ type: 'line', smooth: .32, symbol: 'circle', symbolSize: 5, data: weeklyData.value.map((item) => item.commits), areaStyle: { opacity: .08 }, lineStyle: { width: 2.2 } }],
}))

const turnaroundOption = computed<EChartsOption>(() => ({
  color: ['#0ea5e9', '#1e40af'],
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  legend: { top: 0, right: 0, textStyle: { color: axisColor.value, fontSize: 9 }, itemWidth: 9, itemHeight: 9 },
  grid: { top: 30, right: 15, bottom: 32, left: 40 },
  xAxis: { type: 'category', data: ['8 月', '9 月', '10 月', '11 月'], axisLabel: { color: axisColor.value, fontSize: 9 }, axisLine: { lineStyle: { color: gridColor.value } }, axisTick: { show: false } },
  yAxis: { type: 'value', name: '小时', nameTextStyle: { color: axisColor.value, fontSize: 9 }, axisLabel: { color: axisColor.value, fontSize: 9 }, axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: gridColor.value, type: 'dashed' } } },
  series: [
    { name: 'Issue 关闭', type: 'bar', data: [props.repository.issueMedianHours * 1.16, props.repository.issueMedianHours * .97, props.repository.issueMedianHours * 1.08, props.repository.issueMedianHours], barMaxWidth: 19, itemStyle: { borderRadius: [3, 3, 0, 0] } },
    { name: 'PR 合并', type: 'bar', data: [props.repository.prMedianHours * 1.08, props.repository.prMedianHours * .91, props.repository.prMedianHours * 1.05, props.repository.prMedianHours], barMaxWidth: 19, itemStyle: { borderRadius: [3, 3, 0, 0] } },
  ],
}))

const releaseOption = computed<EChartsOption>(() => ({
  color: ['#0369a1'],
  tooltip: { trigger: 'axis' },
  grid: { top: 18, right: 16, bottom: 32, left: 40 },
  xAxis: { type: 'category', data: ['v1.4', 'v1.5', 'v1.6', 'v1.7', 'v1.8', 'v1.9'], axisLabel: { color: axisColor.value, fontSize: 9 }, axisLine: { lineStyle: { color: gridColor.value } }, axisTick: { show: false } },
  yAxis: { type: 'value', name: '间隔（天）', nameTextStyle: { color: axisColor.value, fontSize: 9 }, axisLabel: { color: axisColor.value, fontSize: 9 }, axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: gridColor.value, type: 'dashed' } } },
  series: [{ type: 'bar', data: [1.2, .82, 1.1, 1.34, .9, 1].map((factor) => Math.max(2, props.repository.releaseIntervalDays * factor)), barMaxWidth: 27, itemStyle: { borderRadius: [4, 4, 0, 0] } }],
}))

const tabs = [
  { value: 'overview', label: '概览' }, { value: 'activity', label: '活动' }, { value: 'issues', label: 'Issue' }, { value: 'prs', label: 'PR' }, { value: 'releases', label: 'Release' },
]
</script>

<template>
  <div class="stack">
    <UiButton variant="quiet" style="justify-self:start" @click="emit('back')"><ArrowLeft :size="13" />返回仓库列表</UiButton>
    <UiPanel as="section">
      <div class="detail-header">
        <div>
          <div class="repo-title-line"><h1 class="page-title">{{ repository.fullName }}</h1><UiBadge tone="accent">Mock 快照</UiBadge></div>
          <p class="repo-description-full">{{ repository.description }}</p>
          <div class="toolbar" style="margin-top:11px"><UiBadge><span class="language-dot" />{{ repository.language }}</UiBadge><UiBadge><Star :size="11" />{{ formatNumber(repository.stars) }} Stars</UiBadge><UiBadge><GitFork :size="11" />{{ formatNumber(repository.forks) }} Forks</UiBadge><UiBadge><CalendarDays :size="11" />创建于 {{ repository.createdYear }}</UiBadge></div>
        </div>
        <div class="page-actions"><span class="snapshot-label"><span class="status-dot" />数据覆盖 <strong>{{ repository.coverage }}%</strong></span><span class="snapshot-label">样例窗口 <strong>近 12 周</strong></span></div>
      </div>
    </UiPanel>

    <div class="detail-tabs" role="tablist" aria-label="仓库分析分类">
      <button v-for="item in tabs" :key="item.value" class="detail-tab" role="tab" :aria-selected="tab === item.value" @click="emit('updateTab', item.value)">{{ item.label }}</button>
    </div>

    <section class="kpi-grid" :aria-label="`${repository.fullName}关键指标`">
      <UiMetricCard label="周均 Commit" :value="repository.weeklyCommits.toFixed(1)" note="次 / 周 · 12 周窗口"><template #icon><GitCommitHorizontal :size="12" /></template></UiMetricCard>
      <UiMetricCard label="活跃周" :value="repository.activeWeeks" note="至少 1 次 Commit"><template #icon><Activity :size="12" /></template><template #value>{{ repository.activeWeeks }}<span class="muted" style="font-size:11px"> / 12</span></template></UiMetricCard>
      <UiMetricCard label="Issue 关闭中位数" :value="repository.issueMedianHours" note="最近 90 天样例"><template #icon><GitPullRequest :size="12" /></template><template #value>{{ repository.issueMedianHours }}<span class="muted" style="font-size:11px"> h</span></template></UiMetricCard>
      <UiMetricCard label="Release 间隔" :value="repository.releaseIntervalDays" note="最近 365 天样例"><template #icon><CalendarDays :size="12" /></template><template #value>{{ repository.releaseIntervalDays }}<span class="muted" style="font-size:11px"> 天</span></template></UiMetricCard>
    </section>

    <template v-if="tab === 'overview' || tab === 'activity'">
      <section class="detail-grid">
        <UiPanel as="article"><div class="panel-heading"><div><h2 class="panel-title">{{ tab === 'overview' ? '最近 12 周 Commit 活动' : '周级活动趋势' }}</h2><p class="panel-description">自然周汇总；横轴按 UTC 周结束日展示</p></div><UiBadge><GitCommitHorizontal :size="11" />{{ repository.weeklyCommits.toFixed(1) }} 次 / 周</UiBadge></div><ChartPanel :option="activityOption" :label="`${repository.fullName}最近 12 周 Commit 活动`" :height="300" /></UiPanel>
        <UiPanel as="article"><div class="panel-heading"><div><h2 class="panel-title">仓库概况</h2><p class="panel-description">与当前快照相邻展示，方便解释趋势</p></div></div><div class="details-list"><div class="detail-line"><span class="muted">主语言</span><strong>{{ repository.language }}</strong></div><div class="detail-line"><span class="muted">活跃周数</span><strong class="mono">{{ repository.activeWeeks }} / 12 周</strong></div><div class="detail-line"><span class="muted">周均 Commit</span><strong class="mono">{{ repository.weeklyCommits.toFixed(1) }}</strong></div><div class="detail-line"><span class="muted">数据覆盖</span><strong class="mono">{{ repository.coverage }}%</strong></div><div class="detail-line"><span class="muted">比较样例</span><strong>最近 90 天</strong></div></div><p class="helper-note">活动连续性和每周提交量是两项不同指标，分别描述规律与频率。</p></UiPanel>
      </section>
      <UiPanel as="article"><div class="panel-heading"><div><h2 class="panel-title">Issue / PR 处理耗时</h2><p class="panel-description">中位处理耗时按月展示；数值越低表示耗时越短</p></div></div><ChartPanel :option="turnaroundOption" label="Issue 关闭和 PR 合并耗时对照图" :height="250" /></UiPanel>
    </template>

    <template v-else-if="tab === 'issues' || tab === 'prs'">
      <section class="detail-grid">
        <UiPanel as="article"><div class="panel-heading"><div><h2 class="panel-title">{{ tab === 'issues' ? 'Issue 关闭耗时' : 'PR 合并耗时' }}</h2><p class="panel-description">最近 90 天样例记录的月度中位数</p></div><UiBadge>中位数 {{ tab === 'issues' ? repository.issueMedianHours : repository.prMedianHours }} 小时</UiBadge></div><ChartPanel :option="turnaroundOption" :label="tab === 'issues' ? 'Issue 关闭耗时趋势' : 'PR 合并耗时趋势'" :height="300" /></UiPanel>
        <UiPanel as="article"><div class="panel-heading"><div><h2 class="panel-title">处理概况</h2><p class="panel-description">完整样例下的处理节奏参考</p></div></div><div class="details-list"><div class="detail-line"><span class="muted">观察窗口</span><strong>最近 90 天</strong></div><div class="detail-line"><span class="muted">记录覆盖</span><strong class="mono">{{ repository.coverage }}%</strong></div><div class="detail-line"><span class="muted">当前中位数</span><strong class="mono">{{ tab === 'issues' ? repository.issueMedianHours : repository.prMedianHours }} 小时</strong></div><div class="detail-line"><span class="muted">相对周均 Commit</span><strong class="mono">{{ repository.weeklyCommits.toFixed(1) }} 次 / 周</strong></div></div><p class="helper-note">演示版不展示真实 Issue 标题或 PR 作者；此处只呈现汇总值。</p></UiPanel>
      </section>
      <UiPanel as="article"><div class="panel-heading"><div><h2 class="panel-title">月度样例记录</h2><p class="panel-description">用表格保留精确读数，并与上方图表对应</p></div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>月份</th><th>关闭 / 合并数量</th><th>中位耗时</th><th>较上月变化</th></tr></thead><tbody><tr v-for="(month, index) in ['2026-08', '2026-09', '2026-10', '2026-11']" :key="month"><td class="mono">{{ month }}</td><td>{{ 22 + ((Number(repository.id) * 7 + index * 9) % 68) }}</td><td class="mono">{{ (tab === 'issues' ? repository.issueMedianHours : repository.prMedianHours) * [1.16, .97, 1.08, 1][index] }} 小时</td><td :style="{ color: index === 3 ? 'var(--green)' : 'var(--muted)' }">{{ index === 3 ? '与前月持平' : '按样例数据变化' }}</td></tr></tbody></table></div></UiPanel>
    </template>

    <template v-else>
      <section class="detail-grid"><UiPanel as="article"><div class="panel-heading"><div><h2 class="panel-title">Release 间隔趋势</h2><p class="panel-description">最近 6 个版本之间的天数</p></div><UiBadge>平均 {{ repository.releaseIntervalDays }} 天</UiBadge></div><ChartPanel :option="releaseOption" label="最近 6 个版本的 Release 间隔图" :height="310" /></UiPanel><UiPanel as="article"><div class="panel-heading"><div><h2 class="panel-title">发布节奏摘要</h2><p class="panel-description">时间窗与版本节奏放在一起阅读</p></div></div><div class="details-list"><div class="detail-line"><span class="muted">观察窗口</span><strong>最近 365 天</strong></div><div class="detail-line"><span class="muted">平均 Release 间隔</span><strong class="mono">{{ repository.releaseIntervalDays }} 天</strong></div><div class="detail-line"><span class="muted">最近版本</span><strong class="mono">v1.9.0 · 2026-11-08</strong></div><div class="detail-line"><span class="muted">近一年版本数</span><strong class="mono">{{ Math.max(2, Math.round(365 / repository.releaseIntervalDays)) }}</strong></div></div><p class="helper-note">间隔按相邻样例版本日期计算，越短表示发布更频繁，不代表版本质量。</p></UiPanel></section>
    </template>
  </div>
</template>
