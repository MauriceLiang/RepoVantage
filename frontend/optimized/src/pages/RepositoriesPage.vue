<script setup lang="ts">
import { ArrowLeft, ArrowRight, Check, Plus, RefreshCw, Search, Trash2 } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useDataSource } from '@/composables/useDataSource'
import type { RepositoryStatus, RepositorySummary } from '@/services/types'
import { useAnalysisStore } from '@/stores/analysis'
import { useUiStore } from '@/stores/ui'

const source = useDataSource()
const router = useRouter()
const analysis = useAnalysisStore()
const ui = useUiStore()
const repositories = ref<RepositorySummary[]>([])
const searchResults = ref<(RepositorySummary & { alreadyInLibrary: boolean })[]>([])
const mode = ref<'library' | 'search'>('library')
const query = ref('')
const language = ref('全部语言')
const status = ref<'all' | RepositoryStatus>('all')
const selected = ref<string[]>([])
const page = ref(1)
const pageSize = 12
const loading = ref(true)
const searching = ref(false)
const busyId = ref<string | null>(null)
const clearingSelected = ref(false)
const error = ref('')
const searchError = ref('')

const languages = computed(() => ['全部语言', ...new Set(repositories.value.map((repository) => repository.language).filter((item): item is string => Boolean(item)))])
const languageOptions = computed(() => languages.value.map((label) => ({ value: label, label })))
const statusOptions = [
  { value: 'all', label: '全部状态' },
  { value: 'ready', label: '已完成' },
  { value: 'partial', label: '部分数据' },
  { value: 'running', label: '正在更新' },
  { value: 'idle', label: '尚未分析' },
  { value: 'failed', label: '采集失败' },
]
const filtered = computed(() => repositories.value.filter((repository) => {
  const normalized = query.value.trim().toLocaleLowerCase()
  const matchesQuery = !normalized || `${repository.fullName} ${repository.description ?? ''} ${repository.language ?? ''}`.toLocaleLowerCase().includes(normalized)
  const matchesStatus = status.value === 'all' || repository.status === status.value
  const matchesLanguage = language.value === '全部语言' || repository.language === language.value
  return matchesQuery && matchesStatus && matchesLanguage
}))
const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize)))
const pageRows = computed(() => filtered.value.slice((page.value - 1) * pageSize, page.value * pageSize))
const rows = computed(() => mode.value === 'library' ? pageRows.value : searchResults.value)
const allPageSelected = computed(() => pageRows.value.length > 0 && pageRows.value.every((repository) => selected.value.includes(repository.id)))
const canCompare = computed(() => selected.value.length >= 2 && selected.value.length <= 5)

watch([query, language, status], () => { page.value = 1 })
watch(pageCount, (count) => { if (page.value > count) page.value = count })
watch(mode, () => { searchError.value = '' })

function formatNumber(value: number | null | undefined) {
  return value === null || value === undefined ? '—' : value.toLocaleString('zh-CN')
}

function statusInfo(value: RepositoryStatus) {
  const metadata: Record<RepositoryStatus, { label: string; tone: 'success' | 'warning' | 'danger' | 'neutral' }> = {
    ready: { label: '已完成', tone: 'success' },
    partial: { label: '部分数据', tone: 'warning' },
    running: { label: '正在更新', tone: 'success' },
    idle: { label: '尚未分析', tone: 'neutral' },
    failed: { label: '采集失败', tone: 'danger' },
  }
  return metadata[value]
}

function dateLabel(value: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? value.slice(0, 10) : new Intl.DateTimeFormat('zh-CN', { timeZone: 'UTC', year: 'numeric', month: '2-digit', day: '2-digit' }).format(date)
}

async function loadRepositories() {
  loading.value = true
  error.value = ''
  try {
    repositories.value = await source.listRepositories()
    const availableIds = new Set(repositories.value.map((repository) => repository.id))
    selected.value = selected.value.filter((id) => availableIds.has(id))
    analysis.setCompare(analysis.compareIds.filter((id) => availableIds.has(id)))
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '仓库列表加载失败'
  } finally {
    loading.value = false
  }
}

function toggle(repositoryId: string) {
  selected.value = selected.value.includes(repositoryId)
    ? selected.value.filter((id) => id !== repositoryId)
    : [...selected.value, repositoryId]
}

function togglePageSelection() {
  const visibleIds = pageRows.value.map((repository) => repository.id)
  if (allPageSelected.value) {
    const visible = new Set(visibleIds)
    selected.value = selected.value.filter((id) => !visible.has(id))
  } else {
    selected.value = [...new Set([...selected.value, ...visibleIds])]
  }
}

function openRepository(repository: RepositorySummary) {
  void router.push(`/repositories/${repository.id}/overview`)
}

function compareSelected() {
  if (!canCompare.value) return
  analysis.setCompare(selected.value)
  void router.push('/compare')
}

