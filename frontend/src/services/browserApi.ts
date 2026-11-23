interface Envelope<T> { data: T; meta?: Record<string, unknown> }
interface ApiError { error?: { code?: string; message?: string }; request_id?: string }

let csrfToken: string | null = null
let sessionRequest: Promise<void> | null = null

function isJsonResponse(response: Response): boolean {
  const mediaType = response.headers.get('content-type')?.split(';', 1)[0].trim().toLowerCase()
  return mediaType === 'application/json' || Boolean(mediaType?.endsWith('+json'))
}

async function openSession() {
  // 并发请求共享尚未完成的会话握手；成功或失败后都清除 Promise，
  // 使后续请求可以重新建立会话。
  if (!sessionRequest) {
    sessionRequest = fetch('/api/browser/session', {
      credentials: 'same-origin',
      headers: { 'X-GDA-Request': 'browser' },
    }).then(async (response) => {
      if (!response.ok) throw new Error('无法建立本机浏览器会话，请确认后端已启动并刷新页面')
      const body = await response.json() as { csrf_token?: string }
      if (!body.csrf_token) throw new Error('后端未返回浏览器请求校验令牌')
      csrfToken = body.csrf_token
    }).finally(() => { sessionRequest = null })
  }
  await sessionRequest
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  await openSession()
  const headers = new Headers(init.headers)
  headers.set('X-GDA-Request', 'browser')
  if (csrfToken && init.method && init.method.toUpperCase() !== 'GET') headers.set('X-CSRF-Token', csrfToken)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')

  const response = await fetch(`/api/browser/v1${path}`, { ...init, headers, credentials: 'same-origin' })
  // 旧版单页应用的兜底路由可能对 API 地址返回状态为 200 的 HTML。
  // 必须先拒绝非 JSON 响应，不能将网页误解析为 API 数据。
  if (response.status !== 204 && !isJsonResponse(response)) {
    throw new Error('后端返回了网页而不是 API 数据，可能仍在运行旧版本；请重启后端后重试')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as ApiError
    const message = body.error?.message ?? `请求失败（${response.status}）`
    throw new Error(body.request_id ? `${message}（请求编号 ${body.request_id}）` : message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function data<T>(path: string, init?: RequestInit): Promise<T> {
  return (await request<Envelope<T>>(path, init)).data
}

export async function downloadResponse(path: string, failureLabel: string): Promise<Blob> {
  await openSession()
  const response = await fetch(`/api/browser/v1${path}`, {
    credentials: 'same-origin',
    headers: { 'X-GDA-Request': 'browser' },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as ApiError
    throw new Error(body.error?.message ?? `${failureLabel}（${response.status}）`)
  }
  return response.blob()
}

export function csv(path: string): Promise<Blob> {
  return downloadResponse(path, '导出失败')
}

/** 通过同源浏览器会话读取新增的、由后端提供的研究端点。 */
export function getBrowserApiData<T>(path: string): Promise<T> {
  return data<T>(path)
}

