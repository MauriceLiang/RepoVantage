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
    const errors = []
    await page.setViewport({ width, height: 1050 })
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
    await page.goto(new URL('/repositories/grid-lite/issues', base).href, { waitUntil: 'networkidle0' })
    assert.equal(await page.$eval('[data-testid="app"]', (element) => element.getAttribute('data-mode')), 'mock')
    assert.equal(await page.evaluate(() => document.documentElement.classList.contains('dark')), theme === 'dark')
    await page.waitForSelector('[data-testid="issue-trend-chart"] canvas')

    await page.evaluate(async () => {
      const { MockRepositoryDataSource } = await import('/src/services/mockRepositoryDataSource.ts')
      const original = MockRepositoryDataSource.prototype.getAnalysis
      MockRepositoryDataSource.prototype.getAnalysis = async function (id, days) {
        const result = await original.call(this, id, days)
        if (id === 'grid-lite' && days === 90) {
          const ready = (date, value) => ({ date, value, quality: 'ready', completeWeek: true })
          const partial = (date, observedValue) => ({ date, value: null, quality: 'partial', completeWeek: true, observedValue })
          result.issues.coverage = { state: 'partial', label: '部分覆盖' }
          result.issues.series = [
            { key: 'opened', label: '新增', points: [ready('2025-01-06', 8), ready('2025-01-13', 3), ready('2025-01-20', 0), partial('2025-01-27', 2), ready('2025-02-17', 4)] },
            { key: 'closed', label: '关闭', points: [ready('2025-01-06', 5), ready('2025-01-13', 6), ready('2025-01-20', 0), partial('2025-01-27', 0), ready('2025-02-03', 4), ready('2025-02-17', 4)] },
          ]
        }
        return result
      }
    })
    for (const days of [30, 90]) {
      await page.click('[data-testid="analysis-window"] button[data-value="' + days + '"]')
      await page.waitForFunction((value) => document.querySelector('[data-testid="repository-analysis"]')?.getAttribute('data-window-days') === String(value), {}, days)
      await page.waitForSelector('[data-testid="issue-trend-chart"] canvas')
    }

    await page.click('[data-testid="issue-trend-chart"] details summary')
    const weeklyRows = await page.$$eval('[data-testid="issue-trend-chart"] details li', (items) => items.map((item) => item.textContent ?? ''))
    assert.ok(weeklyRows.some((row) => row.includes('2025-01-20') && row.includes('新增 0，完整覆盖') && row.includes('关闭 0，完整覆盖') && row.includes('新增减关闭 0')), '真实 0 必须保留为完整周零值')
    assert.ok(weeklyRows.some((row) => row.includes('2025-01-27') && row.includes('新增 2，部分覆盖') && row.includes('关闭 0 已观察，覆盖不完整') && row.includes('覆盖不完整，未计算')), '部分覆盖样本不能用于完整周差值')
    assert.ok(weeklyRows.some((row) => row.includes('2025-02-10') && row.includes('无可用数据')), '缺失周应显式断开而不补零')
    assert.ok(await page.$('[data-testid="issue-trend-chart"] [role="img"][aria-label="Issue 每周新增、关闭及完整周差值"]'), 'G2 图应提供可访问名称')
    assert.deepEqual(errors, [], theme + ' 页面出现脚本错误')
    console.log(theme + ' ' + width + 'px：G2 绘制、完整零值、部分覆盖差值与缺失周通过')
    await context.close()
  }
} finally {
  await browser.close()
}
