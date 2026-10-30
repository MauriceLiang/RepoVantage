import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

const source = await readFile(new URL('../src/lib/authorConcentration.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } })
const { summarizeAuthorDistribution } = await import(`data:text/javascript,${encodeURIComponent(outputText)}`)

const equal = summarizeAuthorDistribution([{ commits: 4, authors: 5 }])
assert.equal(equal.authors, 5)
assert.equal(equal.commits, 20)
assert.equal(equal.gini, 0)
assert.equal(equal.contributors, 3)

const concentrated = summarizeAuthorDistribution([{ commits: 5, authors: 1 }, { commits: 1, authors: 21 }])
assert.equal(concentrated.authors, 22)
assert.equal(concentrated.commits, 26)
assert.ok(Math.abs(concentrated.gini - 168 / 1144) < 1e-12)
assert.equal(concentrated.contributors, 9)
assert.deepEqual(concentrated.points.at(-1).value, [100, 100])
assert.equal(summarizeAuthorDistribution([{ commits: 7, authors: 1 }]).gini, 0)
assert.equal(summarizeAuthorDistribution([]), null)
console.log('作者集中度：均等、集中、单作者和空样本通过')
