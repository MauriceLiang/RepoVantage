<script setup lang="ts">
import { computed, ref } from 'vue'
import { Activity, CheckCircle2, CircleAlert, Clock3, RefreshCw } from 'lucide-vue-next'
import type { MockTask } from '../data/mockData'

const props = defineProps<{ tasks: MockTask[] }>()
defineEmits<{ retry: [id: string]; refresh: [] }>()
const filter = ref('全部')
const filters = ['全部', '进行中', '排队中', '已完成', '部分完成']
const taskRows = computed(() => props.tasks.filter((task) => {
  if (filter.value === '进行中') return task.status === 'running'
  if (filter.value === '排队中') return task.status === 'queued'
  if (filter.value === '已完成') return task.status === 'done'
  if (filter.value === '部分完成') return task.status === 'partial'
  return true
}))
const counts = computed(() => ({
  running: props.tasks.filter((task) => task.status === 'running').length,
  queued: props.tasks.filter((task) => task.status === 'queued').length,
  done: props.tasks.filter((task) => task.status === 'done').length,
  partial: props.tasks.filter((task) => task.status === 'partial').length,
}))
function statusText(task: MockTask) {
  return ({ running: '执行中', queued: '排队中', done: '已完成', partial: '部分完成' } as const)[task.status]
}
function icon(task: MockTask) {
  return task.status === 'done' ? CheckCircle2 : task.status === 'partial' ? CircleAlert : task.status === 'running' ? Activity : Clock3
}
</script>

<template>
  <div class="stack">
    <UiPageHeader title="任务中心" description="查看采集与分析任务的当前阶段。这里的队列变化只在本地演示，不会运行后台采集。">
      <template #title-extra><UiBadge tone="accent">Mock 状态</UiBadge></template>
      <template #actions><UiButton variant="outline" @click="$emit('refresh')"><RefreshCw :size="13" />刷新样例</UiButton></template>
    </UiPageHeader>

    <section class="kpi-grid" aria-label="任务状态概览">
      <UiMetricCard label="执行中" :value="counts.running" note="当前阶段有进度" />
      <UiMetricCard label="排队中" :value="counts.queued" note="等待开始" />
      <UiMetricCard label="已完成" :value="counts.done" note="样例任务" />
      <UiMetricCard label="部分完成" :value="counts.partial" note="可模拟重试" />
    </section>

    <UiPanel as="section">
      <div class="panel-heading"><div><h2 class="panel-title">任务记录</h2><p class="panel-description">进度条只出现在确定数值的任务；排队状态不显示虚构百分比。</p></div><div class="segmented" role="group" aria-label="任务状态筛选"><button v-for="item in filters" :key="item" class="segment" :aria-pressed="filter === item" @click="filter = item">{{ item }}</button></div></div>
      <div class="task-list">
        <article v-for="task in taskRows" :key="task.id" class="task-row">
          <div class="repository-cell"><strong class="repo-link">{{ task.repository }}</strong><div class="small muted" style="margin-top:4px">{{ task.module }} · {{ task.stage }}</div></div>
          <UiBadge :tone="task.status === 'partial' ? 'warning' : task.status === 'done' || task.status === 'running' ? 'success' : 'neutral'"><component :is="icon(task)" :size="11" />{{ statusText(task) }}</UiBadge>
          <div v-if="task.progress !== null" class="task-progress" role="progressbar" :aria-label="`${task.repository}任务进度`" :aria-valuenow="task.progress" aria-valuemin="0" aria-valuemax="100"><span :style="{ width: `${task.progress}%` }" /></div>
          <span v-else class="small muted">等待阶段更新</span>
          <span class="mono small muted">{{ task.progress ?? '—' }}{{ task.progress === null ? '' : '%' }}</span>
          <UiButton v-if="task.status === 'partial'" variant="outline" @click="$emit('retry', task.id)"><RefreshCw :size="12" />重试</UiButton>
          <span v-else class="small muted">{{ task.updated }}</span>
        </article>
        <div v-if="!taskRows.length" class="empty-state"><strong>当前筛选没有任务</strong><span>切换上方状态查看其他记录。</span></div>
      </div>
      <p class="helper-note">此列表展示本地模拟状态；真实产品中的运行阶段和百分比应来自后端实际任务数据。</p>
    </UiPanel>
  </div>
</template>
