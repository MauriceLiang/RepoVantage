import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

const source = await readFile(new URL('../src/lib/chartAnalytics.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } })
const { dailyCoveragePoints } = await import(`data:text/javascript,${encodeURIComponent(outputText)}`)

const complete = dailyCoveragePoints(
  [{ date: '2026-11-17', count: 2 }],
  '2026-11-16T12:00:00Z',
  '2026-11-18T00:00:00Z',
  true,
)
assert.deepEqual(complete, [
  { date: '2026-11-16', value: 0, quality: '完整覆盖' },
  { date: '2026-11-17', value: 2, quality: '完整覆盖' },
], '完整覆盖应显式保留无事件日期为零，并尊重 UTC 窗口边界')

const partial = dailyCoveragePoints(
  [{ date: '2026-11-17', count: 2 }, { date: '2026-11-18', count: 0 }],
  '2026-11-16T12:00:00Z',
  '2026-11-19T00:00:00Z',
  false,
)
assert.deepEqual(partial, [
  { date: '2026-11-17', value: null, observedValue: 2, quality: '部分覆盖' },
  { date: '2026-11-18', value: null, observedValue: 0, quality: '部分覆盖' },
], '部分覆盖的观察数量（包括观察到零）必须与完整计数区分')

console.log('图表聚合：完整零值、部分观察值与 UTC 日期边界通过')
