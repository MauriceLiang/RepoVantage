import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

const source = await readFile(new URL('../src/lib/commitActivity.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } })
const { buildCommitActivity } = await import(`data:text/javascript,${encodeURIComponent(outputText)}`)

const points = ['2026-08-03', '2026-08-10', '2026-08-17', '2026-08-24', '2026-08-31'].map((date, index) => ({
  date, value: index + 1, completeWeek: true, quality: 'ready',
}))
const weeks = points.map((point) => ({ start: point.date, complete: true, observedCommits: point.value, activeAuthors: 2, unidentifiedCommits: 1, contributors: [], otherCommits: 0 }))
const release = (tag, publishedAt, prerelease = false) => ({ tag, publishedAt, prerelease, intervalDays: null, note: '' })
const releases = [
  release('before-start', '2026-08-04T11:59:59Z'),
  release('second', '2026-08-06T01:00:00Z'),
  release('first', '2026-08-04T12:00:00Z'),
  release('prerelease', '2026-08-05T00:00:00Z', true),
  release('at-end', '2026-08-31T12:00:00Z'),
  release('invalid', 'not-a-date'),
]
const bounds = ['2026-08-04T12:00:00Z', '2026-08-31T12:00:00Z']
const rows = buildCommitActivity(points, weeks, releases, ...bounds)
assert.deepEqual(rows.map((row) => row.average), [null, null, null, 2.5, 3.5])
assert.deepEqual(rows[0].releases.map((item) => item.tag), ['first', 'second'])
assert.equal(rows.flatMap((row) => row.releases).length, 2, '窗口外与预发布不能显示')

const partialPoints = points.map((point) => ({ ...point }))
partialPoints[1] = { ...partialPoints[1], value: null, observedValue: 2, quality: 'partial' }
const partialWeeks = weeks.map((week) => ({ ...week }))
partialWeeks[1] = { ...partialWeeks[1], complete: false, activeAuthors: 1 }
const partial = buildCommitActivity(partialPoints, partialWeeks, [], ...bounds)
assert.equal(partial[1].commits, 2)
assert.equal(partial[1].authors, 1)
assert.equal(partial[1].complete, false)
assert.equal(partial[3].average, null)
assert.equal(partial[4].average, null)

partialPoints[1].observedValue = 0
partialWeeks[1].activeAuthors = 0
const unknown = buildCommitActivity(partialPoints, partialWeeks, [], ...bounds)
assert.equal(unknown[1].commits, null, '部分覆盖下观察到零不代表没有提交')
assert.equal(unknown[1].authors, null, '部分覆盖下不能推断活跃账号为零')

const gap = buildCommitActivity(points.filter((_, index) => index !== 1), weeks, [], ...bounds)
assert.equal(gap[3].average, null, '缺失自然周时不能计算四周均值')
assert.equal(buildCommitActivity(points, [], releases, null, null).flatMap((row) => row.releases).length, 0)
const clipped = buildCommitActivity(points, weeks, [], '2026-08-10T00:00:00Z', '2026-08-24T00:00:00Z')
assert.deepEqual(clipped.map((row) => [row.date, row.sourceIndex]), [['2026-08-10', 1], ['2026-08-17', 2]])
console.log('开发活动组合图：完整周均值、部分覆盖、缺失周与 UTC 发布边界通过')
