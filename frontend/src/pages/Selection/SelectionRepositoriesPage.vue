<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowRight, ArrowUpRight, Database, Info } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiPageHeader from '@/components/ui/UiPageHeader.vue'
import UiPanel from '@/components/ui/UiPanel.vue'
import { getBrowserApiData } from '@/services/httpRepositoryDataSource'
import { useAnalysisStore } from '@/stores/analysis'

const props = withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false })
const router = useRouter()
const analysis = useAnalysisStore()

interface CandidateActivity {
  window_start: string
  window_end_exclusive: string
  coverage: string
  collected_at: string
  commits: number | null
  issues_opened: number | null
  issues_closed: number | null
  pulls_opened: number | null
  pulls_merged: number | null
  releases: number | null
}

interface CandidateRepository {
  repository_id: number
  full_name: string
  html_url: string
  description: string | null
  language: string | null
  license_spdx: string | null
  stars: number | null
  forks: number | null
  category: string | null
  inclusion_reason: string | null
  activity: CandidateActivity | null
}

interface CandidateDatasetResponse {
  dataset_id: string
  name: string
  description: string | null
  frozen_at: string | null
  sample_size: number
  items: CandidateRepository[]
}

const result = ref<CandidateDatasetResponse | null>(null)
const loading = ref(true)
const error = ref('')
const selected = ref<string[]>([])
const canCompare = computed(() => selected.value.length >= 2 && selected.value.length <= 5)

const categories = computed(() => {
  const grouped = new Map<string, CandidateRepository[]>()
  for (const repository of result.value?.items ?? []) {
    const category = repository.category || '未分类'
    grouped.set(category, [...(grouped.get(category) ?? []), repository])
  }
  return [...grouped.entries()].map(([name, repositories]) => ({ name, repositories }))
})

const latestCollection = computed(() => {
  const dates = (result.value?.items ?? []).flatMap((item) => item.activity?.collected_at ? [item.activity.collected_at] : [])
  return dates.sort().at(-1) ?? result.value?.frozen_at ?? null
})

async function loadCandidates() {
  loading.value = true
  error.value = ''
  try {
    result.value = await getBrowserApiData<CandidateDatasetResponse>('/datasets/second-dev-candidates-2026-v1/repositories')
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '同类项目数据加载失败'
  } finally {
    loading.value = false
  }
}

function count(value: number | null | undefined) {
  return value === null || value === undefined ? '—' : value.toLocaleString('zh-CN')
}

function toggle(repositoryId: number) {
  const id = String(repositoryId)
  if (selected.value.includes(id)) {
    selected.value = selected.value.filter((value) => value !== id)
  } else if (selected.value.length < 5) {
    selected.value = [...selected.value, id]
  }
}

function compareSelected() {
  if (!canCompare.value) return
  analysis.setCompare(selected.value)
  void router.push('/compare')
}

function date(value: string | null | undefined) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'UTC', month: '2-digit', day: '2-digit' }).format(new Date(value))
}

onMounted(() => { void loadCandidates() })
</script>

<template>
  <div class="candidate-page" :class="{ 'candidate-page--embedded': props.embedded }">
    <UiPageHeader v-if="!props.embedded" title="同类软件候选" description="选择 2–5 个项目后进行对比；候选样本按使用场景分组。">
      <template #actions>
        <RouterLink class="button button--outline" to="/repositories">返回仓库</RouterLink>
      </template>
    </UiPageHeader>

    <div v-if="loading" class="panel candidate-state" role="status">正在读取同类项目样本…</div>
    <div v-else-if="error" class="panel candidate-state candidate-state--error" role="alert">
      <strong>同类项目数据暂不可用</strong><span>{{ error }}</span>
      <UiButton @click="loadCandidates">重新加载</UiButton>
    </div>
    <template v-else-if="result">
      <div class="candidate-overview" aria-label="候选样本概况">
        <div><Database :size="15" /><strong>{{ result.sample_size }}</strong><span>个候选仓库</span></div>
        <div><strong>{{ categories.length }}</strong><span>类使用场景</span></div>
        <div><strong>{{ latestCollection ? date(latestCollection) : '—' }}</strong><span>最近采集</span></div>
      </div>

      <div class="candidate-groups">
        <UiPanel v-for="group in categories" :key="group.name" as="section" class="candidate-group">
          <header class="candidate-group__header">
            <div><h2>{{ group.name }}</h2><p>{{ group.repositories.length }} 个项目</p></div>
            <UiBadge tone="accent">二次开发候选</UiBadge>
          </header>
          <div class="candidate-list">
            <article v-for="repository in group.repositories" :key="repository.repository_id" class="candidate-row">
              <label class="candidate-select" :title="selected.includes(String(repository.repository_id)) ? '取消选择' : selected.length >= 5 ? '最多选择 5 个仓库' : '选择用于对比'">
                <input type="checkbox" :checked="selected.includes(String(repository.repository_id))" :disabled="!selected.includes(String(repository.repository_id)) && selected.length >= 5" :aria-label="`选择 ${repository.full_name} 进行对比`" @change="toggle(repository.repository_id)" />
              </label>
              <div class="candidate-main">
                <a class="candidate-name" :href="repository.html_url" target="_blank" rel="noreferrer">
                  {{ repository.full_name }} <ArrowUpRight :size="13" />
                </a>
                <p>{{ repository.description || repository.inclusion_reason || '暂无仓库说明' }}</p>
                <div class="candidate-tags">
                  <span>{{ repository.language || '语言未知' }}</span>
                  <span v-if="repository.license_spdx">{{ repository.license_spdx }}</span>
                  <span>{{ count(repository.stars) }} Stars</span>
                </div>
              </div>
              <div v-if="repository.activity" class="candidate-activity">
                <div class="candidate-activity__heading">
                  <strong>180 天活动</strong>
                  <UiBadge :tone="repository.activity.coverage === 'complete' ? 'success' : 'warning'">
                    {{ repository.activity.coverage === 'complete' ? '覆盖完整' : '部分覆盖' }}
                  </UiBadge>
                </div>
                <div class="candidate-metrics">
                  <span><strong>{{ count(repository.activity.commits) }}</strong><small>Commit</small></span>
                  <span><strong>{{ count(repository.activity.issues_opened) }}</strong><small>新建 Issue</small></span>
                  <span><strong>{{ count(repository.activity.pulls_opened) }}</strong><small>新建 PR</small></span>
                  <span><strong>{{ count(repository.activity.releases) }}</strong><small>Release</small></span>
                </div>
                <small class="candidate-window">{{ date(repository.activity.window_start) }} – {{ date(repository.activity.window_end_exclusive) }} UTC</small>
              </div>
              <div v-else class="candidate-activity candidate-activity--empty">
                <UiBadge tone="neutral">活动数据不可用</UiBadge>
                <span>仅展示仓库档案</span>
              </div>
            </article>
          </div>
        </UiPanel>
      </div>

      <div v-if="selected.length" class="candidate-compare-bar" aria-live="polite">
        <span><strong>{{ selected.length }}</strong> 个候选仓库已选择<span class="muted"> · 需选择 2–5 个</span></span>
        <div class="candidate-compare-actions">
          <UiButton variant="quiet" @click="selected = []">清除选择</UiButton>
          <UiButton variant="primary" :disabled="!canCompare" @click="compareSelected">进入项目比较 <ArrowRight :size="13" /></UiButton>
        </div>
      </div>

      <p class="candidate-note"><Info :size="13" />这组项目用于场景内候选发现。活动计数说明采集窗口中的可见记录，不表示软件质量、功能适配或安全结论；具体选型仍以场景约束和逐项证据为准。</p>
    </template>
  </div>
