import assert from 'node:assert/strict'
import puppeteer from 'puppeteer-core'

const base = new URL(process.env.BASE_URL ?? 'http://127.0.0.1:5173')
const executablePath = process.env.CHROME_PATH
assert.ok(executablePath, '必须设置 CHROME_PATH，指向独立测试浏览器')
const browser = await puppeteer.launch({ executablePath, headless: true, args: process.platform === 'linux' ? ['--no-sandbox'] : [] })

try {
  for (const [theme, width] of [['light', 1440], ['dark', 840]]) {
    const context = await browser.createBrowserContext()
    const page = await context.newPage()
    page.setDefaultTimeout(8000)
    const errors = []
    await page.setViewport({ width, height: 1000 })
    await page.evaluateOnNewDocument((value) => {
      localStorage.setItem('repovantage-theme', value)
      localStorage.setItem('repovantage-analysis-window', '90')
    }, theme)
    await page.setRequestInterception(true)
    page.on('request', (request) => {
      if (request.url().startsWith(base.origin)) void request.continue()
      else void request.abort()
    })
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('console', (message) => {
      if (message.type() === 'error' && !message.text().includes('Failed to load resource')) errors.push(message.text())
    })
    await page.goto(new URL('/repositories/grid-lite/overview', base).href, { waitUntil: 'networkidle0' })
    assert.equal(await page.$eval('[data-testid="app"]', (element) => element.getAttribute('data-mode')), 'mock')
    assert.equal(await page.evaluate(() => document.documentElement.classList.contains('dark')), theme === 'dark')
    await page.waitForSelector('[data-testid="commit-activity-chart"] canvas')

    await page.evaluate(async () => {
      const { REPOSITORIES } = await import('/src/mocks/catalog.ts')
      REPOSITORIES.find((repo) => repo.id === 'grid-lite').releases.push({
        tag: 'v1.9.1', publishedAt: '2025-03-20T10:30:00Z', prerelease: false, intervalDays: 2, note: '额外版本测试',
      })
    })
    for (const days of [30, 90]) {
      await page.click('[data-testid="analysis-window"] button[data-value="' + days + '"]')
      await page.waitForFunction((value) => document.querySelector('[data-testid="repository-analysis"]')?.getAttribute('data-window-days') === String(value), {}, days)
      await page.waitForSelector('[data-testid="commit-activity-chart"] canvas')
    }
    await page.click('[data-testid="commit-activity-chart"] details summary')
    const releases = await page.$$eval('[data-testid="commit-activity-chart"] details button', (buttons) => buttons.map((button) => button.textContent ?? ''))
    assert.ok(releases.some((text) => text.includes('v1.9.0') && text.includes('v1.9.1')), '同周 Release 应聚合并保留全部标签')
    await page.evaluate(() => [...document.querySelectorAll('[data-testid="commit-activity-chart"] details button')].find((button) => button.textContent.includes('v1.9.1')).click())
    const releaseList = await page.waitForSelector('[data-testid="activity-release-list"]', { visible: true })
    assert.match(await releaseList.evaluate((element) => element.textContent), /2 次发布/)
    await page.evaluate(() => [...document.querySelectorAll('[data-testid="activity-release-list"] button')].find((button) => button.textContent.includes('v1.9.1')).click())
    await page.waitForFunction(() => document.querySelector('[role="dialog"]')?.textContent.includes('额外版本测试'))
    await page.keyboard.press('Escape')
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'))

    const commitButton = await page.waitForSelector('[data-testid="commit-activity-chart"] details button:not(:disabled)')
    await page.evaluate(() => { const details = document.querySelector('[data-testid="commit-activity-chart"] details'); if (details && !details.open) details.querySelector('summary')?.click() })
    await page.evaluate(() => document.querySelector('[data-testid="commit-activity-chart"] details button:not(:disabled)')?.click())
    await page.waitForFunction(() => document.querySelector('[role="dialog"]')?.textContent.includes('次提交'))
    await page.keyboard.press('Escape')
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'))

    await page.click('a[href="/repositories/grid-lite/releases"]')
    await page.waitForFunction(() => location.pathname.endsWith('/releases'))
    await page.waitForSelector('table tbody button')
    await page.evaluate(() => [...document.querySelectorAll('table tbody button')].find((button) => button.textContent.includes('v1.9.0')).click())
    await page.waitForFunction(() => document.querySelector('[role="dialog"]')?.textContent.includes('日历热力图'))
    await page.keyboard.press('Escape')
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'))

    await page.goto(new URL('/repositories/steady-core/overview', base).href, { waitUntil: 'networkidle0' })
    await page.waitForSelector('[data-testid="commit-activity-chart"] details summary')
    await page.click('[data-testid="commit-activity-chart"] details summary')
    const partialWeek = await page.$$eval('[data-testid="commit-activity-chart"] details button', (buttons) => buttons.find((button) => button.textContent.includes('2025-03-17'))?.textContent ?? '')
    assert.match(partialWeek, /Commit \d+.*部分覆盖/, '部分覆盖周应显示已观察 Commit 数和覆盖状态')
    assert.deepEqual(errors, [], theme + ' 页面出现脚本错误')
    console.log(theme + ' ' + width + 'px：G2 绘制、同周 Release 聚合、Release 详情、Commit 明细与部分覆盖通过')
    await context.close()
  }
} finally {
  await browser.close()
}
