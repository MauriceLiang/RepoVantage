import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import puppeteer from 'puppeteer-core'

const base = new URL(process.env.BASE_URL ?? 'http://127.0.0.1:8000')
assert.ok(['127.0.0.1', 'localhost'].includes(base.hostname), '测试只允许连接本地应用')
const chrome = process.env.CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../docs/research-v44/screenshots')
await mkdir(root, { recursive: true })

const browser = await puppeteer.launch({ executablePath: chrome, headless: true, args: process.platform === 'linux' ? ['--no-sandbox'] : [] })
const failures = []
const requests = []
try {
  const page = await browser.newPage()
  page.on('pageerror', (error) => failures.push(error.message))
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/browser/')) requests.push({ method: request.method(), path: new URL(request.url()).pathname })
  })
  await page.evaluateOnNewDocument(() => localStorage.setItem('repovantage-theme', 'dark'))

  for (const width of [1440, 1920]) {
    const height = width === 1440 ? 900 : 1080
    await page.setViewport({ width, height })
    const start = performance.now()
    await page.goto(new URL('/research', base), { waitUntil: 'networkidle0' })
    await page.waitForFunction(() => document.querySelector('.atlas-meta-row')?.textContent?.includes('300 个真实节点'))
    await page.waitForFunction(() => Boolean(document.querySelector('.research-g2-chart canvas, .research-g2-chart svg')))
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, `图谱在 ${width}px 横向溢出`)
    await page.screenshot({ path: resolve(root, `atlas-${width}x${height}.png`) })
    console.log(`atlas ${width}x${height}: route-to-visible-chart ${(performance.now() - start).toFixed(0)}ms; 300 nodes`)

    if (width === 1440) {
    const atlasCount = async () => Number.parseInt((await page.$eval('.atlas-count', (node) => node.textContent ?? '')).split('/')[0].trim(), 10)
    assert.equal(await atlasCount(), 300, '图谱默认显示全部真实仓库')
    const atlasMarker = await page.$eval('.research-g2-chart canvas', (canvas) => {
      const pixels = canvas.getContext('2d')?.getImageData(0, 0, canvas.width, canvas.height).data ?? new Uint8ClampedArray()
      const rect = canvas.getBoundingClientRect()
      for (let y = Math.floor(canvas.height * 0.12); y < canvas.height * 0.88; y += 1) {
        for (let x = Math.floor(canvas.width * 0.12); x < canvas.width * 0.88; x += 1) {
          const index = (y * canvas.width + x) * 4
          const [red, green, blue, alpha] = pixels.slice(index, index + 4)
          if (alpha > 220 && red > 50 && red < 110 && green > 150 && green < 220 && blue > 120 && blue < 200) {
            return { x: rect.left + x * rect.width / canvas.width, y: rect.top + y * rect.height / canvas.height }
          }
        }
      }
      return null
    })
    assert.ok(atlasMarker, '图谱应绘制可悬停的真实节点')
    await page.mouse.move(atlasMarker.x, atlasMarker.y)
    await page.waitForFunction(() => document.querySelector('.g2-tooltip')?.textContent?.includes('窗口开始 UTC'))
    const atlasTooltip = await page.$eval('.g2-tooltip', (node) => node.textContent ?? '')
    assert.match(atlasTooltip, /次 \/ 周|个 \/ 周/)
    assert.match(atlasTooltip, /Commit 覆盖|新开 PR 覆盖/)
    assert.match(atlasTooltip, /complete/)
    const atlasMode = await page.$('select[aria-label="研究视图"]')
    assert.ok(atlasMode)
    await atlasMode.select('activity-volatility')
    assert.match(await page.$eval('.atlas-view-description', (node) => node.textContent ?? ''), /总体标准差/)
    await page.waitForFunction(() => document.querySelector('.research-g2-chart')?.getAttribute('data-view')?.includes('波动'))
    await atlasMode.select('pr-trend')
    assert.match(await page.$eval('.atlas-view-description', (node) => node.textContent ?? ''), /最小二乘斜率.*线性轴/)
    await page.waitForFunction(() => document.querySelector('.research-g2-chart')?.getAttribute('data-view')?.includes('趋势斜率'))
    await atlasMode.select('activity-mean')
    await page.waitForFunction(() => document.querySelector('.research-g2-chart')?.getAttribute('data-view')?.includes('12 周周均'))

    const languageFilter = await page.$('select[aria-label="按语言筛选"]')
    const languageChoice = await page.$eval('select[aria-label="按语言筛选"]', (node) => node.options[1]?.value)
    assert.ok(languageFilter && languageChoice)
    await languageFilter.select(languageChoice)
    assert.ok(await atlasCount() < 300, '语言筛选应减少样本数量')
    await languageFilter.select('全部语言')

    const roleFilter = await page.$('select[aria-label="按样本角色筛选"]')
    const roleChoice = await page.$eval('select[aria-label="按样本角色筛选"]', (node) => node.options[1]?.value)
    assert.ok(roleFilter && roleChoice)
    await roleFilter.select(roleChoice)
    assert.ok(await atlasCount() < 300, '样本角色筛选应减少样本数量')
    await roleFilter.select('全部样本角色')

    await page.type('input[aria-label="最低周均 Commit"]', '0.1')
    await page.waitForFunction(() => Number.parseInt((document.querySelector('.atlas-count')?.textContent ?? '').split('/')[0].trim(), 10) < 300)
    assert.ok(await atlasCount() < 300, 'Commit 活动阈值应过滤低活动仓库')
    await page.click('.atlas-clear-filter')
    assert.equal(await atlasCount(), 300, '清除活动门槛后应恢复 300 个样本')

    const firstAtlasRow = await page.$('.atlas-list-row')
    assert.ok(firstAtlasRow)
    const firstAtlasRepository = await firstAtlasRow.$eval('strong', (node) => node.textContent)
    await firstAtlasRow.click()
    await page.waitForFunction((name) => document.querySelector('.atlas-repo-title strong')?.textContent === name, {}, firstAtlasRepository)
    await page.waitForSelector('.atlas-trend-panel canvas')

    const atlasCanvas = await page.$('.research-g2-chart canvas')
    const atlasCanvasBounds = await atlasCanvas?.boundingBox()
    assert.ok(atlasCanvasBounds)
    await new Promise((resolve) => setTimeout(resolve, 350))
    await page.mouse.move(atlasCanvasBounds.x + atlasCanvasBounds.width * 0.12, atlasCanvasBounds.y + atlasCanvasBounds.height * 0.12)
    await page.mouse.down()
    await page.mouse.move(atlasCanvasBounds.x + atlasCanvasBounds.width * 0.88, atlasCanvasBounds.y + atlasCanvasBounds.height * 0.88, { steps: 8 })
    await page.mouse.up()
    await page.waitForFunction(() => {
      const value = Number.parseInt((document.querySelector('.atlas-count')?.textContent ?? '').split('/')[0].trim(), 10)
      return value > 0 && value < 300
    })
    const brushedCount = await atlasCount()
    await page.mouse.click(atlasCanvasBounds.x + atlasCanvasBounds.width * 0.5, atlasCanvasBounds.y + atlasCanvasBounds.height * 0.5)
    await page.mouse.click(atlasCanvasBounds.x + atlasCanvasBounds.width * 0.5, atlasCanvasBounds.y + atlasCanvasBounds.height * 0.5, { delay: 120 })
    await page.waitForFunction(() => Number.parseInt((document.querySelector('.atlas-count')?.textContent ?? '').split('/')[0].trim(), 10) === 300)
    assert.ok(brushedCount < 300, '框选应过滤联动列表并缩放坐标范围')
    }

    const selectionStart = performance.now()
    await page.goto(new URL('/selection', base), { waitUntil: 'networkidle0' })
    await page.waitForSelector('.scenario-tabs button[aria-selected="true"]')
    await page.waitForFunction(() => document.querySelector('.data-count')?.textContent?.includes('3 个有效节点'))
    await page.waitForFunction(() => Boolean(document.querySelector('.decision-scatter canvas, .decision-scatter svg')))
    await page.waitForSelector('.parallel-panel canvas')
    console.log(`selection G1 ${width}x${height}: route-to-visible-chart ${(performance.now() - selectionStart).toFixed(0)}ms`)

    const rows = () => page.$$eval('.candidate-row', (items) => items.map((item) => item.textContent?.replace(/\s+/g, ' ').trim() ?? ''))
    const goRows = await rows()
    assert.equal(goRows.length, 4, 'G1 应保留四个候选')
    assert.ok(goRows.some((row) => row.includes('go-chi/chi') && row.includes('指标待采')), 'Chi 应为待采集并保持无可比指标')
    assert.match(await page.$eval('.capability-evidence-list', (node) => node.textContent ?? ''), /已证实支持/)
    const chartMarkers = await page.$eval('.decision-scatter canvas', (canvas) => {
      const pixels = canvas.getContext('2d')?.getImageData(0, 0, canvas.width, canvas.height).data ?? new Uint8ClampedArray()
      let orange = 0
      let greenX = 0
      let greenY = 0
      let greenCount = 0
      for (let index = 0; index < pixels.length; index += 4) {
        const pixel = index / 4
        const x = pixel % canvas.width
        const y = Math.floor(pixel / canvas.width)
        if (pixels[index] > 190 && pixels[index + 1] > 130 && pixels[index + 1] < 210 && pixels[index + 2] < 160) orange += 1
        if (y < canvas.height - 40 && pixels[index] > 65 && pixels[index] < 105 && pixels[index + 1] > 180 && pixels[index + 2] > 120 && pixels[index + 2] < 185) {
          greenX += x
          greenY += y
          greenCount += 1
        }
      }
      const rect = canvas.getBoundingClientRect()
      return {
        orange,
        greenCount,
        greenX: rect.left + (greenX / Math.max(greenCount, 1)) * rect.width / canvas.width,
        greenY: rect.top + (greenY / Math.max(greenCount, 1)) * rect.height / canvas.height,
      }
    })
    assert.ok(chartMarkers.orange > 80, 'Fiber 条件候选应绘制为可见的橙色菱形')
    assert.ok(chartMarkers.greenCount > 80, 'Echo 候选应绘制为可点击的绿色标记')
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, `G1 在 ${width}px 横向溢出`)
    await page.screenshot({ path: resolve(root, `selection-go-${width}x${height}.png`) })
    if (width === 1440) await page.screenshot({ path: resolve(root, 'selection-go-detail-1440x900.png') })

    const filters = await page.$$('.eligibility-control select')
    assert.equal(filters.length, 2, 'G1 应显示兼容约束与候选资格筛选')
    await filters[0].select('conditional')
    const filteredRows = await rows()
    assert.equal(filteredRows.length, 1, 'net/http 有条件状态筛选应只保留 Fiber')
    assert.ok(filteredRows[0].includes('gofiber/fiber'), 'net/http 有条件状态筛选应匹配 Fiber')
    await filters[0].select('all')

    const tabs = await page.$$('button[role="tab"]')
    assert.equal(tabs.length, 4, '目录应包含四个固定场景')
    const pythonTitle = await page.evaluate((node) => node.querySelector('span')?.textContent, tabs[1])
    await tabs[1].click()
    await page.waitForFunction((title) => document.querySelector('.scenario-brief h2')?.textContent === title, {}, pythonTitle)
    await page.waitForFunction(() => document.querySelector('.data-count')?.textContent?.includes('2 个有效节点'))
    const pythonRows = await rows()
    assert.equal(pythonRows.length, 3, 'G2 应显示两个历史候选和一个待采候选')
    assert.ok(pythonRows.some((row) => row.includes('litestar-org/litestar') && row.includes('指标待采')))
    if (width === 1440) {
      await page.evaluate(() => {
        const pending = [...document.querySelectorAll('.candidate-row')].find((node) => node.textContent?.includes('litestar-org/litestar'))
        pending?.scrollIntoView({ block: 'center' })
      })
      await page.screenshot({ path: resolve(root, 'selection-python-pending-1440x900.png') })
    }

    await tabs[0].click()
    await page.waitForFunction(() => document.querySelector('.scenario-brief h2')?.textContent === (document.querySelector('button[role="tab"] span')?.textContent ?? ''))
    await page.waitForFunction(() => document.querySelector('.data-count')?.textContent?.includes('3 个有效节点'))
    await page.mouse.click(chartMarkers.greenX, chartMarkers.greenY)
    await page.waitForFunction(() => document.querySelector('.candidate-title-line strong')?.textContent === 'labstack/echo')
    assert.equal(await page.$eval('.candidate-row[aria-pressed="true"] strong', (node) => node.textContent), 'labstack/echo', '点击图表标记应同步高亮列表与证据')
    const ginButton = await page.$('.candidate-row[aria-pressed="false"]')
    assert.ok(ginButton, 'G1 中应可选择其他候选')
    await ginButton.click()
    await page.waitForFunction(() => document.querySelector('.candidate-title-line strong')?.textContent === 'gin-gonic/gin')

    for (let index = 0; index < 20; index += 1) {
      const tabIndex = index % 4
      const expected = await page.$eval(`button[role="tab"]:nth-child(${tabIndex + 1}) span`, (node) => node.textContent)
      await page.click(`button[role="tab"]:nth-child(${tabIndex + 1})`)
      await page.waitForFunction((title) => document.querySelector('.scenario-brief h2')?.textContent === title, {}, expected)
      await page.waitForFunction(() => Boolean(document.querySelector('.candidate-title-line strong')))
      assert.equal(await page.$$eval('.decision-scatter canvas', (items) => items.length), 1, '多次切换场景后只保留一个 G2 实例')
    }
    for (const resizeWidth of [1440, 1600, 1920, 1680, 1440, 1920, 1600, 1440, 1920, 1440]) {
      await page.setViewport({ width: resizeWidth, height: resizeWidth === 1920 ? 1080 : 900 })
      await page.waitForFunction(() => document.querySelector('.decision-scatter canvas')?.width > 0)
    }
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, `多次 Resize 后 ${width}px 页面横向溢出`)
    assert.deepEqual(failures, [], '页面不应产生未捕获异常')
  }

  assert.ok(requests.length > 0, '页面应从正式 API 加载数据')
  assert.ok(requests.every((request) => request.method === 'GET'), '这些只读页面不应产生写请求')
  assert.ok(requests.some((request) => request.path.endsWith('/research/atlas')))
  assert.ok(requests.some((request) => request.path.endsWith('/selection/scenarios/go-http-api/viz')))
  assert.ok(!requests.some((request) => /github|crawl|collect/i.test(request.path)), '页面打开不得触发 GitHub 抓取')
  console.log(`browser checks passed; ${requests.length} browser API GETs; no writes or page errors`)
} finally {
  await browser.close()
}