</template>

<style scoped>
.candidate-page { display: grid; gap: 14px; }
.candidate-page--embedded { gap: 12px; }
.candidate-overview { display: flex; flex-wrap: wrap; gap: 8px 24px; align-items: center; color: var(--muted); font-size: 11px; }
.candidate-overview > div { display: flex; align-items: center; gap: 7px; }
.candidate-overview strong { color: var(--ink); font-size: 14px; }
.candidate-groups { display: grid; gap: 12px; }
.candidate-group { padding: 0; overflow: hidden; }
.candidate-group__header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 15px 17px; border-bottom: 1px solid var(--line); }
.candidate-group__header h2 { margin: 0; font-size: 15px; }
.candidate-group__header p { margin: 3px 0 0; color: var(--muted); font-size: 10px; }
.candidate-list { display: grid; }
.candidate-row { display: grid; grid-template-columns: 24px minmax(240px, 1.15fr) minmax(310px, 1fr); gap: 14px; align-items: center; padding: 14px 17px; border-bottom: 1px solid var(--line); }
.candidate-row:last-child { border-bottom: 0; }
.candidate-select { display: grid; place-items: center; }
.candidate-select input { width: 15px; height: 15px; accent-color: var(--primary); cursor: pointer; }
.candidate-select input:disabled { cursor: not-allowed; }
.candidate-main { min-width: 0; }
.candidate-name { display: inline-flex; gap: 5px; align-items: center; color: var(--ink); font-size: 12px; font-weight: 650; text-decoration: none; }
.candidate-name:hover { color: var(--primary); }
.candidate-main p { display: -webkit-box; overflow: hidden; margin: 5px 0 7px; color: var(--muted); font-size: 10.5px; line-height: 1.55; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.candidate-tags { display: flex; flex-wrap: wrap; gap: 5px 12px; color: var(--muted); font-size: 10px; }
.candidate-activity { min-width: 0; }
.candidate-activity__heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; font-size: 10px; }
.candidate-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.candidate-metrics span { display: grid; gap: 2px; }
.candidate-metrics strong { overflow: hidden; color: var(--ink); font-size: 12px; font-variant-numeric: tabular-nums; text-overflow: ellipsis; }
.candidate-metrics small,.candidate-window { color: var(--muted); font-size: 9px; }
.candidate-window { display: block; margin-top: 6px; }
.candidate-activity--empty { display: grid; justify-items: start; gap: 5px; color: var(--muted); font-size: 10px; }
.candidate-note { display: flex; align-items: flex-start; gap: 7px; margin: 0; color: var(--muted); font-size: 10px; line-height: 1.55; }
.candidate-note :deep(svg) { flex: 0 0 auto; margin-top: 1px; }
.candidate-compare-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: var(--surface-soft); color: var(--ink); font-size: 11px; }
.candidate-compare-bar > span > strong { font-size: 14px; }
.candidate-compare-actions { display: flex; align-items: center; gap: 8px; }
.candidate-state { display: grid; justify-items: start; gap: 8px; color: var(--muted); font-size: 12px; }
.candidate-state strong { color: var(--ink); }
.candidate-state--error { border-color: color-mix(in srgb, var(--red) 35%, var(--line)); }
@media (max-width: 760px) {
  .candidate-row { grid-template-columns: 24px minmax(0, 1fr); gap: 8px 12px; }
  .candidate-activity { grid-column: 2; }
  .candidate-overview { gap: 8px 16px; }
  .candidate-compare-bar { align-items: flex-start; flex-direction: column; }
}
</style>
