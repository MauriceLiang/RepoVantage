import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

const source = await readFile(new URL('../src/lib/issueTrend.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } })
const { buildIssueTrend } = await import(`data:text/javascript,${encodeURIComponent(outputText)}`)
const point = (date, value, extra = {}) => ({ date, value, quality: 'ready', completeWeek: true, ...extra })
const series = [
  { key: 'opened', label: '新增', points: [
    point('2026-08-03', 8), point('2026-08-10', 3), point('2026-08-17', 0),
    point('2026-08-24', null, { quality: 'partial', observedValue: 2 }), point('2026-09-14', 4),
  ] },
  { key: 'closed', label: '关闭', points: [
    point('2026-08-03', 5), point('2026-08-10', 6), point('2026-08-17', 0),
    point('2026-08-24', null, { quality: 'partial', observedValue: 0 }), point('2026-08-31', 4), point('2026-09-14', 4),
  ] },
]
const bounds = ['2026-08-03T00:00:00Z', '2026-09-21T00:00:00Z']
const rows = buildIssueTrend(series, 'complete', ...bounds)
assert.deepEqual(rows.map((row) => row.difference), [3, -3, 0, null, null, null, 0])
assert.equal(rows[3].added.value, 2)
assert.equal(rows[3].added.complete, false)
assert.equal(rows[3].resolved.value, null, '部分覆盖下观察到零不能视为完整零值')
assert.equal(rows[4].added.value, null, '缺失的新增计数不能补零')
assert.equal(rows[5].date, '2026-09-07', '两条序列缺失同一周时应保留空档')
assert.equal(rows[5].difference, null)
assert.equal(buildIssueTrend(series, 'partial', ...bounds)[0].difference, 3, '逐周完整性以周数据为准，不受耗时样本量影响')
const sparse = series.map((item) => ({ ...item, points: item.points.filter((entry) => ['2026-08-03', '2026-09-14'].includes(entry.date)) }))
assert.deepEqual(buildIssueTrend(sparse, 'complete', ...bounds).map((row) => row.difference), [3, null, null, null, null, null, 0], '连续缺失多周时不能跨空档连线')

const legacy = [
  { key: 'created', label: '新增', points: [{ date: '2026-08-03', value: 3 }, { date: '2026-08-10', value: 5 }] },
  { key: 'closed', label: '关闭', points: [{ date: '2026-08-03', value: 0 }, { date: '2026-08-10', value: 2 }] },
]
const boundary = buildIssueTrend(legacy, 'complete', '2026-08-03T12:00:00Z', '2026-08-17T00:00:00Z')
assert.equal(boundary[0].difference, null, '窗口起点所在的不完整周不能计算完整差值')
assert.equal(boundary[0].resolved.value, null)
assert.equal(boundary[1].difference, 3)
assert.equal(buildIssueTrend(legacy, 'partial', ...bounds)[1].difference, null)
assert.deepEqual(buildIssueTrend(series, 'complete', '2026-08-10T00:00:00Z', '2026-08-24T00:00:00Z').map((row) => row.date), ['2026-08-10', '2026-08-17'])
console.log('Issue 组合图：正负差值、零值、缺失、部分覆盖与时间边界通过')
