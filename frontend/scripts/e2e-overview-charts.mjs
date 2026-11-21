import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import puppeteer from 'puppeteer-core'

const base = new URL(process.env.BASE_URL ?? 'http://127.0.0.1:5173')
const chrome = process.env.CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const outputDir = process.env.SCREENSHOT_DIR ?? '/tmp/repovantage-overview-charts'
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
  await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'light' }])
  await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 })
  await page.setRequestInterception(true)
  page.on('request', (request) => {
    const url = new URL(request.url())
    const respond = (data, status = 200) => request.respond({
      status,
      contentType: 'application/json',
      body: JSON.stringify({ data, meta: { request_id: 'overview-e2e', pagination: { total: repositories.length } } }),
    })
    if (url.pathname === '/api/browser/session') {
      void request.respond({ status: 200, contentType: 'application/json', body: JSON.stringify({ csrf_token: 'overview-e2e', expires_in: 1800 }) })
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
  await page.waitForFunction(() => ['.language-panel', '.stars-panel', '.scatter-panel'].every((selector) => {
    const canvas = document.querySelector(`${selector} .g2-chart__canvas canvas`)
    return canvas instanceof HTMLCanvasElement && canvas.width > 100 && canvas.height > 100
  }), { timeout: 15000 })
  const scatterPixels = await page.$eval('.scatter-panel .g2-chart__canvas canvas', (canvas) => {
    const context = canvas.getContext('2d')
    if (!context) return 0
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data
    let visible = 0
    for (let index = 0; index < pixels.length; index += 4) {
      if (pixels[index + 3] > 0 && (pixels[index] < 238 || pixels[index + 1] < 238 || pixels[index + 2] < 238)) visible += 1
    }
    return visible
  })
  assert.ok(scatterPixels > 1000, `散点图 Canvas 必须有实际绘制像素，检测到 ${scatterPixels}`)
  const pointColorPixels = await page.$eval('.scatter-panel .g2-chart__canvas canvas', (canvas) => {
    const context = canvas.getContext('2d')
    if (!context) return 0
    const pixels = context.getImageData(0, 0, canvas.width, Math.floor(canvas.height * 0.8)).data
    let visible = 0
    for (let index = 0; index < pixels.length; index += 4) {
      const max = Math.max(pixels[index], pixels[index + 1], pixels[index + 2])
      const min = Math.min(pixels[index], pixels[index + 1], pixels[index + 2])
      if (pixels[index + 3] > 100 && max > 90 && max - min > 35) visible += 1
    }
    return visible
  })
  assert.ok(pointColorPixels > 100, `散点图绘图区应有清晰可见的彩色仓库点，检测到 ${pointColorPixels} 个彩色像素`)
  const headings = await page.$$eval('[data-testid="overview-visualizations"] h2', (items) => items.map((item) => item.textContent?.trim()))
  for (const heading of ['主语言构成', 'Stars 关注度分层', 'Stars × Forks 关联', '最近 Push 活跃度']) assert.ok(headings.includes(heading), `总览应展示「${heading}」`)
  assert.equal(await page.$eval('.repository-total', (element) => element.textContent?.trim()), '18 / 18', '仓库列表的初始样本数应与四图一致')

  await mkdir(outputDir, { recursive: true })
  await page.screenshot({ path: `${outputDir}/overview-1440-light.png`, fullPage: true })

  await page.$eval('.scatter-panel .g2-chart__canvas canvas', (canvas) => canvas.scrollIntoView({ block: 'center' }))
  const rustMarker = await page.$eval('.scatter-panel .g2-chart__canvas canvas', (canvas) => {
    const context = canvas.getContext('2d')
    if (!context) return null
    const pixels = context.getImageData(0, 0, canvas.width, Math.floor(canvas.height * 0.8)).data
    let count = 0
    let maxX = -1
    let minY = Number.POSITIVE_INFINITY
    for (let y = 0; y < Math.floor(canvas.height * 0.8); y += 1) {
      for (let x = 0; x < canvas.width; x += 1) {
        const index = (y * canvas.width + x) * 4
        const [red, green, blue, alpha] = pixels.slice(index, index + 4)
        if (alpha > 180 && red > 120 && green < 100 && blue < 75) {
          count += 1
          maxX = Math.max(maxX, x)
          minY = Math.min(minY, y)
        }
      }
    }
    return count > 0 ? { count, x: maxX - 4, y: minY + 4 } : null
  })
  assert.ok(rustMarker && rustMarker.count > 20, '应能从绘图区识别 Rust 样本点像素')
  const scatterTarget = await page.$eval('.scatter-panel .g2-chart__canvas canvas', (canvas, marker) => {
    const rect = canvas.getBoundingClientRect()
    return { x: rect.left + marker.x, y: rect.top + marker.y }
  }, rustMarker)
  await page.mouse.click(scatterTarget.x, scatterTarget.y)
  await page.waitForFunction(() => document.querySelector('.selected-repository-chip')?.textContent?.includes('sample/project-14'), { timeout: 2500 })
  assert.equal(await page.$$eval('tr.is-selected[data-repository-id]', (rows) => rows.length), 1, '散点中的真实点选应通过稳定仓库 ID 联动列表')
  await page.evaluate(() => document.querySelector('.clear-selection')?.click())
  await page.waitForFunction(() => !document.querySelector('.selected-repository-chip'))

  const pythonButton = await page.evaluateHandle(() => [...document.querySelectorAll('.language-row')].find((button) => button.querySelector('.language-name')?.textContent?.trim() === 'Python'))
  assert.ok(pythonButton.asElement(), '主语言排名应提供真实可聚焦的 Python 筛选按钮')
  await pythonButton.asElement().click()
  await page.waitForFunction(() => document.querySelector('.repository-total')?.textContent?.trim() === '4 / 18')
  await pythonButton.asElement().click()
  await page.waitForFunction(() => document.querySelector('.repository-total')?.textContent?.trim() === '18 / 18')

  const zeroStarsButton = await page.evaluateHandle(() => [...document.querySelectorAll('.stars-legend-item')].find((button) => button.querySelector('span')?.textContent?.trim() === '0'))
  assert.ok(zeroStarsButton.asElement(), 'Stars 图应为 0 桶保留可操作图例')
  await zeroStarsButton.asElement().focus()
  await page.keyboard.press('Enter')
  await page.waitForFunction(() => document.querySelector('.repository-total')?.textContent?.trim() === '1 / 18')
  await page.evaluate(() => document.querySelector('.clear-filters')?.click())
  await page.waitForFunction(() => document.querySelector('.repository-total')?.textContent?.trim() === '18 / 18')

  const recentPushButton = await page.evaluateHandle(() => [...document.querySelectorAll('.push-filter-chip')].find((button) => button.querySelector('span')?.textContent?.trim() === '近 7 天'))
  await recentPushButton.asElement().click()
  assert.match(await page.$eval('.repository-total', (element) => element.textContent?.trim() ?? ''), /^[1-9]\d* \/ 18$/u, 'Push 时间分组应联动过滤仓库列表')
  await page.evaluate(() => document.querySelector('.clear-filters')?.click())

  const outlierButton = await page.$('.outlier-list button')
  assert.ok(outlierButton, '散点图应为最远端样本提供可访问的仓库选择项')
  const selectedName = await outlierButton.evaluate((button) => button.textContent?.split(' · ')[0])
  await outlierButton.click()
  await page.waitForSelector('.selected-repository-chip')
  assert.ok((await page.$eval('.selected-repository-chip', (element) => element.textContent?.trim() ?? '')).includes(selectedName), '点选应显示稳定仓库身份')
  assert.equal(await page.$$eval('tr.is-selected[data-repository-id]', (rows) => rows.length), 1, '散点选择应高亮仓库列表中的对应行')
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
    document.querySelector('.selected-repository-chip button')?.click()
  })
  await page.waitForFunction(() => !document.querySelector('.selected-repository-chip'))

  await page.setViewport({ width: 1280, height: 900, deviceScaleFactor: 1 })
  await page.screenshot({ path: `${outputDir}/overview-1280-light.png`, fullPage: true })
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 })
  await page.waitForFunction(() => {
    const host = document.querySelector('.scatter-panel .g2-chart__canvas')
    const canvas = host?.querySelector('canvas')
    return host instanceof HTMLElement && canvas instanceof HTMLCanvasElement && canvas.clientWidth <= host.clientWidth + 2
  })
  const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  assert.ok(mobileOverflow <= 2, `390px 页面不应出现横向溢出，当前溢出 ${mobileOverflow}px`)
  await page.screenshot({ path: `${outputDir}/overview-390-light.png`, fullPage: true })
  await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 })
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.mouse.move(8, 8)
  const themeButton = await page.$('button[aria-label="切换深色主题"]')
  assert.ok(themeButton, `深色主题按钮应可用；当前按钮：${await page.$$eval('button', (buttons) => buttons.map((button) => button.getAttribute('aria-label') ?? button.textContent?.trim()).filter(Boolean).join(', '))}`)
  await themeButton.evaluate((button) => button.click())
  await page.waitForFunction(() => document.documentElement.classList.contains('dark'))
  await new Promise((resolve) => setTimeout(resolve, 500))
  const darkDonutColorCount = await page.$eval('.language-panel .g2-chart__canvas canvas', (canvas) => {
    const pixels = canvas.getContext('2d')?.getImageData(0, 0, canvas.width, canvas.height).data
    if (!pixels) return 0
    const colors = new Set()
    for (let index = 0; index < pixels.length; index += 4) {
      const [red, green, blue, alpha] = pixels.slice(index, index + 4)
      if (alpha > 150 && Math.max(red, green, blue) - Math.min(red, green, blue) > 45) colors.add([red >> 4, green >> 4, blue >> 4].join(','))
    }
    return colors.size
  })
  assert.ok(darkDonutColorCount >= 5, `深色主题应保留多个语言扇区的颜色，检测到 ${darkDonutColorCount} 种`)
  await page.screenshot({ path: `${outputDir}/overview-1440-dark.png`, fullPage: true })

  assert.deepEqual(pageErrors, [], `页面运行时错误：${pageErrors.join('; ')}`)
  console.log(`总览图表浏览器验收通过；截图保存在 ${outputDir}`)
} finally {
  await browser.close()
}
