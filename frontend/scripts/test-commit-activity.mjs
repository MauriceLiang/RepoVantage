import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

async function loadModule(path) {
  const source = await readFile(new URL(path, import.meta.url), 'utf8')
  const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } })
  return import('data:text/javascript,' + encodeURIComponent(outputText))
}
const { buildCommitActivity } = await loadModule('../src/lib/commitActivity.ts')
const { buildCompleteFourWeekAverage } = await loadModule('../src/lib/commitAverages.ts')
const points = ['2026-08-03', '2026-08-10', '2026-08-17', '2026-08-24', '2026-08-31'].map((date, index) => ({ date, value: index + 1, completeWeek: true, quality: 'ready' }))
const weeks = points.map((point) => ({ start: point.date, complete: true, observedCommits: point.value, activeAuthors: 2, unidentifiedCommits: 1, contributors: [], otherCommits: 0 }))
const release = (tag, publishedAt, prerelease = false) => ({ tag, publishedAt, prerelease, intervalDays: null, note: '' })
const releases = [
  release('before-start', '2026-08-04T11:59:59Z'), release('second', '2026-08-06T01:00:00Z'),
  release('first', '2026-08-04T12:00:00Z'), release('prerelease', '2026-08-05T00:00:00Z', true),
  release('at-end', '2026-08-31T12:00:00Z'), release('invalid', 'not-a-date'),
]
const bounds = ['2026-08-04T12:00:00Z', '2026-08-31T00:00:00Z']
const rows = buildCommitActivity(points, weeks, releases, ...bounds)
assert.deepEqual(rows.map((row) => row.date), ['2026-08-03', '2026-08-10', '2026-08-17', '2026-08-24'])
assert.deepEqual(rows.map((row) => row.sourceIndex), [0, 1, 2, 3])
assert.deepEqual(rows[0].releases.map((item) => item.tag), ['first', 'second'])
assert.equal(rows.flatMap((row) => row.releases).length, 2, '窗口外、预发布和无效日期不能进入正式 Release 标记')
assert.deepEqual(buildCompleteFourWeekAverage(points).map((row) => row.value), [null, null, null, 2.5, 3.5])

const partialPoints = points.map((point) => ({ ...point }))
partialPoints[1] = { ...partialPoints[1], value: null, observedValue: 2, quality: 'partial' }
const partialWeeks = weeks.map((week) => ({ ...week }))
partialWeeks[1] = { ...partialWeeks[1], complete: false, activeAuthors: 1 }
const partial = buildCommitActivity(partialPoints, partialWeeks, [], ...bounds)
assert.equal(partial[1].commits, 2)
assert.equal(partial[1].authors, 1)
assert.equal(partial[1].complete, false)
assert.deepEqual(buildCompleteFourWeekAverage(partialPoints).map((row) => row.value), [null, null, null, null, null])

partialPoints[1].observedValue = 0
partialWeeks[1].activeAuthors = 0
const unknown = buildCommitActivity(partialPoints, partialWeeks, [], ...bounds)
assert.equal(unknown[1].commits, null, '部分覆盖下观察到零不代表没有提交')
assert.equal(unknown[1].authors, null, '部分覆盖下不能推断活跃账号为零')
const gapPoints = points.filter((_, index) => index !== 1)
assert.deepEqual(buildCompleteFourWeekAverage(gapPoints).map((row) => row.value), [null, null, null, null], '缺失的 UTC 周不能参与四周均值')
assert.equal(buildCommitActivity(gapPoints, weeks, [], ...bounds).at(-1).date, '2026-08-24')
assert.equal(buildCommitActivity(points, [], releases, null, null).flatMap((row) => row.releases).length, 0)
const clipped = buildCommitActivity(points, weeks, [], '2026-08-10T00:00:00Z', '2026-08-24T00:00:00Z')
assert.deepEqual(clipped.map((row) => [row.date, row.sourceIndex]), [['2026-08-10', 1], ['2026-08-17', 2]])
console.log('开发活动：窗口内 UTC 周、Release 过滤、完整四周均值、部分覆盖与缺周通过')
