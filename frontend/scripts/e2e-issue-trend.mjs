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
      // 仅使用本机演示服务，不请求 GitHub 或其他外部资源。
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

    // 用覆盖完整、部分覆盖和缺失周验证同一图中的柱形、折线及面积带。
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
      await page.click(`[data-testid="analysis-window"] button[data-value="${days}"]`)
      await page.waitForFunction((value) => document.querySelector('[data-testid="repository-analysis"]')?.getAttribute('data-window-days') === String(value), {}, days)
      await page.waitForSelector('[data-testid="issue-trend-chart"] canvas')
    }

    const chartInfo = () => page.evaluate(async () => {
      const element = document.querySelector('[data-testid="issue-trend-chart"]')
      element.scrollIntoView({ block: 'center' })
      const core = performance.getEntriesByType('resource').map((entry) => entry.name).find((name) => name.includes('echarts_core'))
      const chart = (await import(core)).getInstanceByDom(element)
      const option = chart.getOption()
      const index = option.xAxis[0].data.indexOf('2025-01-27')
      const pixel = chart.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [index, 1])
      const rect = element.getBoundingClientRect()
      return {
        x: rect.x + pixel[0], y: rect.y + pixel[1], left: rect.x, top: rect.y,
        withinViewport: rect.left >= 0 && rect.right <= innerWidth + 1,
        grids: option.grid.length, xAxes: option.xAxis.length, yAxes: option.yAxis.length,
        dates: option.xAxis[0].data, types: option.series.map((series) => series.type),
        segments: option.series[0].data, added: option.series[1].data, closed: option.series[2].data,
        difference: option.series[3].data, selected: option.legend[0].selected,
      }
    })

    const chart = await chartInfo()
    assert.ok(chart.withinViewport, `${theme} 图表横向溢出`)
    assert.deepEqual([chart.grids, chart.xAxes, chart.yAxes], [1, 1, 1], '组合图应使用同一个绘图区和坐标系')
    assert.deepEqual(chart.types, ['custom', 'bar', 'bar', 'line'])
    assert.deepEqual(chart.difference, [3, -3, 0, null, null, null, 0])
    assert.deepEqual(chart.segments, [[0, 3, -3], [1, -3, 0]], '面积只连接相邻完整周')
    assert.equal(chart.added[3].value, 2)
    assert.equal(chart.added[3].itemStyle.opacity, 0.5)
    assert.equal(chart.closed[3].value, null)
    assert.equal(chart.dates[5], '2025-02-10')
    await page.mouse.move(chart.x, chart.y)
    await page.waitForFunction(() => [...document.querySelectorAll('[data-testid="issue-trend-chart"] div')].some((element) => element.textContent.includes('2 个（已观察）') && element.textContent.includes('—（覆盖不完整）')))

    await page.mouse.click(chart.left + 175, chart.top + 10)
    await page.waitForFunction(async () => {
      const element = document.querySelector('[data-testid="issue-trend-chart"]')
      const core = performance.getEntriesByType('resource').map((entry) => entry.name).find((name) => name.includes('echarts_core'))
      const option = (await import(core)).getInstanceByDom(element).getOption()
      return option.legend[0].selected['新增 − 关闭'] === false
    })
    assert.deepEqual(errors, [], `${theme} 页面出现脚本错误`)
    console.log(`${theme} ${width}px：同图组合、正负差值、部分覆盖、悬浮与图例切换通过`)
    await context.close()
  }
} finally {
  await browser.close()
}
