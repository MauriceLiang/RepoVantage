import assert from 'node:assert/strict'
import puppeteer from 'puppeteer-core'

const base = new URL(process.env.BASE_URL ?? 'http://127.0.0.1:8501')
const chrome = process.env.CHROME_PATH
assert.ok(chrome, '必须设置 CHROME_PATH，指向本机 Chrome 可执行文件')

const repositoryId = 897992568
const scenarios = [
  { status: 'not_started', button: 'start-analysis', scope: 'quick' },
  { status: 'not_started', button: 'start-analysis', scope: 'window' },
  { status: 'failed', button: 'retry-collection', scope: 'quick' },
  { status: 'failed', button: 'retry-collection', scope: 'window' },
]

const browser = await puppeteer.launch({ executablePath: chrome, headless: true })
try {
  for (const scenario of scenarios) {
    const page = await browser.newPage()
    const collectionRequest = new Promise((resolve) => {
      page.on('request', (request) => {
        if (!request.url().endsWith(`/repositories/${repositoryId}/refresh`)) return
        resolve(request)
      })
    })

    await page.setRequestInterception(true)
    page.on('request', (request) => {
      const url = new URL(request.url())
      if (url.pathname.startsWith('/api/browser/')) {
        const json = (data, status = 200) => request.respond({
          status,
          contentType: 'application/json',
          body: JSON.stringify({ data, meta: { request_id: 'e2e', generated_at: '2026-11-11T00:00:00Z' } }),
        })
        if (url.pathname === '/api/browser/session') {
          void request.respond({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ csrf_token: 'e2e', expires_in: 1800 }),
          })
        } else if (request.method() === 'POST' && url.pathname.endsWith('/refresh')) {
          void json({ task_id: 'e2e-task', reused: false, status: 'queued' }, 202)
        } else if (request.method() === 'GET' && url.pathname === `/api/browser/v1/repositories/${repositoryId}`) {
          const analysisStatus = scenario.status === 'failed' ? 'failed' : 'not_started'
          void json({
            repository: { repository_id: repositoryId, full_name: 'neo4j-contrib/mcp-neo4j', analysis_status: analysisStatus },
            html_url: `https://github.com/neo4j-contrib/mcp-neo4j`, topics: [],
          })
        } else if (request.method() === 'GET' && url.pathname.endsWith('/analysis')) {
          void json({ repository_id: repositoryId, depth: 'deep', analysis_status: scenario.status, metrics: null, modules: {}, source_metadata: null, limitations: [] })
        } else if (request.method() === 'GET' && url.pathname.endsWith('/insights')) {
          void json({ repository_id: repositoryId, status: 'missing', window_available: false, available_window_days: 0, window_reason: '尚无事件级数据', limitations: [] })
        } else {
          void json({ items: [] })
        }
      } else if (url.origin === base.origin) {
        void request.continue()
      } else {
        void request.abort('blockedbyclient')
      }
    })

    await page.goto(new URL(`/repositories/${repositoryId}/overview`, base).href, { waitUntil: 'networkidle0' })
    await page.waitForSelector(`[data-testid="${scenario.button}"]`)
    await page.click(`[data-testid="collection-mode"] button[data-value="${scenario.scope}"]`)
    const requestPromise = collectionRequest
    await page.click(`[data-testid="${scenario.button}"]`)
    const request = await Promise.race([
      requestPromise,
      new Promise((_, reject) => setTimeout(() => reject(new Error(`未收到采集请求：${scenario.button} / ${scenario.scope}`)), 10000)),
    ])
    const payload = JSON.parse(request.postData() ?? '{}')
    assert.deepEqual(payload, {
      depth: 'deep', force: false, scope_kind: scenario.scope, window_days: 90,
    }, `${scenario.button} 必须提交选择的采集范围`)
    await page.close()
  }
  console.log(`通过 ${scenarios.length} 个空状态采集参数场景`)
} finally {
  await browser.close()
}
