<script setup lang="ts">
import { ArrowRight, ListChecks, Search, Trash2 } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import GdBadge from '@/components/ui/GdBadge.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import GdInput from '@/components/ui/GdInput.vue'
import GdSegmented from '@/components/ui/GdSegmented.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useDataSource } from '@/composables/useDataSource'
import type { RepositoryStatus, RepositorySummary } from '@/services/types'
import { useAnalysisStore } from '@/stores/analysis'
import { useUiStore } from '@/stores/ui'

const router = useRouter()
const source = useDataSource()
const ui = useUiStore()
const analysis = useAnalysisStore()
const courseTestDatasetId = 'course-research-300-v1'

const query = ref('')
const tab = ref<'library' | 'search'>('library')
const repositoryTabOptions = [
  { value: 'library', label: '我的仓库' },
  { value: 'search', label: '发现仓库' },
]
const status = ref<'all' | RepositoryStatus>('all')
const selected = ref<string[]>([])
const searchResults = ref<(RepositorySummary & { alreadyInLibrary: boolean })[]>([])
const searchError = ref<string | null>(null)
const searching = ref(false)
const busyId = ref<string | null>(null)
const clearingSelected = ref(false)
const { data: repositories, loading, error, reload } = useAsyncData(() => source.listRepositories())

watch(tab, () => { searchError.value = null })

function setTab(value: string | number) {
  if (value === 'library' || value === 'search') tab.value = value
}

const filtered = computed(() =>
  (repositories.value ?? []).filter((repo) => {
    const matchesQuery = !query.value || repo.fullName.toLowerCase().includes(query.value.toLowerCase()) || (repo.description ?? '').toLowerCase().includes(query.value.toLowerCase())
    const matchesStatus = status.value === 'all' || repo.status === status.value
    return matchesQuery && matchesStatus
  }),
)
const allFilteredSelected = computed(() => filtered.value.length > 0 && filtered.value.every((repo) => selected.value.includes(repo.id)))

const statusMeta: Record<RepositoryStatus, { text: string; variant: 'default' | 'warn' | 'plain' }> = {
  ready: { text: '已完成', variant: 'default' },
  partial: { text: '部分数据', variant: 'warn' },
  running: { text: '正在更新', variant: 'default' },
  failed: { text: '采集失败', variant: 'warn' },
  idle: { text: '尚未分析', variant: 'plain' },
}

function isCourseTestRepository(repo: RepositorySummary) {
  return repo.datasetIds?.includes(courseTestDatasetId) === true
}

function repositoryPath(repo: RepositorySummary) {
  return `/repositories/${repo.id}/overview`
}

function repositoryActionLabel(repo: RepositorySummary) {
  if (isCourseTestRepository(repo) && repo.hasHistoricalData) return '查看历史分析'
  return repo.status === 'idle' ? '开始分析' : '查看分析'
}

function toggle(repo: RepositorySummary) {
  if (selected.value.includes(repo.id)) selected.value = selected.value.filter((id) => id !== repo.id)
  else selected.value = [...selected.value, repo.id]
}

function toggleAllFiltered() {
  const visibleIds = filtered.value.map((repo) => repo.id)
  if (!visibleIds.length) return

  if (allFilteredSelected.value) {
    const visibleIdSet = new Set(visibleIds)
    selected.value = selected.value.filter((id) => !visibleIdSet.has(id))
    return
  }

  const selectedIds = new Set(selected.value)
  const newIds = visibleIds.filter((id) => !selectedIds.has(id))
  selected.value = [...selected.value, ...newIds]
}

function compare() {
  if (selected.value.length < 2 || selected.value.length > 5) return
  analysis.setCompare(selected.value)
  void router.push('/compare')
}

async function searchGithub() {
  if (query.value.trim().length < 2) {
    searchError.value = '请输入至少 2 个字符'
    return
  }
  searching.value = true
  searchError.value = null
  try {
    searchResults.value = await source.searchRepositories(query.value)
  } catch (cause) {
    searchError.value = cause instanceof Error ? cause.message : '搜索 GitHub 仓库失败'
  } finally {
    searching.value = false
  }
}

async function add(repo: RepositorySummary) {
  busyId.value = repo.id
  try {
    const result = await source.addRepository(repo.fullName)
    ui.toast(result.taskId ? '仓库已加入，采集任务已排队' : '仓库已加入分析库', result.taskId ? 'warning' : 'success')
    await reload()
    void router.push(`/repositories/${result.repositoryId}/overview`)
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '添加仓库失败', 'error')
  } finally {
    busyId.value = null
  }
}

