import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

const source = await readFile(new URL('../src/pages/Comparison/weightMath.ts', import.meta.url), 'utf8')
const javascript = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const moduleUrl = `data:text/javascript;base64,${Buffer.from(javascript).toString('base64')}`
const { presetWeights, rebalanceWeight } = await import(moduleUrl)

const metrics = ['commits_weekly_mean', 'issue_median_hours', 'pr_median_hours', 'release_interval_days']
const sum = (weights) => Object.values(weights).reduce((total, value) => total + value, 0)

assert.deepEqual(presetWeights('balanced'), {
  commits_weekly_mean: 25, issue_median_hours: 25, pr_median_hours: 25, release_interval_days: 25,
})
assert.deepEqual(presetWeights('activity'), {
  commits_weekly_mean: 100, issue_median_hours: 0, pr_median_hours: 0, release_interval_days: 0,
})
assert.deepEqual(presetWeights('collaboration'), {
  commits_weekly_mean: 0, issue_median_hours: 50, pr_median_hours: 50, release_interval_days: 0,
})
assert.deepEqual(presetWeights('release'), {
  commits_weekly_mean: 0, issue_median_hours: 0, pr_median_hours: 0, release_interval_days: 100,
})

const balanced = presetWeights('balanced')
const decimal = rebalanceWeight(balanced, 'commits_weekly_mean', 59.73)
assert.equal(decimal.commits_weekly_mean, 59.73)
assert.ok(Math.abs(sum(decimal) - 100) < 1e-10)
assert.ok(Math.abs(decimal.issue_median_hours - 13.423333333333334) < 1e-10)
assert.equal(rebalanceWeight(balanced, 'issue_median_hours', 0).issue_median_hours, 0)
assert.equal(rebalanceWeight(balanced, 'release_interval_days', 100).release_interval_days, 100)

const oneMetric = presetWeights('activity')
const splitFromZero = rebalanceWeight(oneMetric, 'commits_weekly_mean', 40)
assert.ok(Math.abs(sum(splitFromZero) - 100) < 1e-10)
for (const key of metrics.filter((metric) => metric !== 'commits_weekly_mean')) assert.equal(splitFromZero[key], 20)

assert.equal(rebalanceWeight(balanced, 'commits_weekly_mean', -10).commits_weekly_mean, 0)
assert.equal(rebalanceWeight(balanced, 'commits_weekly_mean', 110).commits_weekly_mean, 100)
assert.deepEqual(rebalanceWeight(balanced, 'commits_weekly_mean', Number.NaN), balanced)

console.log('selection weight math: passed')
