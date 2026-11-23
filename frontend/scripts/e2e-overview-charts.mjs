import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import puppeteer from 'puppeteer-core'

const base = new URL(process.env.BASE_URL ?? 'http://127.0.0.1:5173')
const chrome = process.env.CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const outputDir = process.env.SCREENSHOT_DIR ?? '/tmp/repovantage-overview-charts'
await mkdir(outputDir, { recursive: true })
const DAY = 24 * 60 * 60 * 1000
const now = Date.now()
const languages = [
  'Python', 'Python', 'Python', 'Python', 'TypeScript', 'TypeScript', 'TypeScript', 'Go', 'Go', 'Go',
  'Java', 'Java', 'Rust', 'Rust', 'JavaScript', 'C++', null, null,
]
const stars = [0, 1, 20, 99, 100, 101, 1000, 1001, 1200, 10000, 10001, 50000, 100001, 230000, 12, null, 500, 5]
const forks = [0, 0, 2, 10, 15, 20, 80, 90, 100, 500, 600, 1200, 4000, 8000, 12, 3, null, 1]
const pushAges = [1, 2, 3, 5, 8, 12, 22, 28, 40, 75, 120, 200, 400, 800, null, null, -1, Number.NaN]
const repositories = languages.map((language, index) => {
  const age = pushAges[index]
  const pushedAt = age === null ? null : Number.isNaN(age) ? 'bad-date' : age < 0 ? new Date(now + DAY).toISOString() : new Date(now - age * DAY).toISOString()
  const fullName = `sample/project-${String(index + 1).padStart(2, '0')}`
  return {
    repository: {
      repository_id: index + 1,
      full_name: fullName,
      description: `用于总览图表验收的专用数据 ${index + 1}`,
      language,
      stars: stars[index],
      forks: forks[index],
      pushed_at: pushedAt,
      created_at: '2020-01-01T00:00:00Z',
      archived: false,
      analysis_status: 'completed',
      data_status: 'fresh',
      last_successful_collection_at: new Date(now).toISOString(),
    },
    html_url: `https://github.com/${fullName}`,
    topics: [],
  }
})

const browser = await puppeteer.launch({
  executablePath: chrome,
  headless: true,
  args: process.platform === 'linux' ? ['--no-sandbox'] : [],
})

try {
  const page = await browser.newPage()
  const pageErrors = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  await page.setViewport({ width: 1440, height: 960, deviceScaleFactor: 1 })
  await page.setRequestInterception(true)
  page.on('request', (request) => {
    const url = new URL(request.url())
    const respond = (data) => request.respond({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data, meta: { request_id: 'overview-e2e', pagination: { total: repositories.length } } }),
    })
    if (url.pathname === '/api/browser/session') {
      void request.respond({ status: 200, contentType: 'application/json', body: JSON.stringify({ csrf_token: 'overview-e2e' }) })
    } else if (url.pathname === '/api/browser/v1/library/repositories') {
      void respond({ items: repositories })
    } else if (url.pathname === '/api/browser/v1/tasks') {
      void respond({ items: [] })
    } else if (url.origin === base.origin) {
      void request.continue()
    } else {
      void request.abort('blockedbyclient')
    }
  })

  await page.goto(new URL('/', base).href, { waitUntil: 'networkidle0' })
  await page.waitForSelector('[data-testid="overview-visualizations"]')
  await page.waitForFunction(() =>
    [...document.querySelectorAll('.language-panel .g2-chart__canvas canvas, .scatter-panel .g2-chart__canvas canvas')].length === 2
    && [...document.querySelectorAll('.language-panel .g2-chart__canvas canvas, .scatter-panel .g2-chart__canvas canvas')].every((canvas) => canvas.width > 100 && canvas.height > 100),
    { timeout: 20000 },
  )
  const snapshot = await page.evaluate(() => ({
    title: document.querySelector('.language-panel')?.textContent ?? '',
    scatter: document.querySelector('.scatter-panel')?.textContent ?? '',
    headings: [...document.querySelectorAll('[data-testid="overview-visualizations"] h2')].map((element) => element.textContent?.trim()),
  }))
  assert.match(snapshot.title, /18 个仓库/)
  assert.match(snapshot.scatter, /配对 n=16 \/ 18/)
  for (const title of ['主语言构成', 'Stars 关注度分层', 'Stars × Forks 关联']) {
    assert.ok(snapshot.headings.includes(title), '缺少图表：' + title)
  }
  await page.screenshot({ path: outputDir + '/overview-desktop.png', fullPage: true })

  // Verify component events without depending on chart tooltip or pointer overlays.
  const clicked = await page.evaluate(() => {
    const button = [...document.querySelectorAll('.language-row')].find((element) =>
      element.querySelector('.language-name')?.textContent?.trim() === 'Python')
    if (!(button instanceof HTMLButtonElement)) return false
    button.click()
    return true
  })
  assert.ok(clicked, '找不到 Python 语言筛选')
  await page.waitForFunction(() =>
    document.querySelector('.overview-filter-summary strong')?.textContent?.includes('4 / 18'),
    { timeout: 10000 },
  )
  await page.evaluate(() => document.querySelector('.clear-filters')?.click())
  await page.waitForFunction(() => !document.querySelector('.overview-filter-summary'))

  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 })
  await page.screenshot({ path: outputDir + '/overview-mobile.png', fullPage: true })
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  assert.ok(overflow <= 2, '移动端存在 ' + overflow + 'px 横向溢出')

  await page.setViewport({ width: 1440, height: 960, deviceScaleFactor: 1 })
  await page.evaluate(() => document.querySelector('button[aria-label="切换深色主题"]')?.click())
  await page.waitForFunction(() => document.documentElement.classList.contains('dark'))
  await page.screenshot({ path: outputDir + '/overview-dark.png', fullPage: true })
  assert.deepEqual(pageErrors, [], '浏览器运行错误：' + pageErrors.join('; '))
  console.log('PASS: overview data, G2 canvas, filtering, responsive layout, theme')
} finally {
  await browser.close()
}
