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
    await page.setViewport({ width, height: 1000 })
    await page.evaluateOnNewDocument((value) => {
      localStorage.setItem('repovantage-theme', value)
      localStorage.setItem('repovantage-analysis-window', '90')
    }, theme)
    await page.setRequestInterception(true)
    page.on('request', (request) => {
      // 测试只允许访问本机演示服务，不连接 GitHub 或其他外部资源。
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

    // 在演示数据中补一个同周版本，验证多个标记不会互相遮挡或丢失。
    await page.evaluate(async () => {
      const { REPOSITORIES } = await import('/src/mocks/catalog.ts')
      REPOSITORIES.find((repo) => repo.id === 'grid-lite').releases.push({
        tag: 'v1.9.1', publishedAt: '2025-03-20T10:30:00Z', prerelease: false, intervalDays: 2, note: '额外版本测试',
      })
    })
    for (const days of [30, 90]) {
      await page.click(`[data-testid="analysis-window"] button[data-value="${days}"]`)
      await page.waitForFunction((value) => document.querySelector('[data-testid="repository-analysis"]')?.getAttribute('data-window-days') === String(value), {}, days)
      await page.waitForSelector('[data-testid="commit-activity-chart"] canvas')
    }

    const chartInfo = (axis, date, value) => page.evaluate(async ({ axis, date, value }) => {
      const element = document.querySelector('[data-testid="commit-activity-chart"]')
      element.scrollIntoView({ block: 'center' })
      const core = performance.getEntriesByType('resource').map((entry) => entry.name).find((name) => name.includes('echarts_core'))
      const echarts = await import(core)
      const chart = echarts.getInstanceByDom(element)
      const option = chart.getOption()
      const index = option.xAxis[0].data.indexOf(date)
      const pixel = chart.convertToPixel({ xAxisIndex: axis, yAxisIndex: axis }, [index, value])
      const rect = element.getBoundingClientRect()
      return {
        x: rect.x + pixel[0], y: rect.y + pixel[1], index,
        withinViewport: rect.left >= 0 && rect.right <= innerWidth + 1,
        types: option.series.map((series) => series.type),
        average: option.series[1].data[index],
        release: option.series[4].data[index],
      }
    }, { axis, date, value })

    const marker = await chartInfo(2, '2025-03-17', 0.5)
    assert.ok(marker.withinViewport, `${theme} 图表横向溢出`)
    assert.deepEqual(marker.types, ['bar', 'line', 'line', 'scatter', 'scatter'])
    assert.equal(marker.average, 59)
    assert.equal(marker.release.count, 2)
    await page.mouse.move(marker.x, marker.y)
    await page.waitForFunction(() => [...document.querySelectorAll('[data-testid="commit-activity-chart"] div')].some((element) => element.textContent.includes('v1.9.0') && element.textContent.includes('v1.9.1')))
    await page.mouse.click(marker.x, marker.y)
    const list = await page.waitForSelector('[data-testid="activity-release-list"]', { visible: true })
    assert.match(await list.evaluate((element) => element.textContent), /2 次发布/)
    assert.ok(await list.evaluate((element) => {
      const rect = element.getBoundingClientRect()
      return element.contains(document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2))
    }), '发布列表被图表提示层遮挡')
    await page.evaluate(() => [...document.querySelectorAll('[data-testid="activity-release-list"] button')].find((button) => button.textContent.includes('v1.9.1')).click())
    await page.waitForFunction(() => document.querySelector('[role="dialog"]')?.textContent.includes('额外版本测试'))
    await page.keyboard.press('Escape')
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'))

    const bar = await chartInfo(0, '2025-03-17', 30)
    await page.mouse.click(bar.x, bar.y)
    await page.waitForFunction(() => document.querySelector('[role="dialog"]')?.textContent.includes('2025-03-17 · 60 次提交'))
    await page.keyboard.press('Escape')
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'))

    // 版本页继续使用同一详情入口，检查原有交互未受影响。
    await page.click('a[href="/repositories/grid-lite/releases"]')
    await page.waitForFunction(() => location.pathname.endsWith('/releases'))
    await page.waitForSelector('table tbody button')
    await page.evaluate(() => [...document.querySelectorAll('table tbody button')].find((button) => button.textContent.includes('v1.9.0')).click())
    await page.waitForFunction(() => document.querySelector('[role="dialog"]')?.textContent.includes('日历热力图'))
    await page.keyboard.press('Escape')
    await page.waitForFunction(() => !document.querySelector('[role="dialog"]'))

    await page.goto(new URL('/repositories/steady-core/overview', base).href, { waitUntil: 'networkidle0' })
    await page.waitForSelector('[data-testid="commit-activity-chart"] canvas')
    const partial = await chartInfo(0, '2025-03-17', 30)
    assert.equal(partial.average, null, '部分覆盖时不能生成完整周均值')
    assert.deepEqual(errors, [], `${theme} 页面出现脚本错误`)
    console.log(`${theme} ${width}px：悬浮提示、多版本选择、两处版本详情、Commit 明细与部分覆盖通过`)
    await context.close()
  }
} finally {
  await browser.close()
}