async function searchGithub() {
  if (query.value.trim().length < 2) {
    searchError.value = '请输入至少 2 个字符'
    return
  }
  searching.value = true
  searchError.value = ''
  try {
    searchResults.value = await source.searchRepositories(query.value)
  } catch (cause) {
    searchError.value = cause instanceof Error ? cause.message : '搜索 GitHub 仓库失败'
  } finally {
    searching.value = false
  }
}

async function addRepository(repository: RepositorySummary) {
  busyId.value = repository.id
  try {
    const result = await source.addRepository(repository.fullName)
    ui.toast(result.taskId ? '仓库已加入，采集任务已排队' : '仓库已加入分析库', result.taskId ? 'warning' : 'success')
    await loadRepositories()
    void router.push(`/repositories/${result.repositoryId}/overview`)
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '添加仓库失败', 'error')
  } finally {
    busyId.value = null
  }
}

async function removeRepository(repository: RepositorySummary) {
  if (!window.confirm(`从分析库移除 ${repository.fullName}？历史任务与数据不会删除。`)) return
  busyId.value = repository.id
  try {
    await source.removeRepository(repository.id)
    selected.value = selected.value.filter((id) => id !== repository.id)
    analysis.setCompare(analysis.compareIds.filter((id) => id !== repository.id))
    await loadRepositories()
    ui.toast('已从分析库移除')
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '移除仓库失败', 'error')
  } finally {
    busyId.value = null
  }
}

async function deleteSelectedRepositories() {
  const repositoryIds = [...selected.value]
  if (!repositoryIds.length) return
  const names = new Map(repositories.value.map((repository) => [repository.id, repository.fullName]))
  const shownNames = repositoryIds.slice(0, 5).map((id) => names.get(id) ?? `仓库 #${id}`)
  const remaining = repositoryIds.length - shownNames.length
  const list = `${shownNames.join('、')}${remaining > 0 ? ` 等 ${repositoryIds.length} 个仓库` : ''}`
  if (!window.confirm(`确定删除所选仓库的本地采集与分析记录，并从“我的仓库”移除吗？\n\n${list}\n\n仓库资料、原始数据包、其他数据集归属与任务历史会保留。此操作不可撤销。`)) return

  clearingSelected.value = true
  try {
    await source.clearRepositoryData(repositoryIds, { removeFromLibrary: true })
    selected.value = selected.value.filter((id) => !repositoryIds.includes(id))
    analysis.setCompare(analysis.compareIds.filter((id) => !repositoryIds.includes(id)))
    await loadRepositories()
    ui.toast(`已删除 ${repositoryIds.length} 个仓库的本地数据并从“我的仓库”移除`)
  } catch (cause) {
    await loadRepositories()
    if (repositories.value) {
      const remainingIds = new Set(repositories.value.map((repository) => repository.id))
      const removed = new Set(repositoryIds.filter((id) => !remainingIds.has(id)))
      selected.value = selected.value.filter((id) => remainingIds.has(id))
      analysis.setCompare(analysis.compareIds.filter((id) => !removed.has(id)))
    }
    ui.toast(cause instanceof Error ? cause.message : '删除所选仓库失败', 'error')
  } finally {
    clearingSelected.value = false
  }
}

void loadRepositories()
</script>

