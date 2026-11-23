import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

const source = await readFile(new URL('../src/lib/durationHistogram.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { buildHistogramRows } = await import('data:text/javascript,' + encodeURIComponent(compiled))
const buckets = [
  { label: '<1 天', count: 3 }, { label: '1–3 天', count: 8 }, { label: '3–7 天', count: 2 },
  { label: '7–30 天', count: 5 }, { label: '≥30 天', count: 7 },
]
assert.deepEqual(buildHistogramRows(buckets, true).map((row) => row.plotted), [3, 11, 13, 18, 25], '累计分布必须累加后端真实桶数')
assert.deepEqual(buildHistogramRows(buckets, false).map((row) => row.plotted), [3, 8, 2, 5, 7], '区间柱必须使用后端真实桶数')
assert.deepEqual(buildHistogramRows(buckets, false).map((row) => row.count), buckets.map((bucket) => bucket.count))
assert.deepEqual(buildHistogramRows(buckets.map((bucket) => ({ ...bucket, count: 0 })), true).map((row) => row.plotted), [0, 0, 0, 0, 0], 'API 返回的零桶保持为零')
assert.deepEqual(buildHistogramRows([], false), [], '无样本时保持空数据')
console.log('耗时分布：真实桶、累计数量、零桶和空样本通过')
