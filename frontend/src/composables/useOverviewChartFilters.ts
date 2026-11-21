import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'
import type { RepositorySummary } from '@/services/types'
import { getStarsBucketKey, UNKNOWN_LANGUAGE } from '@/lib/overviewChartData'

export interface OverviewChartFilterState {
  languageKeys: string[]
  starsBucket: string | null
  selectedRepositoryId: string | null
}

export function useOverviewChartFilters(
  repositoriesSource: MaybeRefOrGetter<RepositorySummary[]>,
) {
  const selectedLanguageKeys = ref<string[]>([])
  const selectedStarsBucket = ref<string | null>(null)
  const selectedRepositoryId = ref<string | null>(null)
  const repositories = computed(() => toValue(repositoriesSource))

  function matchesRepository(repository: RepositorySummary): boolean {
    if (selectedLanguageKeys.value.length && !selectedLanguageKeys.value.includes(repository.language?.trim() || UNKNOWN_LANGUAGE)) return false
    if (selectedStarsBucket.value && getStarsBucketKey(repository.stars) !== selectedStarsBucket.value) return false
    return true
  }

  const filteredRepositories = computed(() => repositories.value.filter(matchesRepository))
  const filterState = computed<OverviewChartFilterState>(() => ({
    languageKeys: selectedLanguageKeys.value,
    starsBucket: selectedStarsBucket.value,
    selectedRepositoryId: selectedRepositoryId.value,
  }))
  const hasFilters = computed(() => selectedLanguageKeys.value.length > 0 || selectedStarsBucket.value !== null)

  function toggleLanguages(languageKeys: string[]) {
    const normalized = [...new Set(languageKeys)]
    if (!normalized.length) return
    const selected = new Set(selectedLanguageKeys.value)
    const alreadySelected = normalized.every((language) => selected.has(language))
    for (const language of normalized) {
      if (alreadySelected) selected.delete(language)
      else selected.add(language)
    }
    selectedLanguageKeys.value = [...selected].sort((left, right) => left.localeCompare(right))
  }

  function toggleStarsBucket(key: string) {
    selectedStarsBucket.value = selectedStarsBucket.value === key ? null : key
  }

  function clearFilters() {
    selectedLanguageKeys.value = []
    selectedStarsBucket.value = null
    selectedRepositoryId.value = null
  }

  return {
    selectedLanguageKeys,
    selectedStarsBucket,
    selectedRepositoryId,
    filteredRepositories,
    filterState,
    hasFilters,
    matchesRepository,
    toggleLanguages,
    toggleStarsBucket,
    clearFilters,
  }
}
