import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

const source = await readFile(new URL('../src/lib/overviewChartData.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } })
const analytics = await import(`data:text/javascript,${encodeURIComponent(outputText)}`)
const { buildOverviewChartData, getMedian, getPushBucketKey, getStarsBucketKey, languageColor } = analytics

const DAY = 24 * 60 * 60 * 1000
const asOfMs = Date.parse('2026-11-21T00:00:00.000Z')
function repository(id, overrides = {}) {
  return {
    id: String(id), fullName: `owner/repo-${id}`, description: null, language: 'TypeScript', stars: 10, forks: 2,
    license: null, topics: [], status: 'ready', lastAnalyzedAt: null, activityDelta: null,
    ...overrides,
  }
}
function pushedAtDaysAgo(days, extraMs = 0) { return new Date(asOfMs - days * DAY - extraMs).toISOString() }

const starValues = [0, 1, 100, 101, 1_000, 1_001, 10_000, 10_001, 100_000, 100_001, null, -1, 1.5, Number.POSITIVE_INFINITY]
for (const [index, value] of starValues.entries()) {
  const expected = ['zero', 'b1', 'b1', 'b2', 'b2', 'b3', 'b3', 'b4', 'b4', 'b5', null, null, null, null][index]
  assert.equal(getStarsBucketKey(value), expected, `Stars 边界值 ${String(value)} 必须只落入一个档位`)
}

const pushBoundaries = [
  [7, 0, '7d'], [7, 1, '30d'], [30, 0, '30d'], [30, 1, '90d'], [90, 0, '90d'],
  [90, 1, '365d'], [365, 0, '365d'], [365, 1, 'older'],
]
for (const [days, extraMs, expected] of pushBoundaries) {
  assert.equal(getPushBucketKey(pushedAtDaysAgo(days, extraMs), asOfMs), expected, `${days} 天窗口边界应准确归组`)
}
assert.equal(getPushBucketKey(new Date(asOfMs + 1).toISOString(), asOfMs), 'future', '未来时间戳必须作为异常单列')
assert.equal(getPushBucketKey('not-a-date', asOfMs), 'missing', '无效日期不能被误判成近 0 天')
assert.equal(getPushBucketKey(null, asOfMs), 'missing', '缺失日期不能被误判成近 0 天')
assert.equal(getMedian([]), null, '空样本的中位数为 null')
assert.equal(getMedian([4, 1, 8, 3]), 3.5, '偶数样本的中位数应取中央两值均值')

const boundaryRepositories = starValues.map((stars, index) => repository(index + 1, { stars }))
boundaryRepositories.push(repository(1, { stars: 9, fullName: 'owner/duplicate-id-is-ignored' }))
const starData = buildOverviewChartData({ repositories: boundaryRepositories, asOfMs })
assert.equal(starData.repositories.length, 14, '重复仓库 ID 只应出现一次')
assert.equal(starData.validStarsCount, 10, '0 是有效值，缺失和无效值不进入分母')
assert.equal(starData.invalidStarsCount, 3, '负数、非整数與非有限 Stars 计为无效值')
assert.deepEqual(starData.starsBuckets.map((bucket) => bucket.count), [1, 2, 2, 2, 2, 1], 'Stars 桶数量合计必须等于有效样本')
assert.equal(starData.starsBuckets.reduce((sum, bucket) => sum + bucket.count, 0), 10)
assert.notEqual(starData.starsPoints.find((point) => point.stars === 0).xPlot, starData.starsPoints.find((point) => point.stars === 1).xPlot, 'log1p 必须区分 0 与 1')

const languages = ['Python', 'Go', 'Java', 'Rust', 'TypeScript', 'C++', '未知语言', '  ', 'JavaScript', 'Python', 'Go', 'Java']
const languageData = buildOverviewChartData({ repositories: languages.map((language, index) => repository(`lang-${index}`, { language: language.trim() || null })), asOfMs })
assert.equal(languageData.languageRows.reduce((sum, row) => sum + row.count, 0), 12, '语言汇总必须覆盖所有仓库')
assert.equal(languageData.languageRows.find((row) => row.label === 'Python').percent, 16.666666666666664, '语言占比的分母包括未知语言')
assert.equal(languageData.languageRows.find((row) => row.key === 'other').count, 2, '前五种已知语言以外的类型要合并')
assert.equal(languageData.languageRows.find((row) => row.key === 'unknown').count, 2, '空白和未知语言归入独立未知类')
assert.equal(languageColor('Go'), languageColor('Go'), '语言色映射必须稳定')

const pushRepositories = [
  repository('recent', { pushedAt: pushedAtDaysAgo(2) }),
  repository('window', { pushedAt: pushedAtDaysAgo(30) }),
  repository('old', { pushedAt: pushedAtDaysAgo(365.1) }),
  repository('future', { pushedAt: new Date(asOfMs + DAY).toISOString() }),
  repository('missing', { pushedAt: null }),
  repository('invalid', { pushedAt: 'bad-date' }),
]
const pushData = buildOverviewChartData({ repositories: pushRepositories, asOfMs })
assert.equal(pushData.active30Count, 2)
assert.equal(pushData.active30Rate, 2 / 6 * 100, '近 30 天活跃率分母必须包含无日期仓库')
assert.equal(pushData.futurePushCount, 1)
assert.equal(pushData.missingPushCount, 2)
assert.equal(pushData.invalidPushCount, 1)
assert.equal(pushData.popularityPoints.length, 6, '合法 0 值仍参与 Stars/Forks 配对')

const overlapping = buildOverviewChartData({ repositories: [
  repository('a', { stars: 100, forks: 10 }), repository('b', { stars: 100, forks: 10 }),
  repository('zero', { stars: 0, forks: 0 }), repository('one', { stars: 1, forks: 1 }),
  repository('missing-forks', { forks: null }),
], asOfMs })
assert.equal(overlapping.popularityOverlapGroups[0].count, 2, '数值完全相同的点必须保留可展开的重合记录')
assert.notEqual(overlapping.popularityPoints.find((point) => point.repositoryId === 'zero').xPlot, overlapping.popularityPoints.find((point) => point.repositoryId === 'one').xPlot)
assert.equal(overlapping.popularityMedianStars, 50.5, '中位数先按真实数值计算')
assert.equal(overlapping.popularityPoints.length, 4, '缺失 Forks 的记录不参与配对')

const empty = buildOverviewChartData({ repositories: [], asOfMs })
assert.equal(empty.languageRows.length, 0)
assert.equal(empty.popularityMedianStars, null)
assert.equal(empty.active30Rate, 0)
assert.ok(empty.starsBuckets.every((bucket) => bucket.percent === 0), '空样本比例不得产生 NaN')

console.log('总览图表统计：Stars 边界、语言覆盖、重合点、0/null 区分和 Push 时间窗口通过')
