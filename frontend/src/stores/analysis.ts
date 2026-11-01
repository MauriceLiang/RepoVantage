import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { TimeWindow } from '@/services/types'

/** 跨页面共享的分析偏好，供仓库头部、分析标签和比较页共同使用。 */
export const useAnalysisStore = defineStore('analysis', () => {
  const preferenceKey = 'repovantage-analysis-window'
  const savedWindow = typeof localStorage === 'undefined' ? null : Number(localStorage.getItem(preferenceKey))
  const timeWindow = ref<TimeWindow>(savedWindow === 30 || savedWindow === 90 || savedWindow === 180 ? savedWindow : 90)
  const collectionScope = ref<'quick' | 'window'>('quick')
  const compareIds = ref<string[]>([])

  function setWindow(value: TimeWindow) {
    timeWindow.value = value
    if (typeof localStorage !== 'undefined') localStorage.setItem(preferenceKey, String(value))
  }
  function toggleCompare(id: string) {
    const exists = compareIds.value.includes(id)
    if (exists) compareIds.value = compareIds.value.filter((x) => x !== id)
    else if (compareIds.value.length < 5) compareIds.value = [...compareIds.value, id]
  }
  function setCompare(ids: string[]) {
    compareIds.value = ids.slice(0, 5)
  }
  return { timeWindow, collectionScope, compareIds, setWindow, toggleCompare, setCompare }
})
