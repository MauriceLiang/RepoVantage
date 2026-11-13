import assert from 'node:assert/strict'
import puppeteer from 'puppeteer-core'

const base = new URL(process.env.BASE_URL ?? 'http://127.0.0.1:5174')
assert.ok(['127.0.0.1', 'localhost'].includes(base.hostname), '测试只允许连接本地开发服务器')
const chrome = process.env.CHROME_PATH
assert.ok(chrome, '请设置 CHROME_PATH，指向本机 Chromium 可执行文件')

const datasets = { items: [
  { dataset_id: 'course-research-300-v1', type: 'research', name: '默认 300 仓库' },
  { dataset_id: 'research-2026-v1', type: 'research', name: '正式研究' },
] }
const course = {
  sample_size: 3, dataset_status: 'analyzable', dataset_version: 'course-research-300-v1',
  source: '测试数据', population_scope: 'fixture', is_probability_sample: false,
  course_summary: {
    data_as_of: '2026-11-08T00:00:00Z',
    observation_window: { start: '2026-08-10T00:00:00Z', end_exclusive: '2026-11-02T00:00:00Z' },
    weekly_records: 36, repositories_with_12_complete_commit_weeks: 2,
    split_counts: { train: 2, test: 3 },
    coverage: { commit_week_complete_or_true_zero: 35, pr_opened_week_complete_or_true_zero: 32, pr_merged_week_complete_or_true_zero: 30, pr_merged_week_partial_concurrent_change: 3 },
  },
  groups: [
    { language: 'TypeScript', n: 2, metrics: { commits_weekly_mean: { count: 1, mean: 5 } } },
    { language: 'Rust', n: 1, metrics: { commits_weekly_mean: { count: 0, mean: null } } },
  ],
  rows: [
    { repository_id: 1, full_name: 'example/alpha', language: 'TypeScript', sample_role: 'test', values: { commits_weekly_mean: 5, course_active_weeks_12w: 10 } },
    { repository_id: 2, full_name: 'example/beta', language: 'TypeScript', sample_role: 'test', values: { commits_weekly_mean: null, course_active_weeks_12w: null } },
    { repository_id: 3, full_name: 'example/gamma', language: 'Rust', sample_role: 'test', values: { commits_weekly_mean: null, course_active_weeks_12w: null } },
  ],
  metric_quality: { commits_weekly_mean: { valid_samples: 1, missing_count: 2, missing_rate: 2 / 3, missing_reasons: [] } },
  limitations: ['测试样本不代表总体。'],
}
const quality = { records_total: 3, missing_fields: [{ field: 'language', count: 0, rate: 0 }] }
const envelope = (data) => JSON.stringify({ data, meta: { request_id: 'research-fixture' } })

