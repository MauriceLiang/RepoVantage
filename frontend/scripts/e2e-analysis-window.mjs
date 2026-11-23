import assert from 'node:assert/strict'
import { access, mkdir, mkdtemp, readFile, readdir, writeFile } from 'node:fs/promises'
import { constants } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import puppeteer from 'puppeteer-core'

const base = new URL(process.env.BASE_URL ?? 'http://127.0.0.1:5173')
const chrome = process.env.CHROME_PATH
assert.ok(chrome, '必须设置 CHROME_PATH，指向独立测试 Chromium 可执行文件')
await access(chrome, constants.X_OK).catch(() => { throw new Error(`CHROME_PATH 不存在或不可执行：${chrome}`) })
const artifacts = process.env.E2E_ARTIFACT_DIR ? resolve(process.env.E2E_ARTIFACT_DIR) : await mkdtemp(join(tmpdir(), 'repovantage-window-e2e-'))
await mkdir(artifacts, { recursive: true })
const report = {
  command: process.env.E2E_COMMAND ?? 'npm run test:e2e:analysis-window',
  baseUrl: base.href,
  dataMode: 'mock',
  scenarios: [],
  failures: [],
  notRun: ['真实后端浏览器模式与 Worker 联调', 'GitHub REST API（本次刻意不请求）', '正式 30 仓库冻结与数据包导入（待负责人批准）'],
  realGitHubApi: 'not_run',
}

function parseCsv(text) {
  const rows = []
  let row = [], cell = '', quoted = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (c === '"') {
      if (quoted && text[i + 1] === '"') { cell += '"'; i++ }
      else quoted = !quoted
    } else if (!quoted && (c === ',' || c === '\n')) {
      row.push(cell.replace(/\r$/, '')); cell = ''
      if (c === '\n') { rows.push(row); row = [] }
    } else cell += c
  }
  if (cell || row.length) { row.push(cell.replace(/\r$/, '')); rows.push(row) }
  const header = rows.shift().map((name) => name.replace(/^\ufeff/, ''))
  return rows.map((values) => Object.fromEntries(header.map((name, i) => [name, values[i]])))
}

