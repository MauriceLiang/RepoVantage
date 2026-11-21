import assert from 'node:assert/strict'
import puppeteer from 'puppeteer-core'

const base = new URL(process.env.BASE_URL ?? 'http://127.0.0.1:5174')
assert.ok(['127.0.0.1', 'localhost'].includes(base.hostname), '测试只允许连接本地开发服务器')
const chrome = process.env.CHROME_PATH
assert.ok(chrome, '请设置 CHROME_PATH，指向本机 Chromium 可执行文件')

const weeks = Array.from({ length: 12 }, (_, index) => {
  const date = new Date(Date.UTC(2026, 7, 10 + index * 7)).toISOString().slice(0, 10)
  return date
})
const sampleDefinitions = [
  { id: 1, name: 'example/alpha', language: 'TypeScript', role: 'train', commits: 10, prs: 2, stars: 120 },
  { id: 2, name: 'example/beta', language: 'Rust', role: 'test', commits: 5, prs: 1, stars: 80 },
  { id: 3, name: 'example/gamma', language: 'TypeScript', role: 'test', commits: 4, prs: 1, stars: 40 },
  { id: 4, name: 'example/delta', language: 'Go', role: 'test', commits: 8, prs: 3, stars: 60 },
]
const points = sampleDefinitions.map((sample) => ({
  repository_id: sample.id,
  full_name: sample.name,
  language: sample.language,
  sample_role: sample.role,
  stars: sample.stars,
  weekly_commit_mean: sample.commits,
  weekly_pr_open_mean: sample.prs,
  observation_window: { start: '2026-08-10T00:00:00Z', end_exclusive: '2026-11-02T00:00:00Z', weeks: 12 },
  coverage: { commits: 'complete', prs_opened: 'complete' },
  weekly_trace: weeks.map((week_start) => ({ week_start, commits: sample.commits, prs_opened: sample.prs })),
}))
const atlas = {
  dataset_id: 'research-fixture-v1',
  data_as_of: '2026-11-08T00:00:00Z',
  observation_window: { start: '2026-08-10T00:00:00Z', end_exclusive: '2026-11-02T00:00:00Z', weeks: 12 },
  repository_count: points.length,
  point_count: points.length,
  excluded_count: 0,
  excluded_reasons: {},
  weekly_record_count: points.length * 12,
  coordinates: { x: 'weekly_commit_mean', y: 'weekly_pr_open_mean', stars: 'stars' },
  points,
}
const envelope = (data) => JSON.stringify({ data, meta: { request_id: 'research-fixture' } })

