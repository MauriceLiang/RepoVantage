<script setup lang="ts">
import { ArrowRight, Check, Compass, Folder, FolderMinus, FolderPlus, Library, Plus, RefreshCw, Search, Trash2 } from 'lucide-vue-next'
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDataSource } from '@/composables/useDataSource'
import type { RepositoryGroup, RepositoryStatus, RepositorySummary } from '@/services/types'
import { useAnalysisStore } from '@/stores/analysis'
import { useUiStore } from '@/stores/ui'
import RepositoryGroupDialog, { type GroupAction } from './RepositoryGroupDialog.vue'

const source = useDataSource()
const route = useRoute()
const router = useRouter()
const analysis = useAnalysisStore()
const ui = useUiStore()
const repositories = ref<RepositorySummary[]>([])
const searchResults = ref<(RepositorySummary & { alreadyInLibrary: boolean })[]>([])
const isLibraryView = computed(() => route.query.scope !== 'discover')
const discoveryRoute = { name: 'repositories', query: { scope: 'discover' } }
const groups = ref<RepositoryGroup[]>([])
const groupFilter = ref('all')
const groupAction = ref<GroupAction | null>(null)
const groupsLoading = ref(true)
const groupError = ref('')
const removingGroupMember = ref<string | null>(null)
const query = ref('')
const githubQuery = ref('')
const githubSearchForm = ref<HTMLFormElement | null>(null)
const repositoryResults = ref<HTMLElement | null>(null)
const repositoryTable = ref<HTMLDivElement | null>(null)
const searched = ref(false)
const language = ref('全部语言')
const status = ref<'all' | RepositoryStatus>('all')
const selected = ref<string[]>([])
const loading = ref(true)
const libraryLoaded = ref(false)
const searching = ref(false)
const busyId = ref<string | null>(null)
const clearingSelected = ref(false)
const error = ref('')
const searchError = ref('')

const activeGroup = computed(() => groups.value.find((group) => group.id === groupFilter.value))
const isEmptyLibrary = computed(() => isLibraryView.value && libraryLoaded.value && !error.value && !repositories.value.length)
const showOnboarding = computed(() => isEmptyLibrary.value && !activeGroup.value)
const showLibrary = computed(() => isLibraryView.value && !showOnboarding.value)
const showDiscoveryLanding = computed(() => !isLibraryView.value && !searched.value && !searching.value && !searchError.value)
const groupsByRepository = computed(() => {
  const memberships = new Map<string, RepositoryGroup[]>()
  for (const group of groups.value) {
    for (const id of group.repositoryIds) {
      const repositoryGroups = memberships.get(id) ?? []
      repositoryGroups.push(group)
      memberships.set(id, repositoryGroups)
    }
  }
  return memberships
})
const ungroupedRepositories = computed(() => repositories.value.filter((repository) => !groupsByRepository.value.has(repository.id)))
const groupRepositories = computed(() => {
  if (groupFilter.value === 'ungrouped') return ungroupedRepositories.value
  if (!activeGroup.value) return repositories.value
  const ids = new Set(activeGroup.value.repositoryIds)
  return repositories.value.filter((repository) => ids.has(repository.id))
})
const groupTitle = computed(() => activeGroup.value?.name ?? (groupFilter.value === 'ungrouped' ? '未分组' : '全部仓库'))
const groupOperationsDisabled = computed(() => loading.value || groupsLoading.value || Boolean(groupError.value || error.value) || clearingSelected.value || busyId.value !== null || removingGroupMember.value !== null)
const canPickRepositories = computed(() => groupRepositories.value.length < repositories.value.length)
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
const filtered = computed(() => groupRepositories.value.filter((repository) => {
  const normalized = query.value.trim().toLocaleLowerCase()
  const matchesQuery = !normalized || `${repository.fullName} ${repository.description ?? ''} ${repository.language ?? ''}`.toLocaleLowerCase().includes(normalized)
  const matchesStatus = status.value === 'all' || repository.status === status.value
  const matchesLanguage = language.value === '全部语言' || repository.language === language.value
  return matchesQuery && matchesStatus && matchesLanguage
}))
const rows = computed(() => showLibrary.value ? filtered.value : searchResults.value)
const allFilteredSelected = computed(() => filtered.value.length > 0 && filtered.value.every((repository) => selected.value.includes(repository.id)))
const canCompare = computed(() => selected.value.length >= 2 && selected.value.length <= 5)