<template>
  <div class="stack optimized-page">
    <UiPageHeader title="仓库" description="管理分析库、发现 GitHub 仓库并选择比较候选。列表覆盖所有分页。">
      <template #actions><UiButton variant="quiet" :disabled="loading || clearingSelected" @click="loadRepositories"><RefreshCw :size="13" />刷新列表</UiButton></template>
    </UiPageHeader>

    <UiPanel as="section" class="stack" style="gap:13px">
      <div class="toolbar repository-source-tabs" role="tablist" aria-label="仓库来源">
        <button type="button" class="segment" :aria-pressed="mode === 'library'" @click="mode = 'library'">我的仓库 <span class="muted">{{ repositories.length }}</span></button>
        <button type="button" class="segment" :aria-pressed="mode === 'search'" @click="mode = 'search'">发现 GitHub 仓库</button>
      </div>

      <div class="toolbar">
        <label class="search-field"><Search :size="14" /><UiInput v-model="query" type="search" :aria-label="mode === 'library' ? '搜索分析库' : '搜索 GitHub 仓库'" :placeholder="mode === 'library' ? '搜索仓库名、语言或说明' : '输入至少 2 个字符搜索 GitHub'" @keyup.enter="mode === 'search' && searchGithub()" /></label>
        <UiSelect v-if="mode === 'library'" v-model="language" label="按语言筛选" :options="languageOptions" style="width:170px" />
        <UiSelect v-if="mode === 'library'" v-model="status" label="按状态筛选" :options="statusOptions" style="width:170px" />
        <UiButton v-if="mode === 'search'" variant="primary" :loading="searching" :disabled="searching" @click="searchGithub"><Search :size="13" />{{ searching ? '搜索中…' : '搜索 GitHub' }}</UiButton>
        <UiBadge v-else>{{ formatNumber(filtered.length) }} 个结果</UiBadge>
      </div>

      <p v-if="searchError" class="small" role="alert" style="margin:0;color:var(--red)">{{ searchError }}</p>
      <div v-if="error" class="notice" role="alert">仓库列表加载失败：{{ error }} <UiButton variant="outline" @click="loadRepositories">重试</UiButton></div>

      <div class="table-wrap">
        <table class="data-table">
          <thead><tr>
            <th v-if="mode === 'library'"><input class="checkbox" type="checkbox" :checked="allPageSelected" :disabled="loading || !pageRows.length || clearingSelected" aria-label="选择当前页仓库" @change="togglePageSelection" /></th>
            <th>仓库 / 说明</th><th>语言</th><th>Stars</th><th>状态</th><th>最近分析</th><th>操作</th>
          </tr></thead>
          <tbody v-if="loading && !repositories.length"><tr><td :colspan="mode === 'library' ? 7 : 6"><div class="empty-state"><strong>正在加载仓库</strong><span>从数据服务读取仓库列表。</span></div></td></tr></tbody>
          <TransitionGroup v-else-if="rows.length" tag="tbody" name="list">
            <tr v-for="repository in rows" :key="repository.id">
              <td v-if="mode === 'library'"><input class="checkbox" type="checkbox" :checked="selected.includes(repository.id)" :disabled="clearingSelected || busyId === repository.id" :aria-label="`选择仓库 ${repository.fullName}`" data-testid="repository-select" :data-repository-id="repository.id" @change="toggle(repository.id)" /></td>
              <td class="repository-cell"><button class="repo-link" type="button" @click="openRepository(repository)">{{ repository.fullName }}</button><div class="repo-description" :title="repository.description ?? ''">{{ repository.description || '暂无仓库说明' }}</div></td>
              <td class="nowrap">{{ repository.language || '未知' }}</td>
              <td class="mono">{{ formatNumber(repository.stars) }}</td>
              <td><UiBadge :tone="statusInfo(repository.status).tone">{{ statusInfo(repository.status).label }}</UiBadge><span v-if="repository.hasHistoricalData" class="small muted" style="display:block;margin-top:4px">含本地历史数据</span></td>
              <td class="mono small">{{ dateLabel(repository.lastAnalyzedAt) }}</td>
              <td>
                <UiButton v-if="mode === 'library'" variant="quiet" type="button" :disabled="busyId === repository.id || clearingSelected" @click="removeRepository(repository)"><Trash2 :size="12" />移除</UiButton>
                <UiButton v-else variant="primary" type="button" :disabled="repository.alreadyInLibrary || busyId === repository.id" @click="addRepository(repository)"><Check v-if="repository.alreadyInLibrary" :size="12" /><Plus v-else :size="12" />{{ repository.alreadyInLibrary ? '已在分析库' : busyId === repository.id ? '正在添加…' : '添加并分析' }}</UiButton>
              </td>
            </tr>
          </TransitionGroup>
          <tbody v-else><tr><td :colspan="mode === 'library' ? 7 : 6"><div class="empty-state"><strong>{{ mode === 'search' && !searchResults.length ? '搜索 GitHub 仓库' : '没有匹配的仓库' }}</strong><span>{{ mode === 'search' && !searchResults.length ? '输入仓库名或关键词后开始搜索。' : '调整搜索文字或筛选条件后再试。' }}</span></div></td></tr></tbody>
        </table>
      </div>

      <footer v-if="mode === 'library'" class="pagination">
        <span>显示 {{ filtered.length ? (page - 1) * pageSize + 1 : 0 }}–{{ Math.min(page * pageSize, filtered.length) }} 条，共 {{ formatNumber(filtered.length) }} 个仓库</span>
        <div class="pagination-actions"><UiButton variant="quiet" :disabled="page <= 1" aria-label="上一页" @click="page--"><ArrowLeft :size="12" />上一页</UiButton><UiBadge>{{ page }} / {{ pageCount }}</UiBadge><UiButton variant="quiet" :disabled="page >= pageCount" aria-label="下一页" @click="page++">下一页<ArrowRight :size="12" /></UiButton></div>
      </footer>
    </UiPanel>

    <Transition name="page-transition">
      <aside v-if="mode === 'library' && selected.length" class="bottom-selection" aria-live="polite">
        <span><strong>{{ selected.length }}</strong> 个已选仓库<span class="muted"> · 比较最多选择 5 个</span></span>
        <div class="toolbar">
          <UiButton variant="quiet" :disabled="clearingSelected" @click="selected = []">清除选择</UiButton>
          <UiButton variant="danger" :loading="clearingSelected" :disabled="clearingSelected || busyId !== null" @click="deleteSelectedRepositories"><Trash2 :size="12" />删除所选数据与仓库</UiButton>
          <UiButton variant="primary" :disabled="!canCompare || clearingSelected" data-testid="compare-selected" @click="compareSelected">进入项目比较 <ArrowRight :size="12" /></UiButton>
        </div>
      </aside>
    </Transition>
  </div>
</template>
