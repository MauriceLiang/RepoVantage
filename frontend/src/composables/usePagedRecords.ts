import { computed, ref, shallowRef, watch } from 'vue'

/**
 * 管理 Issue 和 PR 列表共用的分页、搜索、加载及错误状态。
 * 每次请求递增版本号，只允许最后发出的请求更新界面，防止切换仓库或快速搜索时旧结果覆盖新结果。
 * 搜索会去除首尾空格并回到第一页；重复搜索当前条件时主动重新加载。
 */
export function usePagedRecords<T extends { total: number }>(
  repositoryId: () => string,
  load: (id: string, page: number, perPage: number, search: string) => Promise<T>,
  errorMessage: string,
  refreshKey?: () => unknown,
) {
  const pageSize = 10
  const page = ref(1)
  const searchInput = ref('')
  const appliedSearch = ref('')
  const records = shallowRef<T | null>(null)
  const loading = ref(false)
  const loadError = ref('')
  let requestVersion = 0

  const pageCount = computed(() => Math.max(1, Math.ceil((records.value?.total ?? 0) / pageSize)))
  const firstRecord = computed(() => records.value?.total ? (page.value - 1) * pageSize + 1 : 0)
  const lastRecord = computed(() => Math.min(page.value * pageSize, records.value?.total ?? 0))

  async function loadRecords() {
    const version = ++requestVersion
    loading.value = true
    loadError.value = ''
    records.value = null
    try {
      const result = await load(repositoryId(), page.value, pageSize, appliedSearch.value)
      if (version === requestVersion) records.value = result
    } catch (cause) {
      if (version === requestVersion) loadError.value = cause instanceof Error ? cause.message : errorMessage
    } finally {
      if (version === requestVersion) loading.value = false
    }
  }

  watch([repositoryId, page, appliedSearch, ...(refreshKey ? [refreshKey] : [])], () => { void loadRecords() }, { immediate: true })

  function applySearch() {
    const next = searchInput.value.trim()
    if (page.value === 1 && appliedSearch.value === next) {
      void loadRecords()
      return
    }
    page.value = 1
    appliedSearch.value = next
  }

  return { page, searchInput, appliedSearch, records, loading, loadError, pageCount, firstRecord, lastRecord, loadRecords, applySearch }
}
