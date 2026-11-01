import puppeteer from 'puppeteer-core'
import { mkdir } from 'node:fs/promises'

const BASE = process.env.BASE_URL ?? 'http://localhost:5178'
const CHROME = process.env.CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

const pages = [
  ['overview', '/'],
  ['repositories', '/repositories'],
  ['repo-overview', '/repositories/steady-core/overview'],
  ['repo-activity', '/repositories/steady-core/activity'],
  ['repo-issues', '/repositories/steady-core/issues'],
  ['repo-prs', '/repositories/steady-core/prs'],
  ['repo-releases', '/repositories/steady-core/releases'],
  ['compare', '/compare'],
  ['research', '/research'],
  ['tasks', '/tasks'],
]

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--hide-scrollbars', '--font-render-hinting=none'],
})

for (const theme of ['light', 'dark']) {
  const page = await browser.newPage()
  await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 })
  await page.evaluateOnNewDocument((t) => localStorage.setItem('repovantage-theme', t), theme)
  await mkdir(`docs/screenshots/${theme}`, { recursive: true })
  for (const [name, path] of pages) {
    await page.goto(BASE + path, { waitUntil: 'networkidle0' })
    await new Promise((r) => setTimeout(r, 900))
    await page.screenshot({ path: `docs/screenshots/${theme}/${name}.png`, fullPage: true })
    console.log(theme, name)
  }
  // 打开下钻详情侧栏。
  await page.goto(BASE + '/repositories/steady-core/overview', { waitUntil: 'networkidle0' })
  await new Promise((r) => setTimeout(r, 800))
  await page.evaluate(() => {
    const bars = document.querySelectorAll('canvas')
    const target = bars[1] ?? bars[0]
    target?.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: 600, clientY: 500 }))
  })
  await page.evaluate(() => {
    // 如果未点中画布元素，则通过界面状态打开侧栏作为截图兜底。
    const btn = [...document.querySelectorAll('button')].find((b) => b.textContent?.includes('数据与口径'))
    btn?.click()
  })
  await new Promise((r) => setTimeout(r, 500))
  await page.screenshot({ path: `docs/screenshots/${theme}/drawer.png`, fullPage: false })
  console.log(theme, 'drawer')
  await page.close()
}

await browser.close()
