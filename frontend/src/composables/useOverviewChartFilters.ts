import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'
import type { RepositorySummary } from '@/services/types'
import { getPushBucketKey, getStarsBucketKey, UNKNOWN_LANGUAGE, type PushBucketKey } from '@/lib/overviewChartData'

export interface OverviewChartFilterState {
  languageKeys: string[]
  starsBucket: string | null
  pushBucket: PushBucketKey | null
  selectedRepositoryId: string | null
}

export function useOverviewChartFilters(
  repositoriesSource: MaybeRefOrGetter<RepositorySummary[]>,
  asOfSource: MaybeRefOrGetter<number>,
) {
  const selectedLanguageKeys = ref<string[]>([])
  const selectedStarsBucket = ref<string | null>(null)
  const selectedPushBucket = ref<PushBucketKey | null>(null)
  const selectedRepositoryId = ref<string | null>(null)
  const repositories = computed(() => toValue(repositoriesSource))
  const asOfMs = computed(() => toValue(asOfSource))

  function matchesRepository(repository: RepositorySummary): boolean {
    if (selectedLanguageKeys.value.length && !selectedLanguageKeys.value.includes(repository.language?.trim() || UNKNOWN_LANGUAGE)) return false
    if (selectedStarsBucket.value && getStarsBucketKey(repository.stars) !== selectedStarsBucket.value) return false
    if (selectedPushBucket.value && getPushBucketKey(repository.pushedAt, asOfMs.value) !== selectedPushBucket.value) return false
    return true
  }

  const filteredRepositories = computed(() => repositories.value.filter(matchesRepository))
  const filterState = computed<OverviewChartFilterState>(() => ({
    languageKeys: selectedLanguageKeys.value,
    starsBucket: selectedStarsBucket.value,
    pushBucket: selectedPushBucket.value,
    selectedRepositoryId: selectedRepositoryId.value,
  }))
  const hasFilters = computed(() => selectedLanguageKeys.value.length > 0 || selectedStarsBucket.value !== null || selectedPushBucket.value !== null)

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

  function togglePushBucket(key: PushBucketKey) {
    selectedPushBucket.value = selectedPushBucket.value === key ? null : key
  }

  function clearFilters() {
    selectedLanguageKeys.value = []
    selectedStarsBucket.value = null
    selectedPushBucket.value = null
    selectedRepositoryId.value = null
  }

  return {
    selectedLanguageKeys,
    selectedStarsBucket,
    selectedPushBucket,
    selectedRepositoryId,
    filteredRepositories,
    filterState,
    hasFilters,
    matchesRepository,
    toggleLanguages,
    toggleStarsBucket,
    togglePushBucket,
    clearFilters,
  }
}
