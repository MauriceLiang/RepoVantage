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
  await page.setViewport({ width: 1440, height: 1000 })
  await page.evaluateOnNewDocument(() => localStorage.setItem('repovantage-theme', 'light'))
  await page.goto(new URL('/repositories', base).href, { waitUntil: 'networkidle0' })
  assert.equal(await page.$eval('[data-testid="app"]', (element) => element.getAttribute('data-mode')), 'mock')
  assert.equal(await page.$eval('nav[aria-label="主要导航"]', (nav) => nav.textContent?.includes('项目比较') ?? false), false, '项目比较不应作为独立侧栏入口')

  await page.evaluate(async () => {
    const { MockRepositoryDataSource } = await import('/src/services/mockRepositoryDataSource.ts')
    window.__selectionCalls = []
    window.__selectionInputs = []
    MockRepositoryDataSource.prototype.getSelection = async function (input) {
      window.__selectionCalls.push({ ...input.weights })
      window.__selectionInputs.push({ ...input, weights: { ...input.weights } })
      const active = Object.entries(input.weights).filter(([, weight]) => weight > 0)
      const totalWeight = active.reduce((sum, [, weight]) => sum + weight, 0)
      return {
        status: 'available',
        scoringVersion: 'weighted-relative-v2',
        weights: Object.fromEntries(active.map(([metric, weight]) => [metric, weight / totalWeight])),
        sharedWindow: { start: '2026-01-01T00:00:00Z', end: '2026-04-01T00:00:00Z' },
        ranking: input.repositoryIds.map((id, index) => {
          const normalized = index === 0 ? 0.8 : 0.4
          const evidence = active.map(([metric, weight], metricIndex) => ({
            metric,
            value: 4 + metricIndex,
            unit: metric.includes('hours') || metric.includes('days') ? '天' : '次/周',
            normalized,
            weight: weight / totalWeight,
            contribution: normalized * weight / totalWeight * 100,
            validSamples: 12,
            windowStart: '2026-01-01',
            windowEnd: '2026-04-01',
            sourceRunId: `mock-${id}`,
            sourceKind: 'online_event_analysis',
          }))
          return { id, name: `${id}/test-repo`, score: normalized * 100, evidence }
        }),
        excluded: [],
        sensitivity: [],
        maintenance: {
          commonWindow: null,
          dataAsOf: null,
          repositories: input.repositoryIds.map((id) => ({
            id,
            name: `${id}/test-repo`,
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
            activityAnomaly: { status: 'insufficient_data', method: 'none', suspected: false, reasonCode: 'insufficient_data', weeks: [], notes: [] },
          })),
        },
        notes: ['浏览器交互测试替身，不是实际分析结果。'],
        reportMarkdown: '# 测试报告',
        resultSignature: 'test-signature',
      }
    }
  })

  for (const id of ['steady-core', 'grid-lite']) {
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
  await page.waitForFunction(() => [...document.querySelectorAll('[data-testid^="weight-metric-"] input[type="range"]')].some((input) => !input.disabled))
  await page.waitForSelector('[data-testid^="selection-score-"]')

  const initial = await page.evaluate(() => ({
    active: [...document.querySelectorAll('[data-testid^="weight-metric-"] input[type="range"]')].filter((input) => Number(input.value) > 0).length,
    available: [...document.querySelectorAll('[data-testid^="weight-metric-"] input[type="range"]')].filter((input) => !input.disabled).length,
    sliderTotal: [...document.querySelectorAll('[data-testid^="weight-metric-"] input[type="range"]')].reduce((sum, input) => sum + Number(input.value), 0),
    donut: document.querySelector('[data-testid="weight-donut"]').getAttribute('style'),
    sliderLabels: [...document.querySelectorAll('[data-testid^="weight-metric-"] input[type="range"]')].map((input) => input.getAttribute('aria-label')),
    sliderValues: [...document.querySelectorAll('[data-testid^="weight-metric-"] input[type="range"]')].map((input) => Number(input.value)),
    scoreCount: document.querySelectorAll('[data-testid^="selection-score-"]').length,
    scoreText: document.querySelector('[data-testid^="selection-score-"]').textContent,
    selectionInput: window.__selectionInputs[0],
    filterInputCount: [...document.querySelectorAll('[data-testid="selection-report"] input')].filter((input) => input.type === 'text').length,
    explanationVisible: Boolean(document.querySelector('[data-testid="selection-scoring-explanation"]')),
    maintenanceVisible: Boolean(document.querySelector('[data-testid="selection-maintenance"]')),
    removedSupplementCount: [...document.querySelectorAll('[data-testid="selection-report"] summary')]
      .filter((summary) => ['评分口径与权重敏感性', '预览 Markdown 报告', '记录选择反馈'].some((title) => summary.textContent.includes(title))).length,
    sampleSourceCount: [...document.querySelectorAll('[data-testid^="selection-score-"] summary')]
      .filter((summary) => summary.textContent.includes('样本与来源')).length,
    calls: window.__selectionCalls.length,
    requestWeights: window.__selectionCalls[0],
    viewportWidth: innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    overflowElements: [...document.querySelectorAll('body *')].map((element) => {
      const rect = element.getBoundingClientRect()
      return { tag: element.tagName, className: typeof element.className === 'string' ? element.className : '', text: element.textContent?.trim().slice(0, 45), left: Math.round(rect.left), right: Math.round(rect.right) }
    }).filter((element) => element.right > innerWidth + 1 || element.left < -1).slice(-12),
  }))
  assert.ok(initial.calls >= 1, '默认权重应自动生成比较')
  assert.equal(initial.scoreCount, 2)
  assert.match(initial.scoreText, /80\.0\s*\/100/)
  assert.equal(initial.selectionInput.scenario, '自定义权重对比')
  assert.equal(initial.selectionInput.candidateGroup, '当前所选仓库')
  assert.equal(initial.selectionInput.candidatesConfirmed, true)
  assert.deepEqual(initial.selectionInput.allowedLanguages, [])
  assert.deepEqual(initial.selectionInput.allowedLicenses, [])
  assert.equal(initial.filterInputCount, 0, '评分说明之外仍显示筛选输入')
  assert.equal(initial.explanationVisible, true)
  assert.equal(initial.maintenanceVisible, true, '近期维护行为没有保留')
  assert.equal(initial.removedSupplementCount, 0, '仍显示已移除的辅助区块')
  assert.equal(initial.sampleSourceCount, 0, '综合排名仍显示样本与来源')
  assert.ok(Math.abs(initial.sliderTotal - 100) < 0.005, `权重初始值未合计为 100%：${initial.sliderTotal}`)
  assert.ok(initial.documentWidth <= initial.viewportWidth + 1, `桌面页面发生横向溢出：${initial.documentWidth}/${initial.viewportWidth} ${JSON.stringify(initial.overflowElements)}`)

  const scaleCompatibility = await page.evaluate(async () => {
    const originalFetch = window.fetch
    let requestBody
    let replyIndex = 0
    const evidence = (contribution) => ({ value: 1, unit: '次/周', normalized: 0.6, weight: 0.5, contribution, valid_samples: 10, window_start: '2026-01-01', window_end: '2026-04-01', source_run_id: 'fixture', source_kind: 'online_event_analysis' })
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
      if (url === '/api/browser/session') {
        return new Response(JSON.stringify({ csrf_token: 'test-token' }), { headers: { 'content-type': 'application/json' } })
      }
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
    } finally {
      window.fetch = originalFetch
    }
  })
  assert.equal(scaleCompatibility.legacy.score, 70, '旧版 0–1 综合分没有转换为百分制')
  assert.deepEqual(scaleCompatibility.legacy.contributions, [30, 40], '旧版单项贡献没有转换为百分制')
  assert.equal(scaleCompatibility.current.score, 70, '新版百分制分数不应再次缩放')
  assert.deepEqual(scaleCompatibility.current.contributions, [30, 40], '新版百分制贡献不应再次缩放')
  assert.deepEqual(scaleCompatibility.requestBody.repository_ids, [1, 2])
  assert.equal(scaleCompatibility.requestBody.candidates_confirmed, true)
  assert.equal(scaleCompatibility.requestBody.scenario, '自定义权重对比')

  const target = await page.$$eval('[data-testid^="weight-metric-"] input[type="range"]:not([disabled])', (inputs) => {
    const input = inputs.find((item) => Number(item.value) === 0) ?? inputs.find((item) => Number(item.value) > 0)
    const value = Number(input.value)
    return { label: input.getAttribute('aria-label'), value, nextValue: value === 0 ? 25.37 : value >= 75.37 ? value - 20.37 : value + 20.37 }
  })
  const previousCallCount = initial.calls
  const previousDonut = initial.donut
  const slider = await page.$(`[aria-label="${target.label}"]`)
  await slider.evaluate((input) => input.scrollIntoView({ block: 'center' }))
  const sliderBox = await slider.boundingBox()
  const startX = sliderBox.x + sliderBox.width * target.value / 100
  const endX = sliderBox.x + sliderBox.width * target.nextValue / 100
  const centerY = sliderBox.y + sliderBox.height / 2
  await page.mouse.move(startX, centerY)
  await page.mouse.down()
  await page.mouse.move(endX, centerY, { steps: 8 })
  await page.mouse.up()
  await page.waitForFunction((count) => window.__selectionCalls.length > count, {}, previousCallCount)
  await page.waitForSelector('[data-testid^="selection-score-"]')
  const updated = await page.evaluate((label) => {
    const slider = document.querySelector(`[aria-label="${label}"]`)
    return {
      weights: window.__selectionCalls.at(-1),
      donut: document.querySelector('[data-testid="weight-donut"]').getAttribute('style'),
      resultCount: document.querySelectorAll('[data-testid^="selection-score-"]').length,
      sliderValue: Number(slider.value),
      sliderValues: [...document.querySelectorAll('[data-testid^="weight-metric-"] input[type="range"]')].map((input) => Number(input.value)),
      sliderTotal: [...document.querySelectorAll('[data-testid^="weight-metric-"] input[type="range"]')].reduce((sum, input) => sum + Number(input.value), 0),
      sliderStep: slider.getAttribute('step'),
      sliderValueText: slider.getAttribute('aria-valuetext'),
    }
  }, target.label)
  assert.equal(updated.resultCount, 2)
  assert.notDeepEqual(updated.weights, initial.requestWeights, '滑杆变化没有进入自动重算请求')
  assert.equal(updated.sliderStep, 'any', '滑杆仍限制在离散步长')
  assert.ok(Math.abs(updated.sliderValue - Math.round(updated.sliderValue)) > 0.005, '拖动后权重仍被取整')
  assert.ok(Object.values(updated.weights).some((weight) => Math.abs(weight - Math.round(weight)) > 0.005), '小数权重没有进入综合分请求')
  assert.ok(Math.abs(updated.sliderTotal - 100) < 0.005, `拖动后总权重变化：${updated.sliderTotal}`)
  assert.ok(Math.abs(Object.values(updated.weights).reduce((sum, weight) => sum + weight, 0) - 10) < 0.005, '提交给接口的归一化权重不再合计10')
  const targetIndex = initial.sliderLabels.indexOf(target.label)
  assert.ok(updated.sliderValues.some((value, index) => index !== targetIndex && Math.abs(value - initial.sliderValues[index]) > 0.005), '拖动一项后其他权重没有同步调整')
  assert.match(updated.sliderValueText, /\d+\.\d+/, '无障碍标签没有显示小数权重')
  if (initial.active > 1) assert.notEqual(updated.donut, previousDonut, '多指标权重变化后环图占比没有改变')

  await page.click('[data-testid="manual-weight-toggle"]')
  const setManualWeight = async (metric, value) => {
    await page.$eval(`[data-testid="manual-weight-input-${metric}"]`, (input, nextValue) => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, String(nextValue))
      input.dispatchEvent(new Event('input', { bubbles: true }))
    }, value)
  }
  await setManualWeight('issue_median_hours', 40.25)
  await setManualWeight('pr_median_hours', 35.25)
  await setManualWeight('release_interval_days', 24.4)
  assert.equal(await page.$eval('[data-testid="apply-manual-weights"]', (button) => button.disabled), true, '权重合计不为100%时仍允许应用')
  await setManualWeight('release_interval_days', 24.5)
  await page.waitForFunction(() => !document.querySelector('[data-testid="apply-manual-weights"]').disabled)
  const beforeManualApply = await page.evaluate(() => window.__selectionCalls.length)
  await page.click('[data-testid="apply-manual-weights"]')
  await page.waitForFunction((count) => window.__selectionCalls.length > count, {}, beforeManualApply)
  const manual = await page.evaluate(() => ({
    sliderTotal: [...document.querySelectorAll('[data-testid^="weight-metric-"] input[type="range"]')].reduce((sum, input) => sum + Number(input.value), 0),
    weights: window.__selectionCalls.at(-1),
    editorVisible: Boolean(document.querySelector('[data-testid="manual-weight-editor"]')),
  }))
  assert.ok(Math.abs(manual.sliderTotal - 100) < 0.005, '手动应用后界面权重没有保持100%')
  assert.ok(Math.abs(Object.values(manual.weights).reduce((sum, weight) => sum + weight, 0) - 10) < 0.005, '手动权重没有按比例提交到接口')
  assert.equal(manual.editorVisible, false, '应用手动权重后未收起输入面板')

  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: '/private/tmp/repovantage-selection-desktop.png', fullPage: true })
  await page.setViewport({ width: 390, height: 844 })
  await delay(150)
  const mobile = await page.evaluate(() => {
    const slider = document.querySelector('[data-testid^="weight-metric-"] input[type="range"]').getBoundingClientRect()
    return { viewportWidth: innerWidth, documentWidth: document.documentElement.scrollWidth, sliderLeft: slider.left, sliderRight: slider.right }
  })
  assert.ok(mobile.documentWidth <= mobile.viewportWidth + 1, '手机页面发生横向溢出')
  assert.ok(mobile.sliderLeft >= 0 && mobile.sliderRight <= mobile.viewportWidth + 1, '手机端滑杆超出视口')
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: '/private/tmp/repovantage-selection-mobile.png', fullPage: true })
  await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }])
  const reducedMotion = await page.$eval('[data-testid^="selection-score-"] [role="progressbar"] > div', (element) => getComputedStyle(element).transitionProperty)
  assert.equal(reducedMotion, 'none', '系统减少动态效果时应关闭分数条过渡')
  assert.deepEqual(pageErrors, [], `页面运行错误：${pageErrors.join('; ')}`)
  assert.deepEqual(externalRequests, [], 'Mock 浏览器检查不应请求 GitHub')
  console.log(JSON.stringify({ initial, scaleCompatibility, updated, manual, mobile, reducedMotion, pageErrors, externalRequests }, null, 2))
} finally {
  await browser.close()
}
