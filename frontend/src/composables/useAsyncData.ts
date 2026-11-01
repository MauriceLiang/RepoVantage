import { ref, shallowRef, watch, type WatchSource } from 'vue'

/**
 * Load data immediately and whenever the optional watched source changes.
 * Only the latest request may update the visible state, so a slow response for
 * an earlier repository or time window cannot overwrite a newer selection.
 * Earlier requests are not aborted; reload returns the new request's promise.
 */
export function useAsyncData<T>(loader: () => Promise<T>, source?: WatchSource) {
  const data = shallowRef<T | null>(null)
  const loading = ref(true)
  const error = ref<string | null>(null)
  let requestId = 0

  async function run() {
    const id = ++requestId
    loading.value = true
    error.value = null
    try {
      const result = await loader()
      if (id === requestId) data.value = result as T
    } catch (e) {
      if (id === requestId) {
        error.value = e instanceof Error ? e.message : '未知错误'
        data.value = null
      }
    } finally {
      if (id === requestId) loading.value = false
    }
  }

  if (source) watch(source, () => void run(), { immediate: true })
  else void run()

  return { data, loading, error, reload: run }
}
