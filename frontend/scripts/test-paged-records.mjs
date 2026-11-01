import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'
import { effectScope, nextTick, ref } from 'vue'

const source = await readFile(new URL('../src/composables/usePagedRecords.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const script = compiled.replace(/from ['"]vue['"]/, `from '${import.meta.resolve('vue')}'`)
const { usePagedRecords } = await import(`data:text/javascript,${encodeURIComponent(script)}`)

const repository = ref('first')
const requests = []
const scope = effectScope()
const state = scope.run(() => usePagedRecords(
  () => repository.value,
  (...args) => new Promise((resolve, reject) => requests.push({ args, resolve, reject })),
  '加载失败',
))
assert.deepEqual(requests[0].args, ['first', 1, 10, ''])

repository.value = 'second'
await nextTick()
requests[1].resolve({ total: 25, items: ['new'] })
await Promise.resolve()
requests[0].resolve({ total: 1, items: ['stale'] })
await Promise.resolve()
assert.deepEqual(state.records.value.items, ['new'])
assert.equal(state.pageCount.value, 3)

state.page.value = 2
await nextTick()
requests[2].resolve({ total: 25, items: ['page 2'] })
await Promise.resolve()
assert.equal(state.firstRecord.value, 11)
assert.equal(state.lastRecord.value, 20)

state.searchInput.value = '  bug  '
state.applySearch()
await nextTick()
assert.deepEqual(requests[3].args, ['second', 1, 10, 'bug'])
requests[3].reject('network failure')
await Promise.resolve()
assert.equal(state.loadError.value, '加载失败')
assert.equal(state.loading.value, false)

state.applySearch()
assert.deepEqual(requests[4].args, ['second', 1, 10, 'bug'])
requests[4].resolve({ total: 0, items: [] })
await Promise.resolve()
assert.equal(state.firstRecord.value, 0)
assert.equal(state.lastRecord.value, 0)
assert.equal(state.loadError.value, '')
scope.stop()
console.log('分页记录：切换仓库、过期响应、分页、搜索与重试通过')