const browser = await puppeteer.launch({ executablePath: chrome, headless: true, args: process.platform === 'linux' ? ['--no-sandbox'] : [] })
try {
  for (const theme of ['light', 'dark']) {
    const context = await browser.createBrowserContext()
    const page = await context.newPage()
    const unexpected = [], apiRequests = [], errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.setViewport({ width: 1440, height: 900 })
    await page.evaluateOnNewDocument((value) => {
      localStorage.setItem('repovantage-theme', value)
      document.addEventListener('click', (event) => {
        if (event.target instanceof HTMLAnchorElement && event.target.download) event.preventDefault()
      }, true)
    }, theme)
    await page.setRequestInterception(true)
    page.on('request', (request) => {
      const url = new URL(request.url())
      if (!url.pathname.startsWith('/api/browser/')) return void request.continue()
      apiRequests.push({ path: url.pathname, method: request.method(), analysisMode: url.searchParams.get('analysis_mode') })
      if (request.method() !== 'GET') unexpected.push(`${request.method()} ${url.pathname}`)
      const json = (body) => request.respond({ status: 200, contentType: 'application/json', body })
      if (url.pathname === '/api/browser/session') return void json(JSON.stringify({ csrf_token: 'fixture' }))
      if (url.pathname === '/api/browser/v1/datasets') return void json(envelope(datasets))
      if (url.pathname === '/api/browser/v1/research/insights') return void json(envelope(course))
      if (url.pathname === '/api/browser/v1/research/data-quality') return void json(envelope(quality))
      if (url.pathname.startsWith('/api/browser/v1/exports/')) return void request.respond({ status: 200, contentType: 'text/csv', body: 'id\n1\n' })
      unexpected.push(`GET ${url.pathname}`)
      return void request.respond({ status: 404, contentType: 'application/json', body: '{}' })
    })

    await page.goto(new URL('/research', base).href, { waitUntil: 'networkidle0' })
    assert.equal(await page.$eval('[data-testid="app"]', (node) => node.getAttribute('data-mode')), 'http')
    assert.equal(await page.$('[data-testid="research-mode"]'), null, '研究分析固定使用默认 300 仓库数据，不展示模式选项')
    await page.waitForSelector('[data-testid="course-repositories"]')
    const text = (selector) => page.$eval(selector, (node) => node.textContent ?? '')
    assert.match(await text('[data-testid="course-research-summary"]'), /默认仓库\s*3个/)
    assert.match(await text('[data-testid="course-research-summary"]'), /Commit 完整覆盖\s*2\s*\/\s*3/)
    assert.match(await text('[data-testid="course-language-distribution"]'), /TypeScript.*2\s*·\s*66\.7%.*n=1.*5\.00/s)
    assert.match(await text('[data-testid="course-language-distribution"]'), /Rust.*n=0.*—/s)
    assert.match(await text('[data-testid="course-weekly-coverage"]'), /PR 合并周记录\s*30\s*\/\s*36.*83\.3%.*3 条部分覆盖/s)

    const search = '[aria-label="搜索课程仓库"]'
    await page.type(search, 'missing')
    assert.match(await text('[data-testid="course-repositories"]'), /没有匹配的仓库/)
    await page.$eval(search, (node) => { node.value = ''; node.dispatchEvent(new Event('input', { bubbles: true })) })
    await page.type(search, 'example/alpha')
    assert.equal(await page.$$eval('[data-testid="course-repositories"] tbody tr', (rows) => rows.length), 1)
    assert.equal(await page.$eval('[data-testid="course-repositories"] tbody a', (node) => node.getAttribute('href')), '/repositories/1/overview')
    await page.click('[aria-label="加入对比 example/alpha"]')
    assert.ok(await page.$('[aria-label="已加入对比 example/alpha"]'))

    for (const [button, path] of [['export-research-members', '/exports/repositories.csv'], ['export-research-statistics', '/exports/research-insights.csv']]) {
      await Promise.all([page.waitForResponse((response) => response.url().includes(path)), page.click(`[data-testid="${button}"]`)])
    }
    for (const width of [1440, 390, 320]) {
      await page.setViewport({ width, height: 844 })
      await page.waitForFunction(() => [...document.querySelectorAll('.route-page canvas')].every((canvas) => canvas.getBoundingClientRect().width <= canvas.parentElement.parentElement.clientWidth + 1))
      const geometry = await page.evaluate(() => ({
        pageOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
        cardsOverflow: [...document.querySelectorAll('.route-page .gd-card')].some((node) => {
          const rect = node.getBoundingClientRect()
          return rect.left < -1 || rect.right > innerWidth + 1
        }),
        tableScrollable: (() => { const node = document.querySelector('[data-testid="course-repositories"] [role="region"]'); return node.scrollWidth > node.clientWidth + 1 })(),
        clippedButtons: [...document.querySelectorAll('.route-page button')].filter((node) => !node.closest('[role="region"]') && node.getBoundingClientRect().width > 0 && (node.getBoundingClientRect().right > innerWidth + 1 || node.scrollWidth > node.clientWidth + 1)).map((node) => node.textContent?.trim()),
        overflowers: [...document.querySelectorAll('body *')].filter((node) => !node.closest('[role="region"]') && node.getBoundingClientRect().right > innerWidth + 1).slice(0, 5).map((node) => ({ tag: node.tagName, className: String(node.className).slice(0, 100), text: node.textContent?.trim().slice(0, 50) })),
      }))
      assert.equal(geometry.pageOverflow, false, `${theme} ${width}px 页面横向溢出 ${JSON.stringify(geometry.overflowers)}`)
      assert.equal(geometry.cardsOverflow, false, `${theme} ${width}px 卡片超出视口`)
      assert.deepEqual(geometry.clippedButtons, [], `${theme} ${width}px 按钮文字或控件被裁切`)
      if (width <= 390) {
        assert.equal(geometry.tableScrollable, true, '窄屏表格应可横向滚动')
        assert.match(await text('[data-testid="course-repositories"]'), /左右滑动表格/)
      }
    }
    await page.setViewport({ width: 800, height: 900 })
    await page.evaluate(() => { document.documentElement.style.zoom = '200%' })
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1), false, `${theme} 200% 缩放页面横向溢出`)
    await page.evaluate(() => { document.documentElement.style.zoom = ''; document.documentElement.style.fontSize = '200%' })
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1), false, `${theme} 200% 字号页面横向溢出`)
    await page.$eval('[data-testid="research-data-quality"]', (node) => node.scrollIntoView({ block: 'end' }))
    assert.equal(await page.$eval('[data-testid="research-data-quality"]', (node) => node.getBoundingClientRect().bottom <= innerHeight + 1), true, '页面底部应可滚动到数据质量说明')
    assert.deepEqual(unexpected, [])
    assert.deepEqual(errors, [])
    assert.ok(apiRequests.filter((request) => request.path.endsWith('/research/insights')).every((request) => request.analysisMode === 'course'), '页面只请求默认 300 仓库分析数据')
    assert.ok(apiRequests.some((request) => request.path.endsWith('/exports/repositories.csv')))
    assert.ok(apiRequests.some((request) => request.path.endsWith('/exports/research-insights.csv')))
    console.log(`${theme}: 默认仓库样本统计、缺失值、筛选、对比、导出及响应式通过`)
    await context.close()
  }
} finally {
  await browser.close()
}
