import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { TimeWindow } from '@/services/types'

/** 跨页面共享的分析偏好，供仓库头部、分析标签和比较页共同使用。 */
export const useAnalysisStore = defineStore('analysis', () => {
  const preferenceKey = 'repovantage-analysis-window'
  const compareKey = 'repovantage-comparison-repository-ids'
  const savedWindow = typeof localStorage === 'undefined' ? null : Number(localStorage.getItem(preferenceKey))
  const timeWindow = ref<TimeWindow>(savedWindow === 30 || savedWindow === 90 || savedWindow === 180 ? savedWindow : 90)
  function normalizeCompareIds(ids: unknown): string[] {
    if (!Array.isArray(ids)) return []
    return [...new Set(ids.filter((id): id is string => typeof id === 'string' && id.trim().length > 0))].slice(0, 5)
  }
  function readCompareIds(): string[] {
    if (typeof localStorage === 'undefined') return []
    try {
      return normalizeCompareIds(JSON.parse(localStorage.getItem(compareKey) ?? '[]'))
    } catch {
      return []
    }
  }
  const compareIds = ref<string[]>(readCompareIds())

  function setWindow(value: TimeWindow) {
    timeWindow.value = value
    if (typeof localStorage !== 'undefined') localStorage.setItem(preferenceKey, String(value))
  }
  function toggleCompare(id: string) {
    const exists = compareIds.value.includes(id)
    if (exists) setCompare(compareIds.value.filter((x) => x !== id))
    else if (compareIds.value.length < 5) setCompare([...compareIds.value, id])
  }
  function setCompare(ids: string[]) {
    compareIds.value = normalizeCompareIds(ids)
    if (typeof localStorage !== 'undefined') {
      try {
        localStorage.setItem(compareKey, JSON.stringify(compareIds.value))
      } catch {
        // Keep the current session usable when browser storage is unavailable.
      }
    }
  }
  return { timeWindow, compareIds, setWindow, toggleCompare, setCompare }
})