watch([isLibraryView, groupFilter, query, language, status], () => {
  repositoryResults.value?.scrollTo({ top: 0 })
  repositoryTable.value?.scrollTo({ top: 0 })
})
function selectGroup(id: string) {
  if (id === groupFilter.value) return
  groupFilter.value = id
  selected.value = []
}

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
    libraryLoaded.value = true
    const availableIds = new Set(repositories.value.map((repository) => repository.id))
    selected.value = selected.value.filter((id) => availableIds.has(id))
    analysis.setCompare(analysis.compareIds.filter((id) => availableIds.has(id)))
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '仓库列表加载失败'
  } finally {
    loading.value = false
  }
}

async function loadGroups() {
  groupsLoading.value = true
  groupError.value = ''
  try {
    groups.value = await source.listRepositoryGroups()
    if (!activeGroup.value && groupFilter.value !== 'ungrouped') selectGroup('all')
  } catch (cause) {
    groupError.value = cause instanceof Error ? cause.message : '仓库分组加载失败'
  } finally {
    groupsLoading.value = false
  }
}

async function reloadLibrary() {
  await Promise.all([loadRepositories(), loadGroups()])
}

function updateGroup(group: RepositoryGroup) {
  const existing = groups.value.findIndex((item) => item.id === group.id)
  if (existing < 0) groups.value.push(group)
  else groups.value[existing] = group
}

function groupSaved(group: RepositoryGroup, added: number) {
  updateGroup(group)
  if (groupAction.value?.type === 'create') {
    selectGroup(group.id)
    query.value = ''
    language.value = '全部语言'
    status.value = 'all'
  } else if (groupAction.value?.type === 'assign') {
    const assigned = new Set(groupAction.value.repositoryIds)
    selected.value = selected.value.filter((id) => !assigned.has(id))
  }
  ui.toast(added ? `已将 ${added} 个仓库加入「${group.name}」` : '已创建分组')
}

async function removeFromGroup(repository: RepositorySummary) {
  const group = activeGroup.value
  if (!group || groupOperationsDisabled.value) return
  removingGroupMember.value = repository.id
  try {
    updateGroup(await source.removeRepositoryFromGroup(group.id, repository.id))
    if (groupFilter.value === group.id) selected.value = selected.value.filter((id) => id !== repository.id)
    ui.toast(`已从「${group.name}」移出`)
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '移出分组失败', 'error')
  } finally {
    removingGroupMember.value = null
  }
}

function toggle(repositoryId: string) {
  selected.value = selected.value.includes(repositoryId)
    ? selected.value.filter((id) => id !== repositoryId)
    : [...selected.value, repositoryId]
}