async function remove(repo: RepositorySummary) {
  if (!window.confirm(`从分析库移除 ${repo.fullName}？历史任务与数据不会删除。`)) return
  busyId.value = repo.id
  try {
    await source.removeRepository(repo.id)
    selected.value = selected.value.filter((id) => id !== repo.id)
    await reload()
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
  const names = new Map((repositories.value ?? []).map((repo) => [repo.id, repo.fullName]))
  const shownNames = repositoryIds.slice(0, 5).map((id) => names.get(id) ?? `仓库 #${id}`)
  const remaining = repositoryIds.length - shownNames.length
  const list = `${shownNames.join('、')}${remaining > 0 ? ` 等 ${repositoryIds.length} 个仓库` : ''}`
  if (!window.confirm(`确定删除所选仓库的本地采集与分析记录，并从“我的仓库”移除吗？\n\n${list}\n\n仓库资料、原始数据包、其他数据集归属与任务历史会保留。此操作不可撤销。`)) return

  clearingSelected.value = true
  try {
    await source.clearRepositoryData(repositoryIds, { removeFromLibrary: true })
    selected.value = selected.value.filter((id) => !repositoryIds.includes(id))
    analysis.setCompare(analysis.compareIds.filter((id) => !repositoryIds.includes(id)))
    await reload()
    ui.toast(`已删除 ${repositoryIds.length} 个仓库的本地数据并从“我的仓库”移除`)
  } catch (cause) {
    await reload()
    if (repositories.value) {
      const remaining = new Set(repositories.value.map((repo) => repo.id))
      const removed = new Set(repositoryIds.filter((id) => !remaining.has(id)))
      selected.value = selected.value.filter((id) => remaining.has(id))
      analysis.setCompare(analysis.compareIds.filter((id) => !removed.has(id)))
    }
    ui.toast(cause instanceof Error ? cause.message : '删除所选仓库失败', 'error')
  } finally {
    clearingSelected.value = false
  }
}

</script>

<template>
  <div class="flex h-[calc(100dvh-3.5rem)] flex-col gap-3 px-4 pb-8 pt-5 sm:gap-[18px] sm:px-7 sm:pt-[22px]">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="m-0 text-[24px] font-semibold">仓库</h1>
        <p class="mt-1.5 text-muted">我的分析库与公开仓库发现</p>
      </div>
    </div>

    <GdSegmented :model-value="tab" :options="repositoryTabOptions" aria-label="仓库列表类型" @update:model-value="setTab" />

    <div class="flex flex-wrap items-center gap-2">
      <GdInput v-model="query" size="sm" :placeholder="tab === 'library' ? '搜索已加入的仓库' : '搜索 GitHub 仓库或关键词'" class="max-w-[320px] flex-1" @enter="tab === 'search' && searchGithub()">
        <template #icon><Search :size="15" class="text-muted" /></template>
      </GdInput>
      <select v-if="tab === 'library'" v-model="status" class="h-[38px] rounded-lg border border-line bg-panel px-2.5 text-[12.5px] text-muted outline-none">
        <option value="all">数据状态：全部</option>
        <option value="ready">已完成</option>
        <option value="partial">部分数据</option>
        <option value="running">正在更新</option>
        <option value="failed">采集失败</option>
        <option value="idle">尚未分析</option>
      </select>
      <GdButton v-if="tab === 'library'" variant="outline" size="sm" :disabled="!filtered.length || clearingSelected" title="全选当前搜索和状态筛选结果" @click="toggleAllFiltered">
        <ListChecks :size="13" />{{ allFilteredSelected ? '取消当前全选' : '全选当前列表' }}
      </GdButton>
      <GdButton v-else size="sm" :disabled="searching" @click="searchGithub">{{ searching ? '搜索中…' : '搜索 GitHub' }}</GdButton>
    </div>

    <GdCard padding="sm" class="min-h-[180px] flex-1 overflow-hidden">
      <div class="hidden grid-cols-[40px_minmax(0,1fr)_170px] gap-3 border-b border-line pb-2 text-[11.5px] text-muted lg:grid">
        <span />
        <div class="grid min-w-0 grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)_104px_96px_76px] gap-3">
          <span>仓库</span><span>语言 / Stars</span><span>数据状态</span><span>上次分析</span><span>活动变化</span>
        </div>
        <span />
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
        <p v-if="tab === 'library' && error" class="py-4 text-[12px] text-danger">加载仓库列表失败：{{ error }}</p>
        <p v-else-if="tab === 'search' && searchError" class="py-4 text-[12px] text-danger">{{ searchError }}</p>
        <div v-else-if="tab === 'library' && loading || tab === 'search' && searching" class="flex flex-col gap-2 py-2">
          <div v-for="i in 5" :key="i" class="h-14 animate-pulse rounded bg-track/60" />
        </div>
        <TransitionGroup v-else tag="div" name="gd-motion-list" class="divide-y divide-line">
          <div v-for="repo in (tab === 'library' ? filtered : searchResults)" :key="repo.id" class="gd-interactive-row -mx-2 grid grid-cols-[40px_minmax(0,1fr)] items-center gap-x-3 gap-y-2 rounded-lg px-2 py-3 lg:grid-cols-[40px_minmax(0,1fr)_170px]" :data-selected="tab === 'library' && selected.includes(repo.id)">
            <label v-if="tab === 'library'" class="grid size-10 place-items-center rounded-md hover:bg-soft/80" :class="clearingSelected || busyId === repo.id ? 'cursor-not-allowed' : 'cursor-pointer'">
              <input type="checkbox" :aria-label="`选择仓库 ${repo.fullName}`" data-testid="repository-select" :data-repository-id="repo.id" class="size-4 accent-ink" :disabled="clearingSelected || busyId === repo.id" :checked="selected.includes(repo.id)" @change="toggle(repo)" />
            </label>
            <span v-else />
            <component
              :is="tab === 'library' ? RouterLink : 'div'"
              :to="tab === 'library' ? repositoryPath(repo) : undefined"
              :aria-label="tab === 'library' ? `打开 ${repo.fullName} 的分析` : undefined"
              class="grid min-w-0 self-stretch grid-cols-1 items-center rounded-sm lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)_104px_96px_76px] lg:gap-3"
              :class="tab === 'library' ? 'cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink/30' : ''"
            >
              <div class="min-w-0">
                <div class="truncate text-[13px] font-semibold">{{ repo.fullName }}</div>
                <div class="truncate text-[11.5px] text-muted">{{ repo.description ?? '无公开简介' }}</div>
              </div>
              <div class="hidden text-[11.5px] text-muted lg:block">{{ repo.language ?? '语言未知' }} · ★ {{ repo.stars?.toLocaleString('en-US') ?? '—' }}</div>
              <div class="hidden lg:block"><GdBadge :variant="isCourseTestRepository(repo) && repo.hasHistoricalData && repo.status === 'idle' ? 'default' : statusMeta[repo.status].variant">{{ isCourseTestRepository(repo) && repo.hasHistoricalData && repo.status === 'idle' ? '已有历史数据' : statusMeta[repo.status].text }}</GdBadge></div>
              <div class="hidden font-mono text-[11.5px] text-muted lg:block">{{ repo.lastAnalyzedAt ?? '—' }}</div>
              <div class="hidden font-mono text-[11.5px] lg:block" :class="repo.activityDelta === null || repo.activityDelta === 0 ? 'text-muted' : repo.activityDelta < 0 ? 'text-s1' : 'text-s3'">
                {{ repo.activityDelta === null ? '—' : `${repo.activityDelta > 0 ? '+' : ''}${repo.activityDelta}%` }}
              </div>
            </component>
            <div class="col-span-2 flex items-center justify-end gap-2 lg:col-span-1">
              <RouterLink v-if="tab === 'library'"
                :to="repositoryPath(repo)"
                :aria-label="`${repositoryActionLabel(repo)} ${repo.fullName}`"
                class="inline-flex h-7 shrink-0 items-center whitespace-nowrap rounded-md border border-line bg-panel px-2.5 text-[12px] font-medium hover:bg-soft"
              >
                {{ repositoryActionLabel(repo) }}
              </RouterLink>
              <GdButton v-if="tab === 'library'" variant="ghost" size="sm" :aria-label="`从分析库移除 ${repo.fullName}`" :disabled="clearingSelected || busyId === repo.id" @click="remove(repo)">移除</GdButton>
              <GdButton v-else size="sm" :aria-label="repo.alreadyInLibrary ? `${repo.fullName} 已在分析库` : busyId === repo.id ? `正在添加 ${repo.fullName}` : `添加并分析 ${repo.fullName}`" :disabled="repo.alreadyInLibrary || busyId === repo.id" @click="add(repo)">{{ repo.alreadyInLibrary ? '已在分析库' : busyId === repo.id ? '正在添加…' : '添加并分析' }}</GdButton>
            </div>
          </div>
          <p v-if="tab === 'library' && !filtered.length" key="empty-library" class="py-6 text-center text-[12px] text-muted">没有匹配的仓库。</p>
          <p v-else-if="tab === 'search' && !searchResults.length && !searching" key="empty-search" class="py-6 text-center text-[12px] text-muted">输入关键词并搜索 GitHub。</p>
        </TransitionGroup>
      </div>
      <div class="flex items-center justify-between pt-2 text-[11.5px] text-muted">
        <span>{{ tab === 'library' ? `分析库 ${filtered.length} 个仓库` : `搜索结果 ${searchResults.length} 个（最多显示 20 个）` }}</span>
      </div>
    </GdCard>

    <div v-if="selected.length" class="flex flex-col gap-3 rounded-lg border border-line bg-soft px-3.5 py-2.5 text-[12.5px] md:flex-row md:flex-wrap md:items-center md:justify-between">
      <span class="min-w-0">已选择 {{ selected.length }} 个仓库<span class="text-muted"> · 比较需选择 2–5 个</span></span>
      <div class="flex w-full flex-wrap items-center gap-2 md:w-auto md:justify-end">
        <GdButton variant="ghost" size="sm" :disabled="clearingSelected" @click="selected = []">清除选择</GdButton>
        <GdButton variant="danger" size="sm" :loading="clearingSelected" :disabled="busyId !== null" @click="deleteSelectedRepositories"><Trash2 :size="12" />删除所选仓库及数据</GdButton>
        <GdButton data-testid="compare-selected" size="sm" :disabled="selected.length < 2 || selected.length > 5 || clearingSelected" @click="compare">进入比较 <ArrowRight :size="12" /></GdButton>
      </div>
    </div>
  </div>
</template>