const browser = await puppeteer.launch({ executablePath: chrome, headless: true, args: process.platform === 'linux' ? ['--no-sandbox'] : [] })
try {
  for (const theme of ['light', 'dark']) {
    const context = await browser.createBrowserContext()
    const page = await context.newPage()
    const unexpected = []
    const apiRequests = []
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.setViewport({ width: 1440, height: 900 })
    await page.evaluateOnNewDocument((value) => localStorage.setItem('repovantage-theme', value), theme)
    await page.setRequestInterception(true)
    page.on('request', (request) => {
      const url = new URL(request.url())
      if (!url.pathname.startsWith('/api/browser/')) return void request.continue()
      apiRequests.push({ path: url.pathname, method: request.method() })
      if (request.method() !== 'GET') unexpected.push(`${request.method()} ${url.pathname}`)
      if (url.pathname === '/api/browser/session') {
        return void request.respond({ status: 200, contentType: 'application/json', body: JSON.stringify({ csrf_token: 'fixture' }) })
      }
      if (url.pathname === '/api/browser/v1/research/atlas') {
        return void request.respond({ status: 200, contentType: 'application/json', body: envelope(atlas) })
      }
      unexpected.push(`GET ${url.pathname}`)
      return void request.respond({ status: 404, contentType: 'application/json', body: '{}' })
    })

    await page.goto(new URL('/research', base).href, { waitUntil: 'networkidle0' })
    assert.equal(await page.$eval('[data-testid="app"]', (node) => node.getAttribute('data-mode')), 'http')
    await page.waitForSelector('.atlas-meta-row')
    await page.waitForSelector('.research-g2-chart canvas, .research-g2-chart svg')
    assert.equal(await page.$eval('.atlas-count', (node) => node.textContent.trim()), '4 / 4')
    assert.match(await page.$eval('.atlas-meta-row', (node) => node.textContent), /4 个真实节点.*48 条仓库周记录/s)
    assert.match(await page.$eval('.atlas-detail-meta', (node) => node.textContent), /complete.*complete/)
    assert.ok(await page.$('.atlas-trend-panel canvas, .atlas-trend-panel svg'), '选中仓库应显示 G2 周轨迹')
    await page.screenshot({ path: `/tmp/repovantage-v45-research-${theme}-desktop.png`, fullPage: true })

    await page.$$eval('.atlas-list-row', (rows) => {
      const row = rows.find((item) => item.textContent?.includes('example/beta'))
      if (!(row instanceof HTMLButtonElement)) throw new Error('缺少 example/beta 样本行')
      row.click()
    })
    await page.waitForFunction(() => document.querySelector('.atlas-repo-title strong')?.textContent === 'example/beta')
    assert.match(await page.$eval('.atlas-measures', (node) => node.textContent), /5\.00.*1\.00/s)

    const view = await page.$('select[aria-label="研究视图"]')
    await view.select('activity-volatility')
    assert.match(await page.$eval('.atlas-view-description', (node) => node.textContent), /总体标准差/)
    await view.select('pr-trend')
    assert.match(await page.$eval('.atlas-view-description', (node) => node.textContent), /最小二乘斜率/)
    await view.select('activity-mean')

    const language = await page.$('select[aria-label="按语言筛选"]')
    await language.select('TypeScript')
    assert.equal(await page.$eval('.atlas-count', (node) => node.textContent.trim()), '2 / 4')
    await language.select('全部语言')
    const role = await page.$('select[aria-label="按样本角色筛选"]')
    await role.select('train')
    assert.equal(await page.$eval('.atlas-count', (node) => node.textContent.trim()), '1 / 4')
    await role.select('全部样本角色')

    await page.type('input[aria-label="搜索仓库名称"]', 'example/delta')
    assert.equal(await page.$eval('.atlas-count', (node) => node.textContent.trim()), '1 / 4')
    assert.equal(await page.$eval('.atlas-repo-title strong', (node) => node.textContent), 'example/delta')
    await page.$eval('input[aria-label="搜索仓库名称"]', (node) => { node.value = ''; node.dispatchEvent(new Event('input', { bubbles: true })) })

    await page.type('input[aria-label="最低周均 Commit"]', '6')
    await page.waitForFunction(() => document.querySelector('.atlas-count')?.textContent.trim() === '2 / 4')
    await page.click('.atlas-clear-filter')
    assert.equal(await page.$eval('.atlas-count', (node) => node.textContent.trim()), '4 / 4')

    for (const width of [1440, 390, 320]) {
      await page.setViewport({ width, height: 844 })
      await page.waitForFunction(() => [...document.querySelectorAll('.research-g2-chart, .g2-chart__canvas')].every((host) => {
        const canvas = host.querySelector('canvas')
        return canvas instanceof HTMLCanvasElement && canvas.clientWidth <= host.clientWidth + 2
      }))
      const geometry = await page.evaluate(() => ({
        pageWidth: document.documentElement.scrollWidth,
        viewportWidth: document.documentElement.clientWidth,
        chartRight: document.querySelector('.research-g2-chart').getBoundingClientRect().right,
      }))
      assert.ok(geometry.pageWidth <= geometry.viewportWidth + 1, `${theme} ${width}px 页面横向溢出：${JSON.stringify(geometry)}`)
      assert.ok(geometry.chartRight <= geometry.viewportWidth + 1, `${theme} ${width}px 图表超出视口：${JSON.stringify(geometry)}`)
      if (width === 390) await page.screenshot({ path: `/tmp/repovantage-v45-research-${theme}-mobile.png`, fullPage: true })
    }
    assert.deepEqual(unexpected, [], '研究图谱不应调用未配置的 API 或写接口')
    assert.deepEqual(errors, [], `页面错误：${errors.join('; ')}`)
    assert.ok(apiRequests.some((request) => request.path.endsWith('/research/atlas')))
    assert.ok(apiRequests.every((request) => request.method === 'GET'))
    console.log(`${theme}: 真实 API 图谱、G2 轨迹、样本联动、筛选、视图切换与 320px/390px 响应式通过`)
    await context.close()
  }
} finally {
  await browser.close()
}
