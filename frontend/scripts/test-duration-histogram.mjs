import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

const source = await readFile(new URL('../src/components/charts/options.ts', import.meta.url), 'utf8')
const functionSource = source.match(/export function histogramOption\([\s\S]*?\n}\n/)?.[0]
assert.ok(functionSource, '应能找到耗时分布图配置函数')

const compiled = ts.transpileModule(functionSource.replace('export function', 'function'), {
  compilerOptions: { module: ts.ModuleKind.None, target: ts.ScriptTarget.ES2022 },
}).outputText
const loadOption = new Function(
  'axis',
  'tip',
  'MONO',
  'fontFamily',
  compiled + '\nreturn histogramOption',
)
const histogramOption = loadOption(() => ({}), () => ({}), '等宽字体', '无衬线字体')
const theme = {
  muted: '#777', border: '#ddd', ink: '#111', panel: '#fff',
  series: ['#e2683c', '#e5a03a', '#ce3f7c', '#2e8fcb'],
}
const buckets = [
  { label: '<1 天', count: 3 },
  { label: '1–3 天', count: 8 },
  { label: '3–7 天', count: 2 },
  { label: '7–30 天', count: 5 },
  { label: '≥30 天', count: 7 },
]

const previous = histogramOption(buckets, '#e5a03a', theme, '个 Issue')
assert.equal(previous.series[1].step, 'end', '其他耗时图表保持原有阶梯线')
assert.equal(previous.series[1].markLine, undefined)

const issue = histogramOption(buckets, '#e5a03a', theme, '个 Issue', {
  cumulativeStep: false,
  medianDays: 6,
  showMedianReference: true,
})
assert.equal(issue.series[1].step, undefined, 'Issue 累计占比使用普通折线')
assert.deepEqual(issue.series[1].data, [12, 44, 52, 72, 100])
assert.deepEqual(issue.series[1].markLine.data, [{ yAxis: 50 }])
assert.deepEqual(issue.series[1].markPoint.data[0].coord, ['3–7 天', 50], 'P50 应标在包含中位数的耗时区间')
assert.match(issue.series[1].markPoint.label.formatter, /P50 6 天/)

const longerTail = histogramOption([
  { label: '0–1 天', count: 2 },
  { label: '1–3 天', count: 4 },
  { label: '3–7 天', count: 6 },
  { label: '7–14 天', count: 3 },
  { label: '14–30 天', count: 2 },
  { label: '30 天+', count: 3 },
], '#e5a03a', theme, '个 Issue', {
  cumulativeStep: false,
  medianDays: 99,
  showMedianReference: true,
})
assert.deepEqual(longerTail.series[1].markPoint.data[0].coord, ['30 天+', 50], '末尾开放区间应承接长尾中位数')

const empty = histogramOption(buckets.map((bucket) => ({ ...bucket, count: 0 })), '#e5a03a', theme, '个 Issue', {
  cumulativeStep: false,
  medianDays: null,
  showMedianReference: true,
})
assert.equal(empty.series[1].markLine, undefined, '没有样本时不显示误导性的 50% 参考线')
assert.equal(empty.series[1].markPoint, undefined)

console.log('Issue 耗时组合图：普通折线、累计占比、50% 参考线、P50 区间与空样本通过')