let browser
try {
  browser = await puppeteer.launch({ executablePath: chrome, headless: true, args: process.platform === 'linux' ? ['--no-sandbox'] : [] })
  for (const theme of ['light', 'dark']) {
    const context = await browser.createBrowserContext()
    const page = await context.newPage()
    page.setDefaultTimeout(15000)
    await page.setViewport({ width: 1440, height: 1000 })
    await page.evaluateOnNewDocument((value) => {
      localStorage.setItem('repovantage-theme', value)
      localStorage.setItem('repovantage-analysis-window', '90')
    }, theme)
    const errors = [], apiRequests = []
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('request', (request) => {
      if (request.url().includes('/api/browser/') || request.url().startsWith('https://api.github.com/')) apiRequests.push(request.url())
    })
    const click = async (selector) => {
      await page.waitForSelector(selector, { visible: true })
      await page.click(selector)
    }
    const fetchDrawerOnline = async () => {
      await page.waitForFunction(() => [...document.querySelectorAll('[role="dialog"] button')].some((button) => button.textContent.trim() === '在线获取' && !button.disabled))
      await page.evaluate(() => [...document.querySelectorAll('[role="dialog"] button')].find((button) => button.textContent.trim() === '在线获取').click())
    }
    const closeDrawer = async () => {
      await page.keyboard.press('Escape')
      await page.waitForFunction(() => !document.querySelector('[role="dialog"]'))
    }
    const text = (selector) => page.$eval(selector, (element) => element.textContent ?? '')
    const select = async (group, value) => {
      const selector = `[data-testid="${group}"] button[data-value="${value}"]`
      await click(selector)
      await page.waitForFunction((s) => document.querySelector(s)?.getAttribute('aria-pressed') === 'true', {}, selector)
    }
    const loadedWindow = async (days) => page.waitForFunction((value) => {
      const element = document.querySelector('[data-testid="repository-analysis"]')
      return element?.getAttribute('data-window-days') === String(value)
        && Boolean(document.querySelector(value === 180 ? '[data-testid="analysis-window-unavailable"]' : '[data-testid="analysis-content"]'))
    }, {}, days)
    const layout = async (selector) => {
      const element = await page.waitForSelector(selector, { visible: true })
      await element.scrollIntoView()
      const result = await element.evaluate((node) => {
        const r = node.getBoundingClientRect()
        const top = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
        return { fits: r.x >= 0 && r.right <= innerWidth + 1 && r.y >= 0 && r.bottom <= innerHeight + 1, visible: Boolean(top && (node.contains(top) || top.contains(node))) }
      })
      assert.deepEqual(result, { fits: true, visible: true }, `${theme} 控件溢出或被遮挡：${selector}`)
    }
    const navigate = async (path) => { await click(`a[href="${path}"]`); await page.waitForFunction((p) => location.pathname === p, {}, path) }

    await page.goto(new URL('/repositories/steady-core/overview', base).href, { waitUntil: 'networkidle0' })
    assert.equal(await page.$eval('[data-testid="app"]', (element) => element.getAttribute('data-mode')), 'mock', '必须使用 VITE_DATA_MODE=mock 的独立服务器')
    assert.equal(await page.evaluate(() => document.documentElement.classList.contains('dark')), theme === 'dark')
    for (const days of [30, 90, 180]) {
      await select('analysis-window', days)
      await loadedWindow(days)
      assert.match(await text('[data-testid="analysis-window-summary"]'), new RegExp(`${days} 天`))
      if (days === 180) {
        assert.equal(await page.$('[data-testid="analysis-content"]'), null, '180 天缺失时不能继续展示 90 天图表')
        assert.match(await text('[data-testid="analysis-window-unavailable"]'), /180 天/)
      }
    }
    for (const [mode, label] of [['quick', '快速采集'], ['window', '完整窗口采集']]) {
      await select('collection-mode', mode)
      assert.ok((await text('[data-testid="collect-repository"]')).includes(`${label} · 180 天`))
      assert.match(await text('[data-testid="collection-description"]'), mode === 'quick' ? /页数预算/ : /全部分页/)
    }
    await navigate('/tasks')
    await page.waitForSelector('[data-testid="task-row"]')
    assert.equal((await page.$$('[data-task-id^="mock-refresh-"]')).length, 0, '切换窗口和模式不得自动创建任务')
    assert.equal(await page.$('[data-task-id="mock-featured-failed"]'), null, '已停用的 15 仓库精选导入不应出现在任务演示中')
    assert.match(await text('[data-task-id="t4"]'), /GitHub API 速率限制/, '失败与限流原因应保留在任务记录中')
    assert.match(await text('[data-task-id="t3"]'), /部分完成/, '数据不足/部分完成状态应可见')
    await click('[data-task-id="t4"] button')
    const retriedTask = await page.waitForSelector('[data-task-id^="mock-retry-"]')
    assert.match(await retriedTask.evaluate((element) => element.textContent ?? ''), /排队中.*等待 Worker 重新执行/s, '重试后应出现新的排队任务')
    await navigate('/repositories')
    assert.doesNotMatch(await page.$eval('body', (element) => element.textContent ?? ''), /最多加载 100 个/)
    assert.doesNotMatch(await page.$eval('body', (element) => element.textContent ?? ''), /导入精选仓库|下载数据包/)
    await page.goto(new URL('/repositories/steady-core/overview', base).href, { waitUntil: 'networkidle0' })
    const days = theme === 'light' ? 180 : 30
    const mode = theme === 'light' ? 'window' : 'quick'
    await select('analysis-window', days)
    await loadedWindow(days)
    await select('collection-mode', mode)
    for (const selector of ['[data-testid="analysis-window"]', '[data-testid="collection-mode"]', '[data-testid="collect-repository"]']) await layout(selector)
    await click('[data-testid="collect-repository"]')
    await page.waitForSelector(`[data-task-id^="mock-refresh-"][data-scope-kind="${mode}"][data-window-days="${days}"]`)
    assert.equal((await page.$$('[data-task-id^="mock-refresh-"]')).length, 1)
    assert.match(await text('[data-task-id^="mock-refresh-"]'), new RegExp(`${days} 天`))

    await navigate('/repositories')
    for (const id of ['steady-core', 'grid-lite']) await click(`[data-testid="repository-select"][data-repository-id="${id}"]`)
    await click('[data-testid="compare-selected"]')
    for (const selected of [30, 90, 180]) {
      await select('comparison-window', selected)
      await page.waitForFunction((value) => {
        const element = document.querySelector('[data-testid="comparison-description"]')
        return element?.getAttribute('data-window-days') === String(value) && element.getAttribute('aria-busy') === 'false'
      }, {}, selected)
      assert.equal((await page.$$('[data-testid="comparison-row"]')).length, 2)
      if (selected === 180) {
        assert.equal((await page.$$('[data-testid="comparison-window-unavailable"]')).length, 2)
        assert.equal((await page.$$('[data-testid="comparison-row"][data-window-available="false"]')).length, 2)
      }
    }
    await select('comparison-window', 90)
    await page.waitForFunction(() => document.querySelector('[data-testid="comparison-description"]')?.getAttribute('aria-busy') === 'false')
    await select('comparison-mode', 'same_period')
    await page.waitForFunction(() => document.querySelector('[data-testid="comparison-basis"]')?.getAttribute('data-status') === 'comparable')
    assert.match(await text('[data-testid="comparison-basis"]'), /交集 .* 天 \/ 最低 .* 天/)
    await select('comparison-mode', 'individual_periods')
    await page.waitForFunction(() => document.querySelector('[data-testid="comparison-description"]')?.getAttribute('data-mode') === 'individual_periods')
    assert.equal(await page.$eval('[data-testid="comparison-window"] button[aria-pressed="true"]', (element) => element.getAttribute('data-value')), '90')

    const session = await page.createCDPSession()
    for (const selected of [30, 180]) {
      await select('comparison-window', selected)
      await page.waitForFunction((value) => document.querySelector('[data-testid="comparison-description"]')?.getAttribute('data-window-days') === String(value), {}, selected)
      const dir = await mkdtemp(join(artifacts, `${theme}-${selected}-download-`))
      await session.send('Browser.setDownloadBehavior', { behavior: 'allow', browserContextId: context.id, downloadPath: dir })
      await click('[data-testid="export-comparison"]')
      let file
      for (let attempt = 0; attempt < 100 && !file; attempt++) {
        file = (await readdir(dir)).find((name) => name.endsWith('.csv'))
        if (!file) await delay(100)
      }
      assert.ok(file, '未下载到比较 CSV')
      const rows = parseCsv(await readFile(join(dir, file), 'utf8'))
      assert.equal(rows.length, 2)
      const uiRows = await page.$$eval('[data-testid="comparison-row"]', (elements) => elements.map((element) => [...element.querySelectorAll('td')].map((cell) => cell.textContent.trim())))
      for (let index = 0; index < rows.length; index++) {
        const row = rows[index], cells = uiRows[index]
        assert.equal(row.window_days, String(selected))
        assert.equal(row.comparison_mode, 'individual_periods')
        assert.equal(row.repository, cells[0])
        assert.equal(row.issue_p50_days === '' ? '—' : `${row.issue_p50_days} 天`, cells[2])
        assert.equal(row.pr_p50_days === '' ? '—' : `${row.pr_p50_days} 天`, cells[3])
        if (selected === 180) {
          assert.equal(row.window_available, 'false')
          assert.match(row.window_reason, /180 天/)
          assert.equal(row.weekly_commit_mean, '')
          assert.equal(cells[1], '—')
        } else if (row.weekly_commit_mean !== '') {
          assert.equal(Math.round(Number(row.weekly_commit_mean) * Number(row.complete_weeks)), Number(cells[1].replaceAll(',', '')))
        }
      }
    }

    if (theme === 'light') {
      await navigate('/research')
      await page.waitForSelector('[data-testid="research-atlas-error"]')
      assert.match(await text('[data-testid="research-atlas-error"]'), /研究图谱暂不可用/, '缺少真实课程数据时应明确显示 API 错误')
      assert.equal(await page.$('.research-g2-chart'), null, '没有真实标准样本时不应绘制图谱')
      assert.equal(await page.$('.atlas-meta-row'), null, '没有真实标准样本时不应显示数据摘要')
      const repositoryPages = await page.evaluate(async () => {
        const { HttpRepositoryDataSource } = await import('/src/services/httpRepositoryDataSource.ts')
        const originalFetch = window.fetch
        const requestedPages = []
        window.fetch = async (input) => {
          const url = new URL(String(input), location.origin)
          if (url.pathname === '/api/browser/session') {
            return new Response(JSON.stringify({ csrf_token: 'test-token' }), { headers: { 'content-type': 'application/json' } })
          }
          const pageNumber = Number(url.searchParams.get('page'))
          requestedPages.push(pageNumber)
          const start = (pageNumber - 1) * 100
          const items = Array.from({ length: Math.min(100, 150 - start) }, (_, offset) => {
            const repositoryId = start + offset + 1
            return { repository_id: repositoryId, full_name: `standard/repository-${repositoryId}`, analysis_status: 'not_started' }
          })
          return new Response(JSON.stringify({
            data: { items },
            meta: { pagination: { page: pageNumber, per_page: 100, total: 150, has_next: pageNumber * 100 < 150 } },
          }), { headers: { 'content-type': 'application/json' } })
        }
        try {
          const items = await new HttpRepositoryDataSource().listRepositories()
          return { count: items.length, firstId: items[0]?.id, lastId: items.at(-1)?.id, pages: requestedPages }
        } finally {
          window.fetch = originalFetch
        }
      })
      assert.deepEqual(repositoryPages, { count: 150, firstId: '1', lastId: '150', pages: [1, 2] }, '仓库列表需读取全部分页，不得截断在 100 个')
      await navigate('/compare')
    }

    await layout('[data-testid="comparison-window"]')
    await layout('[data-testid="comparison-window-unavailable"]')
    await page.screenshot({ path: join(artifacts, `${theme}-comparison.png`) })

    for (const [tab, author] of [['issues', 'demo-bot'], ['prs', 'demo-reviewer']]) {
      await page.goto(new URL(`/repositories/grid-lite/${tab}`, base).href, { waitUntil: 'networkidle0' })
      await select('analysis-window', 90)
      await loadedWindow(90)
      await click('tbody button')
      await fetchDrawerOnline()
      await page.waitForFunction((name) => document.querySelector('[role="dialog"]')?.textContent?.includes(name), {}, author)
      assert.match(await text('[role="dialog"]'), /演示模式：以下为示例数据，没有连接 GitHub。/)
      assert.doesNotMatch(await text('[role="dialog"]'), /已从 GitHub 获取最新/)
    }

    if (theme === 'light') {
      await page.goto(new URL('/repositories/grid-lite/issues', base).href, { waitUntil: 'networkidle0' })
      await select('analysis-window', 90)
      await loadedWindow(90)
      await page.evaluate(async () => {
        const { MockRepositoryDataSource } = await import('/src/services/mockRepositoryDataSource.ts')
        const original = MockRepositoryDataSource.prototype.getIssueOnlineDetail
        MockRepositoryDataSource.prototype.getIssueOnlineDetail = function (id, number) {
          if (number !== 482) return original.call(this, id, number)
          return new Promise((resolve) => {
            window.resolveOldIssue = () => original.call(this, id, number).then(resolve)
          })
        }
      })
      await click('tbody tr:nth-child(1) button')
      await fetchDrawerOnline()
      await page.waitForFunction(() => typeof window.resolveOldIssue === 'function')
      await closeDrawer()
      await click('tbody tr:nth-child(2) button')
      await fetchDrawerOnline()
      await page.waitForFunction(() => document.querySelector('[role="dialog"]')?.textContent?.includes('demo-bot'))
      await page.evaluate(() => window.resolveOldIssue())
      assert.match(await text('[role="dialog"]'), /Issue #481/)
      assert.match(await text('[role="dialog"]'), /Issue 关闭耗时缺少 P90 标注/)

      await closeDrawer()
      await page.evaluate(async () => {
        const { MockRepositoryDataSource } = await import('/src/services/mockRepositoryDataSource.ts')
        MockRepositoryDataSource.prototype.getIssueOnlineDetail = async () => { throw new Error('模拟在线请求失败') }
      })
      await click('tbody tr:nth-child(1) button')
      await fetchDrawerOnline()
      await page.waitForFunction(() => document.querySelector('[role="dialog"] [role="alert"]')?.textContent?.includes('模拟在线请求失败'))
      assert.match(await text('[role="dialog"]'), /这是用于界面预览的示例 Issue 描述/)

      await closeDrawer()
      await page.evaluate(async () => {
        const { MockRepositoryDataSource } = await import('/src/services/mockRepositoryDataSource.ts')
        MockRepositoryDataSource.prototype.getIssueOnlineDetail = (_id, number) => new Promise((resolve) => {
          window.resolveCrossIssue = () => resolve({ number, title: '过期 Issue', body: '', state: 'closed', author: null, labels: [], createdAt: null, closedAt: null, updatedAt: null, commentsCount: 0, comments: [], commentsComplete: true, commentsError: null, source: 'mock' })
        })
      })
      await click('tbody tr:nth-child(1) button')
      await fetchDrawerOnline()
      await page.waitForFunction(() => typeof window.resolveCrossIssue === 'function')
      await closeDrawer()
      await navigate('/repositories/grid-lite/prs')
      await click('tbody tr:nth-child(1) button')
      await fetchDrawerOnline()
      await page.waitForFunction(() => document.querySelector('[role="dialog"]')?.textContent?.includes('demo-reviewer'))
      await page.evaluate(async () => { window.resolveCrossIssue(); await new Promise((resolve) => setTimeout(resolve, 0)) })
      assert.match(await text('[role="dialog"]'), /Pull Request #299/)
      assert.doesNotMatch(await text('[role="dialog"]'), /过期 Issue/)

      await closeDrawer()
      await page.evaluate(async () => {
        const { MockRepositoryDataSource } = await import('/src/services/mockRepositoryDataSource.ts')
        MockRepositoryDataSource.prototype.getPullRequestOnlineDetail = async () => { throw new Error('模拟 PR 请求失败') }
      })
      await click('tbody tr:nth-child(1) button')
      await fetchDrawerOnline()
      await page.waitForFunction(() => document.querySelector('[role="dialog"] [role="alert"]')?.textContent?.includes('模拟 PR 请求失败'))
      assert.match(await text('[role="dialog"]'), /这是用于界面预览的示例 Pull Request/)
    }

    await page.setViewport({ width: 390, height: 844 })
    await page.goto(new URL('/repositories/steady-core/overview', base).href, { waitUntil: 'networkidle0' })
    await select('analysis-window', 180)
    await loadedWindow(180)
    for (const selector of ['[data-testid="analysis-window"]', '[data-testid="collect-repository"]', '[data-testid="analysis-window-unavailable"]']) await layout(selector)
    await page.screenshot({ path: join(artifacts, `${theme}-mobile.png`) })
    assert.deepEqual(apiRequests, [], 'Mock smoke 不应访问后端或真实 GitHub API')
    assert.deepEqual(errors, [], '浏览器出现未处理错误')
    report.scenarios.push({ theme, status: 'passed', collectionMode: mode, collectionDays: days, checks: ['analysis-windows', 'no-automatic-task', 'collection-scope', 'comparison-windows', 'mode-preserves-window', 'csv-30-180', 'insufficient-data-visible', 'failure-and-rate-limit-visible', 'retry-requeues-task', 'mock-issue-pr-comments', ...(theme === 'light' ? ['drawer-stale-response', 'drawer-online-error', 'standard-test-default', 'repository-pagination-150', 'featured-sample-retired', 'research-default-dataset'] : []), 'layout-desktop-mobile'] })
    await context.close()
    console.log(`PASS ${theme}: analysis, collection, comparison, CSV, layout`)
  }
} catch (error) {
  report.failures.push(error instanceof Error ? error.message : String(error))
  throw error
} finally {
  await writeFile(join(artifacts, 'report.json'), JSON.stringify(report, null, 2) + '\n')
  await browser?.close()
  console.log(`Artifacts: ${artifacts}`)
}
