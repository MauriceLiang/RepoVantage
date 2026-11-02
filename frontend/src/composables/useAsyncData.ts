import { ref, shallowRef, watch, type WatchSource } from 'vue'

/**
 * 立即加载数据，并在可选的监听源发生变化时重新加载。
 * 只有最近一次请求可以更新页面状态，避免旧仓库或旧时间窗口的慢响应覆盖新选择。
 * 旧请求不会被取消；调用 reload 可等待新请求结束。
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