function toggleFilteredSelection() {
  const matchingIds = filtered.value.map((repository) => repository.id)
  if (allFilteredSelected.value) {
    const matching = new Set(matchingIds)
    selected.value = selected.value.filter((id) => !matching.has(id))
  } else {
    selected.value = [...new Set([...selected.value, ...matchingIds])]
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

async function openDiscovery() {
  await router.push(discoveryRoute)
  await nextTick()
  githubSearchForm.value?.querySelector('input')?.focus()
}

async function searchGithub() {
  if (searching.value) return
  if (githubQuery.value.trim().length < 2) {
    searchError.value = '请输入至少 2 个字符'
    return
  }
  searching.value = true
  searchError.value = ''
  searched.value = false
  searchResults.value = []
  try {
    searchResults.value = await source.searchRepositories(githubQuery.value)
    searched.value = true
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
    await reloadLibrary()
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
    await reloadLibrary()
    ui.toast(`已删除 ${repositoryIds.length} 个仓库的本地数据并从“我的仓库”移除`)
  } catch (cause) {
    await reloadLibrary()
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

void reloadLibrary()
</script>

<template>
  <div class="stack app-page repositories-page">
    <UiPageHeader title="仓库" />

    <UiPanel class="repository-workspace">
      <div class="repository-workspace-header">
        <nav class="repository-views" aria-label="仓库视图">
          <RouterLink to="/repositories" custom v-slot="{ href, navigate }">
            <a :href="href" :aria-current="isLibraryView ? 'page' : undefined" @click="navigate"><Library :size="15" aria-hidden="true" />我的仓库</a>
          </RouterLink>
          <RouterLink :to="discoveryRoute" custom v-slot="{ href, navigate }">
            <a :href="href" :aria-current="!isLibraryView ? 'page' : undefined" @click="navigate"><Compass :size="15" aria-hidden="true" />发现</a>
          </RouterLink>
        </nav>
        <UiButton v-if="isLibraryView" variant="quiet" class="repository-inline-action" aria-label="刷新列表" title="刷新列表" :disabled="loading || groupsLoading || clearingSelected || busyId !== null || removingGroupMember !== null" @click="reloadLibrary">
          <RefreshCw :size="14" aria-hidden="true" /><span class="repository-refresh-label">刷新列表</span>
        </UiButton>
      </div>

      <div class="repository-body" :class="{ 'repository-library': isLibraryView }">
        <aside v-if="isLibraryView" class="repository-groups" aria-labelledby="repository-groups-title">
          <div class="repository-groups-heading">
            <h2 id="repository-groups-title" class="panel-title">分组</h2>
            <UiButton variant="quiet" class="repository-inline-action" :disabled="groupOperationsDisabled" @click="groupAction = { type: 'create' }">
              <Plus :size="14" />新建分组
            </UiButton>
          </div>
          <nav class="repository-group-list" aria-label="仓库分组">
            <button type="button" class="repository-group" :aria-pressed="groupFilter === 'all'" @click="selectGroup('all')">
              <Library :size="15" aria-hidden="true" /><span>全部仓库</span><small>{{ repositories.length }}</small>
            </button>
            <button type="button" class="repository-group" :aria-pressed="groupFilter === 'ungrouped'" :disabled="groupsLoading || Boolean(groupError)" @click="selectGroup('ungrouped')">
              <FolderMinus :size="15" aria-hidden="true" /><span>未分组</span><small>{{ groupsLoading || groupError ? '—' : ungroupedRepositories.length }}</small>
            </button>
            <button
              v-for="group in groups"
              :key="group.id"
              type="button"
              class="repository-group"
              :aria-pressed="groupFilter === group.id"
              @click="selectGroup(group.id)"
            >
              <Folder :size="15" aria-hidden="true" /><span :title="group.name">{{ group.name }}</span><small>{{ group.repositoryIds.length }}</small>
            </button>
          </nav>
          <p v-if="groupError" class="small repository-error" role="alert">{{ groupError }}</p>
        </aside>

        <section
          ref="repositoryResults"
          class="stack repository-results"
          :class="{
            'repository-results-discovery': !isLibraryView,
            'repository-results-discovery--landing': showDiscoveryLanding,
          }"
          aria-labelledby="repository-results-title"
        >
          <template v-if="showLibrary">
            <div class="repository-results-heading">
              <h2 id="repository-results-title">{{ groupTitle }}</h2>
              <UiButton
                v-if="activeGroup && groupRepositories.length"
                variant="outline"
                :disabled="groupOperationsDisabled || !canPickRepositories"
                @click="groupAction = { type: 'pick', groupId: activeGroup.id }"
              >
                <Plus :size="14" aria-hidden="true" />从我的仓库添加
              </UiButton>
              <UiButton v-else-if="!activeGroup && repositories.length" variant="primary" data-testid="repository-add" @click="openDiscovery">
                <Plus :size="14" aria-hidden="true" />添加仓库
              </UiButton>
            </div>
            <div v-if="groupRepositories.length" class="toolbar repository-filters">
              <label class="search-field">
                <Search :size="14" />
                <UiInput v-model="query" type="search" aria-label="搜索我的仓库" placeholder="搜索仓库名、语言或说明" />
              </label>
              <UiSelect v-model="language" label="按语言筛选" :options="languageOptions" class="repository-filter" />
              <UiSelect v-model="status" label="按状态筛选" :options="statusOptions" class="repository-filter" />
            </div>
            <div v-if="error" class="notice" role="alert">仓库列表加载失败：{{ error }} <UiButton variant="outline" @click="reloadLibrary">重试</UiButton></div>
          </template>

          <div v-else class="repository-discovery" :class="{ 'repository-onboarding': showOnboarding || showDiscoveryLanding }">
            <div class="repository-discovery-heading">
              <span v-if="showOnboarding || showDiscoveryLanding" class="repository-onboarding-icon" aria-hidden="true">
                <FolderPlus v-if="showOnboarding" :size="25" />
                <Compass v-else :size="25" />
              </span>
              <h2 id="repository-results-title">
                {{ showOnboarding ? '添加第一个仓库' : showDiscoveryLanding ? '发现 GitHub 项目' : '搜索结果' }}
              </h2>
              <p v-if="showOnboarding">搜索 GitHub 公开仓库，添加后开始采集与分析。</p>
              <p v-else-if="showDiscoveryLanding">按仓库名称或关键词查找公开项目，添加后即可开始分析。</p>
              <p v-else-if="searched && searchResults.length">显示 {{ searchResults.length }} 个搜索结果</p>
            </div>
            <form ref="githubSearchForm" class="repository-discovery-search" @submit.prevent="searchGithub">
              <label class="search-field">
                <Search :size="15" aria-hidden="true" />
                <UiInput
                  v-model="githubQuery"
                  type="search"
                  aria-label="搜索 GitHub 仓库"
                  :aria-describedby="searchError ? 'repository-search-error' : undefined"
                  placeholder="输入仓库名或关键词，例如 vuejs/core"
                  maxlength="100"
                />
              </label>
              <UiButton variant="primary" type="submit" :loading="searching">
                <Search v-if="!searching" :size="15" aria-hidden="true" />
                搜索 GitHub
              </UiButton>
            </form>
            <p v-if="showDiscoveryLanding" class="repository-search-hint">输入至少 2 个字符开始搜索</p>
            <p v-if="searchError" id="repository-search-error" class="small repository-error" role="alert">{{ searchError }}</p>
          </div>

          <div v-if="rows.length" ref="repositoryTable" class="table-wrap" role="region" aria-label="仓库列表" tabindex="0">
            <table class="data-table" :class="{ 'repository-table-library': showLibrary }" role="table">
              <thead role="rowgroup"><tr role="row">
                <th v-if="showLibrary" role="columnheader">
                  <label class="repository-select-filtered" title="选择筛选结果中的所有仓库">
                    <input class="checkbox" type="checkbox" :checked="allFilteredSelected" :disabled="loading || clearingSelected" aria-label="选择筛选结果中的所有仓库" @change="toggleFilteredSelection" />
                    <span>选择筛选结果</span>
                  </label>
                </th>
                <th role="columnheader">仓库 / 说明</th><th role="columnheader">语言</th><th role="columnheader">Stars</th>
                <template v-if="showLibrary"><th role="columnheader">状态</th><th role="columnheader">最近分析</th></template>
                <th role="columnheader">操作</th>
              </tr></thead>
              <tbody role="rowgroup">
                <tr v-for="repository in rows" :key="repository.id" role="row">
                  <td v-if="showLibrary" class="repository-checkbox" role="cell">
                    <input class="checkbox" type="checkbox" :checked="selected.includes(repository.id)" :disabled="clearingSelected || busyId === repository.id" :aria-label="`选择仓库 ${repository.fullName}`" data-testid="repository-select" :data-repository-id="repository.id" @change="toggle(repository.id)" />
                  </td>
                  <td class="repository-cell" role="cell">
                    <button class="repo-link" type="button" @click="openRepository(repository)">{{ repository.fullName }}</button>
                    <div class="repo-description" :title="repository.description ?? ''">{{ repository.description || '暂无仓库说明' }}</div>
                    <div v-if="showLibrary && !activeGroup && groupsByRepository.has(repository.id)" class="repository-memberships">
                      <UiBadge v-for="group in groupsByRepository.get(repository.id)" :key="group.id" :title="group.name">{{ group.name }}</UiBadge>
                    </div>
                  </td>
                  <td class="repository-language nowrap" data-label="语言" role="cell">{{ repository.language || '未知' }}</td>
                  <td class="repository-stars mono" data-label="Stars" role="cell">{{ formatNumber(repository.stars) }}</td>
                  <td v-if="showLibrary" class="repository-status" role="cell"><UiBadge :tone="statusInfo(repository.status).tone">{{ statusInfo(repository.status).label }}</UiBadge><span v-if="repository.hasHistoricalData" class="repository-history small muted">含本地历史数据</span></td>
                  <td v-if="showLibrary" class="repository-date mono small nowrap" data-label="最近分析" role="cell">{{ dateLabel(repository.lastAnalyzedAt) }}</td>
                  <td class="repository-actions-cell" role="cell">
                    <div v-if="showLibrary" class="repository-row-actions">
                      <UiButton variant="quiet" :disabled="groupOperationsDisabled" @click="groupAction = { type: 'assign', repositoryIds: [repository.id] }">
                        <FolderPlus :size="13" />加入分组
                      </UiButton>
                      <UiButton v-if="activeGroup" variant="quiet" :disabled="groupOperationsDisabled" @click="removeFromGroup(repository)">
                        <FolderMinus :size="13" />移出分组
                      </UiButton>
                      <UiButton v-else variant="quiet" :disabled="busyId !== null || clearingSelected || removingGroupMember !== null" @click="removeRepository(repository)">
                        <Trash2 :size="13" />移除
                      </UiButton>
                    </div>
                    <UiButton v-else variant="primary" :loading="busyId === repository.id" :disabled="repository.alreadyInLibrary || busyId !== null" @click="addRepository(repository)">
                      <Check v-if="repository.alreadyInLibrary" :size="13" /><Plus v-else-if="busyId !== repository.id" :size="13" />
                      {{ repository.alreadyInLibrary ? '已在我的仓库' : '添加并分析' }}
                    </UiButton>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <template v-else-if="showLibrary">
            <p v-if="loading || (groupFilter === 'ungrouped' && groupsLoading)" class="repository-list-status muted" role="status">正在加载仓库…</p>
            <div v-else-if="!error && (groupFilter !== 'ungrouped' || !groupError)" class="repository-empty">
              <div class="repository-empty-icon" aria-hidden="true">
                <Folder v-if="!groupRepositories.length" :size="20" />
                <Search v-else :size="20" />
              </div>
              <div class="repository-empty-body">
                <template v-if="activeGroup && !groupRepositories.length">
                  <h3>这个分组还没有仓库</h3>
                  <UiButton v-if="!isEmptyLibrary" variant="primary" :disabled="groupOperationsDisabled" @click="groupAction = { type: 'pick', groupId: activeGroup.id }">
                    <Plus :size="14" aria-hidden="true" />从我的仓库添加
                  </UiButton>
                  <UiButton v-else variant="primary" @click="openDiscovery">
                    <Plus :size="14" aria-hidden="true" />添加仓库
                  </UiButton>
                </template>
                <h3 v-else-if="groupFilter === 'ungrouped' && !groupRepositories.length">所有仓库都已分组</h3>
                <template v-else>
                  <h3>没有匹配的仓库</h3>
                  <p>调整搜索词或筛选条件后再试。</p>
                </template>
              </div>
            </div>
          </template>
          <p v-else-if="searching" class="repository-list-status repository-search-status muted" role="status" aria-live="polite">
            <Search :size="16" aria-hidden="true" />正在 GitHub 上搜索仓库…
          </p>
          <div v-else-if="searched && !searchError" class="repository-empty repository-empty-discovery" role="status">
            <div class="repository-empty-icon" aria-hidden="true"><Compass :size="20" /></div>
            <div class="repository-empty-body">
              <h3>没有找到匹配的仓库</h3>
              <p>试试完整的仓库名称，或换一个关键词后重新搜索。</p>
            </div>
            <UiButton variant="outline" @click="githubSearchForm?.querySelector('input')?.focus()">修改搜索词</UiButton>
          </div>

          <footer v-if="showLibrary && filtered.length" class="small muted">
            共 {{ formatNumber(filtered.length) }} 个仓库
          </footer>
        </section>
      </div>

      <Transition name="page-transition">
        <aside v-if="showLibrary && selected.length" class="repository-selection" aria-live="polite">
          <span><strong>{{ selected.length }}</strong> 个已选仓库<span class="muted"> · 比较最多选择 5 个</span></span>
          <div class="toolbar">
            <UiButton variant="quiet" :disabled="clearingSelected" @click="selected = []">清除选择</UiButton>
            <UiButton variant="outline" :disabled="groupOperationsDisabled" @click="groupAction = { type: 'assign', repositoryIds: [...selected] }">
              <FolderPlus :size="13" />加入分组
            </UiButton>
            <UiButton variant="danger" :loading="clearingSelected" :disabled="clearingSelected || busyId !== null || removingGroupMember !== null" @click="deleteSelectedRepositories"><Trash2 :size="12" />删除所选数据与仓库</UiButton>
            <UiButton variant="primary" :disabled="!canCompare || clearingSelected" data-testid="compare-selected" @click="compareSelected">进入项目比较 <ArrowRight :size="12" /></UiButton>
          </div>
        </aside>
      </Transition>
    </UiPanel>

    <RepositoryGroupDialog :action="groupAction" :repositories="repositories" :groups="groups" @close="groupAction = null" @saved="groupSaved" />
  </div>
</template>

<style scoped>
.repositories-page {
  width: 100%;
  max-width: none;
  block-size: max(420px, calc(100dvh - var(--topbar-height)));
  grid-template-rows: auto minmax(0, 1fr);
  gap: 18px;
  margin-inline: 0;
  padding-block-end: 24px;
}
.repositories-page :deep(.page-header) { margin-bottom: 0; }
.repository-workspace {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  min-block-size: 0;
  container: repository-workspace / inline-size;
  padding: 0;
}
.repository-workspace-header {
  display: flex;
  min-height: 56px;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--line);
}
.repository-views {
  display: flex;
  gap: 4px;
}
.repository-views a {
  display: inline-flex;
  min-height: 38px;
  align-items: center;
  gap: 7px;
  padding: 0 12px;
  border-radius: 7px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  white-space: nowrap;
}
.repository-views a:hover { color: var(--ink); background: var(--surface-soft); }
.repository-views a[aria-current='page'] {
  color: var(--primary-ink);
  background: var(--primary-soft);
}
.repository-body {
  display: grid;
  min-block-size: 0;
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
}
.repository-library { grid-template-columns: 208px minmax(0, 1fr); }
.repository-groups {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-block-size: 0;
  padding: 14px 12px;
  border-inline-end: 1px solid var(--line);
  border-end-start-radius: calc(var(--radius) - 1px);
  background: var(--surface-soft);
}
.repository-groups-heading, .repository-results-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.repository-groups-heading { flex: none; min-height: 36px; margin: 0 0 6px 8px; }
.repository-inline-action { min-height: 34px; padding-inline: 8px; border-color: transparent; }
.repository-group-list {
  display: grid;
  min-block-size: 0;
  align-content: start;
  gap: 3px;
  overflow-y: auto;
  overscroll-behavior-y: contain;
  padding: 3px;
}
.repository-group {
  display: grid;
  min-height: 36px;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  padding: 0 8px;
  border: 0;
  border-radius: 7px;
  color: var(--ink);
  background: transparent;
  font-size: 13px;
  text-align: start;
  cursor: pointer;
}
.repository-group svg, .repository-group small { color: var(--muted); }
.repository-group span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.repository-group small { font-variant-numeric: tabular-nums; }
.repository-group:hover { background: var(--surface); }
.repository-group[aria-pressed='true'] { color: var(--primary-ink); background: var(--primary-soft); font-weight: 600; }
.repository-group[aria-pressed='true'] svg, .repository-group[aria-pressed='true'] small { color: inherit; }
.repository-group:disabled { opacity: .65; cursor: default; }
.repository-results {
  min-width: 0;
  min-block-size: 0;
  align-content: start;
  gap: 14px;
  overflow: auto;
  overscroll-behavior-y: contain;
  padding: 14px 20px 20px;
  scroll-padding-block: 14px 20px;
}
.repository-results-discovery--landing { align-content: stretch; }
.repository-results .table-wrap { min-block-size: 96px; }
.repository-results .table-wrap:focus-visible { outline-offset: -3px; }
.repository-results-heading { min-height: 36px; flex-wrap: wrap; }
.repository-results h2 { margin: 0; font-size: 17px; font-weight: 650; overflow-wrap: anywhere; }
.repository-filter { width: 136px; max-width: 100%; }
.repository-history { display: block; margin-top: 4px; }
.repository-select-filtered span { display: none; }
.repository-error { margin: 0; color: var(--red); overflow-wrap: anywhere; }
.repository-groups .repository-error { margin: 8px; }
.repository-memberships { display: flex; flex-wrap: wrap; gap: 4px; max-width: 360px; margin-top: 7px; }
.repository-memberships :deep(.badge) { display: block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; }
.repository-row-actions { display: flex; gap: 3px; }
.repository-row-actions :deep(.button) { min-height: 32px; padding-inline: 7px; border-color: transparent; }
.repository-row-actions :deep(.button:hover:not(:disabled)) { border-color: var(--line); }
.repository-discovery { display: grid; gap: 14px; }
.repository-discovery-heading { min-height: 36px; align-content: center; }
.repository-discovery-search {
  display: grid;
  width: min(100%, 700px);
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}
.repository-discovery-search .search-field { min-width: 0; }
.repository-onboarding {
  width: min(100%, 760px);
  align-content: start;
  justify-items: center;
  gap: 16px;
  margin: auto;
  padding: 28px 12px;
}
.repository-results-discovery--landing .repository-onboarding { gap: 19px; }
.repository-onboarding .repository-discovery-heading {
  display: grid;
  justify-items: center;
  gap: 6px;
  text-align: center;
}
.repository-onboarding-icon {
  display: grid;
  width: 58px;
  height: 58px;
  place-items: center;
  margin-bottom: 8px;
  border-radius: 12px;
  color: var(--primary-ink);
  background: var(--primary-soft);
}
.repository-onboarding h2 { font-size: 25px; line-height: 1.35; }
.repository-onboarding p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.55; }
.repository-onboarding .repository-error { width: min(100%, 516px); color: var(--red); }
.repository-onboarding .repository-discovery-search { width: min(100%, 640px); }
.repository-onboarding .repository-discovery-search :deep(.field),
.repository-onboarding .repository-discovery-search :deep(.button) { min-height: 48px; font-size: 13px; }
.repository-onboarding .repository-discovery-search :deep(.button) { padding-inline: 17px; }
.repository-search-hint { color: var(--muted); font-size: 11.5px !important; }
.repository-search-status {
  display: flex;
  min-height: 160px;
  align-items: center;
  justify-content: center;
  gap: 9px;
  color: var(--muted);
}
.repository-empty-discovery {
  min-height: 200px;
  flex: 1;
  align-content: center;
  justify-items: center;
  grid-template-columns: minmax(0, 1fr);
  text-align: center;
}
.repository-empty-discovery .repository-empty-body { justify-items: center; }
.repository-list-status { margin: 0; padding: 12px 0; font-size: 13px; }
.repository-empty {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: start;
  gap: 14px;
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: var(--surface-soft);
}
.repository-empty-icon {
  display: grid;
  width: 40px;
  height: 40px;
  place-items: center;
  border-radius: 9px;
  color: var(--primary-ink);
  background: var(--primary-soft);
}
.repository-empty-body { display: grid; justify-items: start; gap: 5px; }
.repository-empty-body h3 { margin: 0; font-size: 15px; font-weight: 650; }
.repository-empty-body p { margin: 0; color: var(--muted); font-size: 13px; }
.repository-empty-body .button { margin-top: 5px; }
.repository-selection {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 11px 13px;
  border-top: 1px solid var(--line);
}
@container repository-workspace (max-width: 920px) {
  .repository-library {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
  }
  .repository-groups {
    padding: 8px 12px 10px;
    border-inline-end: 0;
    border-bottom: 1px solid var(--line);
    border-end-start-radius: 0;
  }
  .repository-groups-heading { margin-bottom: 2px; }
  .repository-group-list {
    display: flex;
    flex-wrap: wrap;
    max-block-size: min(140px, 22dvh);
    padding: 2px;
  }
  .repository-group { flex: 0 0 auto; max-width: min(200px, 100%); }
}
@container repository-workspace (max-width: 700px) {
  .repository-workspace-header { padding-inline: 10px; }
  .repository-results { padding: 12px 12px 16px; }
  .repository-empty { gap: 10px; padding: 14px; }
  .repository-empty-icon { width: 34px; height: 34px; }
  .repository-results .data-table, .repository-results tbody, .repository-table-library thead, .repository-table-library thead tr { display: block; }
  .repository-results .data-table { position: relative; }
  .repository-results .data-table:not(.repository-table-library) thead, .repository-table-library th:not(:first-child) {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    overflow: hidden;
    clip-path: inset(50%);
  }
  .repository-table-library thead { position: static; }
  .repository-table-library tbody { border-top: 1px solid var(--line); }
  .repository-select-filtered { display: flex; align-items: center; gap: 8px; cursor: pointer; }
  .repository-select-filtered span { display: inline; }
  .repository-results tbody tr {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    align-items: center;
    gap: 8px;
    padding: 12px 10px;
  }
  .repository-results .repository-table-library tbody tr {
    grid-template-columns: 18px repeat(3, minmax(0, 1fr));
  }
  .repository-results tbody tr + tr { border-top: 1px solid var(--line); }
  .repository-results tbody td { padding: 0; border: 0; }
  .repository-checkbox { grid-column: 1; grid-row: 1; align-self: start; padding-top: 2px; }
  .repository-results .repository-cell { grid-column: -4 / -1; grid-row: 1; min-width: 0; }
  .repository-results .repo-link { overflow-wrap: anywhere; }
  .repository-results .repo-description { white-space: normal; }
  .repository-language { grid-column: -4; grid-row: 2; white-space: normal; overflow-wrap: anywhere; }
  .repository-stars { grid-column: -3; grid-row: 2; }
  .repository-date { grid-column: -2; grid-row: 2; }
  .repository-results td[data-label]::before {
    display: block;
    color: var(--muted);
    font-family: inherit;
    font-size: 10px;
    content: attr(data-label);
  }
  .repository-status { grid-column: -4; grid-row: 3; }
  .repository-actions-cell { grid-column: -3 / -1; grid-row: 3; justify-self: end; }
  .repository-row-actions { flex-wrap: wrap; justify-content: flex-end; }
}
@media (max-width: 640px) {
  .repositories-page { padding-block-end: 16px; }
}
@container repository-workspace (max-width: 320px) {
  .repository-refresh-label { display: none; }
}
@container repository-workspace (max-width: 420px) {
  .repository-onboarding { min-height: 0; padding: 28px 10px; }
  .repository-discovery-search { grid-template-columns: minmax(0, 1fr); }
  .repository-onboarding .repository-discovery-search { width: min(100%, 480px); }
  .repository-filters { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .repository-filters .search-field { grid-column: 1 / -1; }
  .repository-filters .repository-filter { width: 100%; }
}
</style>
