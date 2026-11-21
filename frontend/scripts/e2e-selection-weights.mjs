import assert from 'node:assert/strict'
import { setTimeout as delay } from 'node:timers/promises'
import puppeteer from 'puppeteer-core'

const base = process.env.BASE_URL ?? 'http://127.0.0.1:5173'
const chrome = process.env.CHROME_PATH
assert.ok(chrome, '必须设置 CHROME_PATH，指向 Chromium 可执行文件')

const browser = await puppeteer.launch({ executablePath: chrome, headless: true, args: process.platform === 'linux' ? ['--no-sandbox'] : [] })
try {
  const page = await browser.newPage()
  const pageErrors = []
  const externalRequests = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  page.on('request', (request) => {
    if (request.url().startsWith('https://api.github.com/')) externalRequests.push(request.url())
  })
  await page.setViewport({ width: 1440, height: 900 })
  await page.evaluateOnNewDocument(() => localStorage.setItem('repovantage-theme', 'light'))
  await page.goto(new URL('/repositories', base).href, { waitUntil: 'networkidle0' })
  assert.equal(await page.$eval('[data-testid="app"]', (element) => element.getAttribute('data-mode')), 'mock')
  assert.equal(await page.$eval('nav[aria-label="主要导航"]', (nav) => nav.textContent?.includes('项目比较') ?? false), false, '项目比较不应作为独立侧栏入口')

  await page.evaluate(async () => {
    const { MockRepositoryDataSource } = await import('/src/services/mockRepositoryDataSource.ts')
    window.__selectionCalls = []
    window.__selectionInputs = []
    window.__selectionAllNeutral = false
    window.__selectionOwnWindow = false
    window.__selectionInsufficient = false
    window.__nextSelectionDelay = 0
    MockRepositoryDataSource.prototype.getSelection = async function (input) {
      const captured = { ...input, weights: { ...input.weights }, repositoryIds: [...input.repositoryIds] }
      window.__selectionCalls.push({ ...input.weights })
      window.__selectionInputs.push(captured)
      const delayMs = window.__nextSelectionDelay
      window.__nextSelectionDelay = 0
      if (delayMs) await new Promise((resolve) => setTimeout(resolve, delayMs))

      const active = Object.entries(input.weights).filter(([, weight]) => weight > 0)
      const totalWeight = active.reduce((sum, [, weight]) => sum + weight, 0)
      const neutralAll = window.__selectionAllNeutral
      const ranking = input.repositoryIds.map((id, index) => {
        const baseScore = index === 0 ? 0.8 : 0.4
        const evidence = active.map(([metric, weight], metricIndex) => {
          const isNeutral = neutralAll || (id === 'grid-lite' && metric === 'issue_median_hours')
          const normalized = isNeutral ? 0.5 : baseScore
          const partial = id === 'steady-core' && metric === 'pr_median_hours'
          return {
            metric,
            value: isNeutral ? null : 4 + metricIndex,
            unit: metric.includes('hours') ? '小时' : metric.includes('days') ? '天' : '次/周',
            normalized,
            weight: weight / totalWeight,
            contribution: normalized * weight / totalWeight * 100,
            validSamples: isNeutral ? 0 : metric === 'issue_median_hours' ? 44 : 12,
            quality: isNeutral ? 'missing' : partial ? 'partial' : 'ready',
            windowStart: isNeutral ? null : '2026-01-01',
            windowEnd: isNeutral ? null : '2026-04-01',
            sourceRunId: isNeutral ? null : `mock-${id}`,
            sourceKind: isNeutral ? null : 'online_event_analysis',
            missingPolicy: isNeutral ? 'neutral_50' : 'observed',
          }
        })
        return { id, name: `${id}/test-repo`, score: evidence.reduce((sum, item) => sum + item.contribution, 0), evidence }
      })
      return {
        status: window.__selectionInsufficient ? 'insufficient_data' : 'available',
        scoringVersion: 'weighted-relative-v2',
        weights: Object.fromEntries(active.map(([metric, weight]) => [metric, weight / totalWeight])),
        sharedWindow: window.__selectionOwnWindow ? null : { start: '2026-01-01T00:00:00Z', end: '2026-04-01T00:00:00Z' },
        ranking: window.__selectionInsufficient ? [] : ranking.sort((left, right) => right.score - left.score || left.name.localeCompare(right.name)),
        excluded: window.__selectionInsufficient ? [{ id: 'grid-lite', name: 'grid-lite/test-repo', reasons: ['测试排除原因'] }] : [],
        sensitivity: [{ criterion: 'commits_weekly_mean', repositoryIds: ['steady-core'] }],
        maintenance: {
          commonWindow: null,
          dataAsOf: null,
          repositories: input.repositoryIds.map((repositoryId) => ({
            id: repositoryId,
            name: `${repositoryId}/test-repo`,
            sampleRole: null,
            pattern: {
              status: 'insufficient_data', method: 'none', reasonCode: 'not_collected', modelId: null, modelVersion: null,
              featureSchemaVersion: null, patternId: null, patternName: null, displayName: null, asOf: null, historyStart: null,
              sourceRunId: null, sourceSha256: null, collectedAt: null, coverage: {}, windowWeeks: 0, evidence: {}, limitations: [],
            },
            recentActivityChange: {
              status: 'insufficient_data', method: 'factual', reasonCode: 'short_history', previous4wCommits: null, recent4wCommits: null,
              changeCount: null, threshold: null, trend: null, previousWindowStart: null, previousWindowEndExclusive: null,
              recentWindowStart: null, recentWindowEndExclusive: null, notes: [],
            },
            activityTrend: {
              status: 'insufficient_data', method: 'none', trend: null, modelId: null, modelVersion: null, horizonWeeks: 4,
              probabilities: null, reasonCode: 'insufficient_data', evidence: {}, notes: [],
            },
          })),
        },
        notes: ['浏览器交互测试替身，不是实际分析结果。'],
        reportMarkdown: '# 测试报告',
        resultSignature: 'test-signature',
      }
    }
  })

  for (const id of ['steady-core', 'grid-lite', 'sparse-kit', 'tiny-lab', 'docs-site']) {
    const selector = `[data-testid="repository-select"][data-repository-id="${id}"]`
    await page.waitForSelector(selector)
    await page.click(selector)
  }
  await page.waitForSelector('[data-testid="compare-selected"]:not([disabled])')
  await page.click('[data-testid="compare-selected"]')
  await page.waitForSelector('[data-testid="selection-report"]')
  assert.ok(page.url().endsWith('/compare'), '从仓库选择后应进入项目比较')
  assert.equal(await page.$eval('nav[aria-label="主要导航"] .nav-link--active', (link) => link.textContent?.trim()), '仓库', '项目比较页应保持仓库导航上下文')
  assert.deepEqual(await page.$eval('.breadcrumb-link', (link) => ({ label: link.textContent?.trim(), path: new URL(link.href).pathname })), { label: '仓库', path: '/repositories' })
  await page.waitForFunction(() => [...document.querySelectorAll('[data-testid^="weight-slider-"]')].some((input) => !input.disabled))
  await page.waitForSelector('[data-testid^="selection-score-"]')

  const initial = await page.evaluate(() => ({
    active: [...document.querySelectorAll('[data-testid^="weight-slider-"]')].filter((input) => Number(input.value) > 0).length,
    available: [...document.querySelectorAll('[data-testid^="weight-slider-"]')].filter((input) => !input.disabled).length,
    sliderTotal: [...document.querySelectorAll('[data-testid^="weight-slider-"]')].reduce((sum, input) => sum + Number(input.value), 0),
    scoreCount: document.querySelectorAll('table[aria-label="仓库综合评分排名"] tbody > tr[data-testid^="selection-score-"]').length,
    scoreText: document.querySelector('table[aria-label="仓库综合评分排名"] tbody > tr[data-testid^="selection-score-"]').textContent,
    selectionInput: window.__selectionInputs[0],
    preciseInputCount: [...document.querySelectorAll('[data-testid="selection-report"] input[type="text"]')].length,
    donutVisible: Boolean(document.querySelector('[data-testid="weight-donut"]')),
    manualPanelVisible: Boolean(document.querySelector('[data-testid="manual-weight-toggle"], [data-testid="manual-weight-editor"]')),
    explanationVisible: Boolean(document.querySelector('[data-testid="selection-scoring-explanation"]')),
    maintenanceVisible: Boolean(document.querySelector('[data-testid="selection-maintenance"]')),
    sampleSourceCount: [...document.querySelectorAll('[data-testid^="selection-score-"] summary')].filter((summary) => summary.textContent.includes('样本与来源')).length,
    calls: window.__selectionCalls.length,
    requestWeights: window.__selectionCalls[0],
    viewportWidth: innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    reportHeight: Math.round(document.querySelector('[data-testid="selection-report"]').getBoundingClientRect().height),
  }))
  assert.ok(initial.calls >= 1, '默认权重应自动生成比较')
  assert.equal(initial.active, 4)
  assert.equal(initial.available, 4)
  assert.equal(initial.scoreCount, 5)
  assert.match(initial.scoreText, /80\.0/)
  assert.equal(initial.selectionInput.scenario, '自定义权重对比')
  assert.equal(initial.selectionInput.candidateGroup, '当前所选仓库')
  assert.equal(initial.selectionInput.candidatesConfirmed, true)
  assert.deepEqual(initial.selectionInput.allowedLanguages, [])
  assert.deepEqual(initial.selectionInput.allowedLicenses, [])
  assert.equal(initial.preciseInputCount, 4, '四项指标均应提供常驻精确输入')
  assert.equal(initial.donutVisible, false, '权重环图应移除')
  assert.equal(initial.manualPanelVisible, false, '不应保留额外手动输入面板')
  assert.equal(initial.explanationVisible, true)
  assert.equal(initial.maintenanceVisible, true, '近期维护证据没有保留')
  assert.equal(initial.sampleSourceCount, 0, '默认视图不应展开样本与来源详情')
  assert.ok(Math.abs(initial.sliderTotal - 100) < 0.005, `初始权重未合计为 100%：${initial.sliderTotal}`)
  assert.ok(Math.abs(Object.values(initial.requestWeights).reduce((sum, weight) => sum + weight, 0) - 10) < 0.005, '初始 API 权重应合计为 10')
  assert.ok(initial.reportHeight <= 650, `改造后的默认评分区过高：${initial.reportHeight}px`)
  assert.ok(initial.documentWidth <= initial.viewportWidth + 1, `桌面页面发生横向溢出：${initial.documentWidth}/${initial.viewportWidth}`)

  const scaleCompatibility = await page.evaluate(async () => {
    const originalFetch = window.fetch
    let requestBody
    let replyIndex = 0
    const evidence = (contribution) => ({ value: 1, unit: '次/周', normalized: 0.6, weight: 0.5, contribution, valid_samples: 10, window_start: '2026-01-01', window_end: '2026-04-01', source_run_id: 'fixture', source_kind: 'online_event_analysis', quality: 'ready', missing_policy: 'observed' })
    const replies = [
      ['weighted-relative-v1', 0.7, [0.3, 0.4]],
      ['weighted-relative-v2', 70, [30, 40]],
    ].map(([version, score, contributions]) => ({ data: {
      status: 'available', scoring_version: version,
      weights: { commits_weekly_mean: 0.5, pr_median_hours: 0.5 },
      comparison_basis: { shared_window: { start: '2026-01-01T00:00:00Z', end: '2026-04-01T00:00:00Z' } },
      ranking: [{ repository_id: 1, full_name: 'fixture/score', score, evidence: {
        commits_weekly_mean: evidence(contributions[0]),
        pr_median_hours: { ...evidence(contributions[1]), normalized: 0.8, unit: '小时' },
      } }],
      excluded: [], sensitivity: [], maintenance: { common_window: null, data_as_of: null, repositories: [] },
      notes: [], report_markdown: '', result_signature: 'fixture',
    } }))
    window.fetch = async (input, init) => {
      const url = typeof input === 'string' ? input : input.url
      if (url === '/api/browser/session') return new Response(JSON.stringify({ csrf_token: 'test-token' }), { headers: { 'content-type': 'application/json' } })
      if (url === '/api/browser/v1/comparisons/selection') {
        requestBody = JSON.parse(init.body)
        return new Response(JSON.stringify(replies[replyIndex++]), { headers: { 'content-type': 'application/json' } })
      }
      return originalFetch(input, init)
    }
    try {
      const { HttpRepositoryDataSource } = await import('/src/services/httpRepositoryDataSource.ts')
      const source = new HttpRepositoryDataSource()
      const input = {
        repositoryIds: ['1', '2'], scenario: '自定义权重对比', candidateGroup: '当前所选仓库', candidatesConfirmed: true,
        windowDays: 90, allowedLanguages: [], allowedLicenses: [],
        weights: { commits_weekly_mean: 1, issue_median_hours: 0, pr_median_hours: 1, release_interval_days: 0 },
      }
      const legacy = await source.getSelection(input)
      const current = await source.getSelection(input)
      return {
        requestBody,
        legacy: { version: legacy.scoringVersion, score: legacy.ranking[0].score, contributions: legacy.ranking[0].evidence.map((item) => item.contribution) },
        current: { version: current.scoringVersion, score: current.ranking[0].score, contributions: current.ranking[0].evidence.map((item) => item.contribution) },
      }
    } finally { window.fetch = originalFetch }
  })
  assert.equal(scaleCompatibility.legacy.score, 70, '旧版 0–1 综合分没有转换为百分制')
  assert.deepEqual(scaleCompatibility.legacy.contributions, [30, 40], '旧版单项贡献没有转换为百分制')
  assert.equal(scaleCompatibility.current.score, 70, '新版百分制分数不应再次缩放')
  assert.deepEqual(scaleCompatibility.current.contributions, [30, 40], '新版百分制贡献不应再次缩放')
  assert.deepEqual(scaleCompatibility.requestBody.repository_ids, [1, 2])
  assert.equal(scaleCompatibility.requestBody.candidates_confirmed, true)
  assert.equal(scaleCompatibility.requestBody.scenario, '自定义权重对比')

  const dragSlider = await page.$('[data-testid="weight-slider-commits_weekly_mean"]')
  const previousDragCalls = await page.evaluate(() => window.__selectionCalls.length)
  await page.evaluate(() => { window.__nextSelectionDelay = 600 })
  const dragBox = await dragSlider.boundingBox()
  const startX = dragBox.x + dragBox.width * 0.25
  const endX = dragBox.x + dragBox.width * 0.5973
  const centerY = dragBox.y + dragBox.height / 2
  await page.mouse.move(startX, centerY)
  await page.mouse.down()
  await page.mouse.move(endX, centerY, { steps: 12 })
  await page.mouse.up()
  await page.waitForFunction((count) => window.__selectionCalls.length > count, {}, previousDragCalls)
  const duringUpdate = await page.evaluate(() => ({
    rowCount: document.querySelectorAll('table[aria-label="仓库综合评分排名"] tbody > tr[data-testid^="selection-score-"]').length,
    busy: document.querySelector('[data-testid="selection-result"]').getAttribute('aria-busy'),
    status: document.querySelector('[aria-labelledby="comparison-ranking-title"]').textContent,
    sliderValue: Number(document.querySelector('[data-testid="weight-slider-commits_weekly_mean"]').value),
    weights: window.__selectionCalls.at(-1),
  }))
  assert.equal(duringUpdate.rowCount, 5, '刷新权重时旧排名应继续展示')
  assert.equal(duringUpdate.busy, 'true')
  assert.match(duringUpdate.status, /更新中/)
  assert.ok(Math.abs(Object.values(duringUpdate.weights).reduce((sum, weight) => sum + weight, 0) - 10) < 0.005)
  await page.waitForFunction(() => document.querySelector('[data-testid="selection-result"]')?.getAttribute('aria-busy') === 'false')
  const afterDrag = await page.evaluate(() => ({
    sliderValue: Number(document.querySelector('[data-testid="weight-slider-commits_weekly_mean"]').value),
    sliderValues: [...document.querySelectorAll('[data-testid^="weight-slider-"]')].map((input) => Number(input.value)),
    total: [...document.querySelectorAll('[data-testid^="weight-slider-"]')].reduce((sum, input) => sum + Number(input.value), 0),
    requestWeights: window.__selectionCalls.at(-1),
  }))
  assert.ok(Math.abs(afterDrag.sliderValue - Math.round(afterDrag.sliderValue)) > 0.005, '滑杆拖动后应保留小数')
  assert.ok(Math.abs(afterDrag.total - 100) < 0.005, `拖动后总权重变化：${afterDrag.total}`)
  assert.ok(Math.abs(Object.values(afterDrag.requestWeights).reduce((sum, weight) => sum + weight, 0) - 10) < 0.005, '拖动后 API 权重应合计 10')
  assert.ok(afterDrag.sliderValues.some((value, index) => index > 0 && value !== 25), '拖动一项后其余权重没有按比例调整')

  const setInput = async (selector, value) => {
    await page.$eval(selector, (input, nextValue) => {
      input.focus()
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, String(nextValue))
      input.dispatchEvent(new Event('input', { bubbles: true }))
    }, value)
  }
  const preciseSelector = '[data-testid="weight-input-issue_median_hours"]'
  const callsBeforePrecise = await page.evaluate(() => window.__selectionCalls.length)
  await setInput(preciseSelector, '13.25')
  await page.keyboard.press('Enter')
  await page.waitForFunction((count) => window.__selectionCalls.length > count, {}, callsBeforePrecise)
  const precise = await page.$eval(preciseSelector, (input) => input.value)
  assert.equal(precise, '13.25', '精确输入应保留两位小数')
  assert.ok(Math.abs(await page.$$eval('[data-testid^="weight-slider-"]', (inputs) => inputs.reduce((sum, input) => sum + Number(input.value), 0)) - 100) < 0.005)

  const callsBeforeInvalid = await page.evaluate(() => window.__selectionCalls.length)
  await setInput(preciseSelector, '101')
  await page.keyboard.press('Enter')
  assert.equal(await page.$eval(preciseSelector, (input) => input.value), precise, '越界输入应恢复上次有效值')
  assert.ok(await page.$('[id="weight-error-issue_median_hours"]'), '越界输入应说明可用范围')
  assert.equal(await page.evaluate(() => window.__selectionCalls.length), callsBeforeInvalid, '非法输入不应触发重算')
  await setInput(preciseSelector, '12')
  await page.keyboard.press('Escape')
  assert.equal(await page.$eval(preciseSelector, (input) => input.value), precise, 'Escape 应撤销未提交编辑')

  const choosePreset = async (key) => {
    const count = await page.evaluate(() => window.__selectionCalls.length)
    await page.click(`[data-testid="weight-preset-${key}"]`)
    await page.waitForFunction((previous) => window.__selectionCalls.length > previous, {}, count)
    await page.waitForFunction(() => document.querySelector('[data-testid="selection-result"]')?.getAttribute('aria-busy') === 'false')
    return page.evaluate(() => window.__selectionInputs.at(-1).weights)
  }
  const activityWeights = await choosePreset('activity')
  assert.deepEqual(activityWeights, { commits_weekly_mean: 10, issue_median_hours: 0, pr_median_hours: 0, release_interval_days: 0 })
  const collaborationWeights = await choosePreset('collaboration')
  assert.deepEqual(collaborationWeights, { commits_weekly_mean: 0, issue_median_hours: 5, pr_median_hours: 5, release_interval_days: 0 })
  const releaseWeights = await choosePreset('release')
  assert.deepEqual(releaseWeights, { commits_weekly_mean: 0, issue_median_hours: 0, pr_median_hours: 0, release_interval_days: 10 })
  await choosePreset('balanced')

  const rowFacts = await page.$$eval('table[aria-label="仓库综合评分排名"] tbody > tr[data-testid^="selection-score-"]', (rows) => rows.map((row) => ({
    id: row.getAttribute('data-testid'),
    name: row.cells[1].textContent.trim(),
    measured: row.cells[3].textContent.trim(),
  })))
  assert.equal(rowFacts.length, 5)
  assert.ok(rowFacts[0].name.startsWith('steady-core/'))
  assert.match(rowFacts[0].measured, /4\/4/)
  assert.match(rowFacts[1].measured, /3\/4/)

  await page.click('[data-testid="selection-details-toggle-steady-core"]')
  assert.equal(await page.$eval('[data-testid="selection-details-toggle-steady-core"]', (button) => button.getAttribute('aria-expanded')), 'true')
  const evidence = await page.$eval('#selection-evidence-desktop-steady-core', (element) => element.textContent)
  assert.match(evidence, /指标贡献与证据/)
  assert.match(evidence, /有效样本/)
  assert.match(evidence, /来源类型/)
  assert.match(evidence, /部分覆盖/)
  await page.click('[data-testid="selection-details-toggle-grid-lite"]')
  assert.equal(await page.$eval('[data-testid="selection-details-toggle-steady-core"]', (button) => button.getAttribute('aria-expanded')), 'false', '同时只允许展开一个仓库')
  assert.equal(await page.$eval('[data-testid="selection-details-toggle-grid-lite"]', (button) => button.getAttribute('aria-expanded')), 'true')
  const neutralEvidence = await page.$eval('#selection-evidence-desktop-grid-lite', (element) => element.textContent)
  assert.match(neutralEvidence, /中性 50 分（无有效样本）/)

  await page.evaluate(() => { window.__selectionAllNeutral = true })
  await choosePreset('activity')
  const neutralNotice = await page.$eval('[aria-labelledby="comparison-ranking-title"]', (element) => element.textContent)
  assert.match(neutralNotice, /缺少可区分的实测证据/)
  assert.doesNotMatch(neutralNotice, /最佳|最优/)
  await page.evaluate(() => { window.__selectionAllNeutral = false; window.__selectionOwnWindow = true })
  await choosePreset('balanced')
  assert.match(await page.$eval('[aria-labelledby="comparison-ranking-title"]', (element) => element.textContent), /各仓库自身窗口，不代表同期/)
  await page.evaluate(() => { window.__selectionOwnWindow = false; window.__selectionInsufficient = true })
  await choosePreset('activity')
  assert.equal(await page.$$('table[aria-label="仓库综合评分排名"] tbody > tr[data-testid^="selection-score-"]').then((rows) => rows.length), 0, '不足数据时不应展示伪排名')
  assert.match(await page.$eval('[aria-labelledby="comparison-ranking-title"]', (element) => element.textContent), /暂不能生成可用排名/)
  await page.evaluate(() => { window.__selectionInsufficient = false })
  await choosePreset('balanced')

  await page.setViewport({ width: 1440, height: 900 })
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: '/private/tmp/repovantage-selection-desktop-1440x900.png', fullPage: true })
  const desktopLayout = await page.$eval('[data-testid="selection-report"]', (element) => Math.round(element.getBoundingClientRect().height))
  await page.setViewport({ width: 1280, height: 800 })
  await delay(100)
  const medium = await page.evaluate(() => ({ viewportWidth: innerWidth, documentWidth: document.documentElement.scrollWidth }))
  assert.ok(medium.documentWidth <= medium.viewportWidth + 1, '1280px 页面发生横向溢出')
  await page.screenshot({ path: '/private/tmp/repovantage-selection-desktop-1280x800.png', fullPage: true })
  await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }])
  const reducedMotion = await page.$eval('table[aria-label="仓库综合评分排名"] [role="progressbar"] > div', (element) => getComputedStyle(element).transitionProperty)
  assert.equal(reducedMotion, 'none', '系统减少动态效果时应关闭分数条过渡')

  await page.click('button[aria-label="切换深色主题"]')
  assert.ok(await page.$eval('html', (element) => element.classList.contains('dark')), '深色模式应切换成功')
  await page.setViewport({ width: 390, height: 844 })
  await delay(100)
  const mobile = await page.evaluate(() => ({
    viewportWidth: innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    slider: (() => {
      const rect = document.querySelector('[data-testid="weight-slider-commits_weekly_mean"]').getBoundingClientRect()
      return { left: rect.left, right: rect.right }
    })(),
    desktopTableDisplay: getComputedStyle(document.querySelector('table[aria-label="仓库综合评分排名"]')).display,
    mobileListDisplay: getComputedStyle(document.querySelector('ul[aria-label="仓库综合评分排名"]')).display,
  }))
  assert.ok(mobile.documentWidth <= mobile.viewportWidth + 1, '手机页面发生横向溢出')
  assert.ok(mobile.slider.left >= 0 && mobile.slider.right <= mobile.viewportWidth + 1, '手机端滑杆超出视口')
  assert.equal(mobile.desktopTableDisplay, 'none', '手机端应切换为紧凑列表')
  assert.notEqual(mobile.mobileListDisplay, 'none', '手机端列表应显示')
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: '/private/tmp/repovantage-selection-mobile-390x844.png', fullPage: true })

  await page.click('button[aria-label="切换浅色主题"]')
  assert.equal(await page.$eval('html', (element) => element.classList.contains('dark')), false, '浅色模式应切换成功')
  assert.deepEqual(pageErrors, [], `页面运行错误：${pageErrors.join('; ')}`)
  assert.deepEqual(externalRequests, [], 'Mock 浏览器检查不应请求 GitHub')
  console.log(JSON.stringify({ initial, scaleCompatibility, duringUpdate, afterDrag, precise, rowFacts, evidence: evidence.slice(0, 350), neutralNotice, desktopLayout, medium, mobile, reducedMotion, pageErrors, externalRequests }, null, 2))
} finally {
  await browser.close()
}
