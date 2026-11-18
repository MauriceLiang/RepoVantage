<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, Info, RefreshCw } from 'lucide-vue-next'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiPageHeader from '@/components/ui/UiPageHeader.vue'
import UiPanel from '@/components/ui/UiPanel.vue'
import type { AtlasPoint, AtlasResponse } from '@/data/researchTypes'
import { getBrowserApiData } from '@/services/httpRepositoryDataSource'

const pageSize = 15
const result = ref<AtlasResponse | null>(null)
const loading = ref(true)
const error = ref('')
const trainQuery = ref('')
const testQuery = ref('')
const trainPage = ref(1)
const testPage = ref(1)

const trainingRows = computed(() => filteredRows('train', trainQuery.value))
const testRows = computed(() => filteredRows('test', testQuery.value))
const trainingPageCount = computed(() => Math.max(1, Math.ceil(trainingRows.value.length / pageSize)))
const testPageCount = computed(() => Math.max(1, Math.ceil(testRows.value.length / pageSize)))
const visibleTrainingRows = computed(() => pageRows(trainingRows.value, trainPage.value))
const visibleTestRows = computed(() => pageRows(testRows.value, testPage.value))

function filteredRows(role: 'train' | 'test', query: string): AtlasPoint[] {
  const normalized = query.trim().toLocaleLowerCase()
  return (result.value?.points ?? [])
    .filter((point) => point.sample_role === role)
    .filter((point) => !normalized || point.full_name.toLocaleLowerCase().includes(normalized))
    .sort((left, right) => left.full_name.localeCompare(right.full_name, 'en'))
}

function pageRows(rows: AtlasPoint[], page: number) {
  return rows.slice((page - 1) * pageSize, page * pageSize)
}

async function loadDataset() {
  loading.value = true
  error.value = ''
  try {
    result.value = await getBrowserApiData<AtlasResponse>('/research/atlas?dataset_id=course-research-300-v1')
    trainPage.value = 1
    testPage.value = 1
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '机器学习样本数据加载失败'
  } finally {
    loading.value = false
  }
}

function count(value: number | null | undefined) {
  return value === null || value === undefined ? '—' : value.toLocaleString('zh-CN', { maximumFractionDigits: 1 })
}

onMounted(() => { void loadDataset() })
</script>

<template>
  <div class="app-page ml-data-page">
    <UiPageHeader title="机器学习数据" description="300 个仓库按仓库 ID 固定分为训练组和留出测试组；两组名单、活动特征和模型评估分开展示。">
      <template #actions>
        <RouterLink class="button button--outline" to="/"><ArrowLeft :size="14" />返回概览</RouterLink>
        <UiButton variant="quiet" :loading="loading" @click="loadDataset"><RefreshCw :size="13" />刷新</UiButton>
      </template>
    </UiPageHeader>

    <div v-if="loading" class="panel ml-state" role="status">正在读取固定训练 / 测试样本…</div>
    <div v-else-if="error" class="panel ml-state ml-state--error" role="alert">
      <strong>机器学习样本暂不可用</strong><span>{{ error }}</span>
      <UiButton @click="loadDataset">重新加载</UiButton>
    </div>
    <template v-else-if="result">
      <div class="ml-context-row">
        <UiBadge tone="accent">{{ result.repository_count }} 个仓库</UiBadge>
        <span>训练 {{ trainingRows.length }} / 150</span>
        <span>测试 {{ testRows.length }} / 150</span>
        <span>{{ result.observation_window.weeks }} 个完整 UTC 周</span>
        <span>{{ result.observation_window.start.slice(0, 10) }} 至 {{ result.observation_window.end_exclusive.slice(0, 10) }}</span>
        <span>数据截至 {{ result.data_as_of.slice(0, 10) }}</span>
      </div>

      <section class="ml-evaluation" aria-label="模型历史评估">
        <UiPanel as="article" class="ml-model-card">
          <div class="ml-card-top"><span>M1 · 无监督聚类</span><UiBadge tone="accent">K-Means · K=3</UiBadge></div>
          <strong class="ml-card-result">测试轮廓系数 0.523</strong>
          <p>训练轮廓系数 0.489 · 按 Commit 规模分组基线 0.252 · 10 个种子平均 ARI 1.000</p>
          <small>描述近期提交模式；聚类不代表维护质量或健康度。</small>
        </UiPanel>
        <UiPanel as="article" class="ml-model-card">
          <div class="ml-card-top"><span>M2 · 未来 4 周趋势</span><UiBadge tone="accent">Logistic Regression</UiBadge></div>
          <strong class="ml-card-result">Macro-F1 0.541</strong>
          <p>Balanced Accuracy 0.579 · 最近趋势基线 0.440 / 0.443</p>
          <small>上升类召回率 0.327；趋势类别仍有较多漏判。</small>
        </UiPanel>
        <UiPanel as="article" class="ml-model-card ml-model-card--rule">
          <div class="ml-card-top"><span>M3 · 活动异常提示</span><UiBadge tone="neutral">统计规则</UiBadge></div>
          <strong class="ml-card-result">Median / MAD</strong>
          <p>以前 11 个完整周作为参照，稳健 Z 分数绝对值达到 3 时标记复核。</p>
          <small>这是统计规则，不是训练出的异常分类器。</small>
        </UiPanel>
      </section>

      <div v-if="trainingRows.length !== 150 || testRows.length !== 150" class="ml-coverage-warning" role="status">
        图谱当前返回训练 {{ trainingRows.length }} / 150、测试 {{ testRows.length }} / 150。名单数以固定分组清单为准；未返回的记录不会补成零值。
      </div>

      <section class="ml-split-grid" aria-label="训练与测试样本名单">
        <UiPanel as="section" class="ml-split-panel">
          <header class="ml-split-heading">
            <div><h2>训练集</h2><p>150 个仓库 · 用于拟合 M1 / M2 参数</p></div>
            <UiBadge tone="accent">TRAIN</UiBadge>
          </header>
          <label class="ml-search"><span class="sr-only">筛选训练仓库</span><UiInput v-model="trainQuery" type="search" placeholder="筛选仓库名称" /></label>
          <div class="ml-table-wrap">
            <table class="data-table ml-table">
              <thead><tr><th>仓库</th><th>语言</th><th>周均 Commit</th><th>周均 PR</th></tr></thead>
              <tbody>
                <tr v-for="point in visibleTrainingRows" :key="point.repository_id">
                  <td><a :href="`https://github.com/${point.full_name}`" target="_blank" rel="noreferrer">{{ point.full_name }}</a></td>
                  <td>{{ point.language || '未知' }}</td>
                  <td class="numeric">{{ count(point.weekly_commit_mean) }}</td>
                  <td class="numeric">{{ count(point.weekly_pr_open_mean) }}</td>
                </tr>
                <tr v-if="!visibleTrainingRows.length"><td colspan="4" class="ml-empty">没有匹配的训练仓库。</td></tr>
              </tbody>
            </table>
          </div>
          <footer class="ml-pagination">
            <span>{{ trainingRows.length }} 个训练样本</span>
            <div><UiButton variant="quiet" :disabled="trainPage <= 1" @click="trainPage--">上一页</UiButton><span>{{ trainPage }} / {{ trainingPageCount }}</span><UiButton variant="quiet" :disabled="trainPage >= trainingPageCount" @click="trainPage++">下一页</UiButton></div>
          </footer>
        </UiPanel>

        <UiPanel as="section" class="ml-split-panel">
          <header class="ml-split-heading">
            <div><h2>留出测试集</h2><p>150 个仓库 · 用于一次性历史回测</p></div>
            <UiBadge tone="success">TEST</UiBadge>
          </header>
          <label class="ml-search"><span class="sr-only">筛选测试仓库</span><UiInput v-model="testQuery" type="search" placeholder="筛选仓库名称" /></label>
          <div class="ml-table-wrap">
            <table class="data-table ml-table">
              <thead><tr><th>仓库</th><th>语言</th><th>周均 Commit</th><th>周均 PR</th></tr></thead>
              <tbody>
                <tr v-for="point in visibleTestRows" :key="point.repository_id">
                  <td><a :href="`https://github.com/${point.full_name}`" target="_blank" rel="noreferrer">{{ point.full_name }}</a></td>
                  <td>{{ point.language || '未知' }}</td>
                  <td class="numeric">{{ count(point.weekly_commit_mean) }}</td>
                  <td class="numeric">{{ count(point.weekly_pr_open_mean) }}</td>
                </tr>
                <tr v-if="!visibleTestRows.length"><td colspan="4" class="ml-empty">没有匹配的测试仓库。</td></tr>
              </tbody>
            </table>
          </div>
          <footer class="ml-pagination">
            <span>{{ testRows.length }} 个测试样本</span>
            <div><UiButton variant="quiet" :disabled="testPage <= 1" @click="testPage--">上一页</UiButton><span>{{ testPage }} / {{ testPageCount }}</span><UiButton variant="quiet" :disabled="testPage >= testPageCount" @click="testPage++">下一页</UiButton></div>
          </footer>
        </UiPanel>
      </section>

      <p class="ml-note"><Info :size="13" />这是同一批历史仓库的固定 150/150 留仓回测，不能代表独立新仓库或未来时点效果。表内显示 12 周 Commit / 新开 PR 描述值；M1/M2 的输入特征按实验定义计算，PR 数值只作背景信息。当前生产准入模型数为 0。</p>
    </template>
  </div>
</template>

<style scoped>
.ml-data-page { display: grid; gap: 14px; }
.ml-context-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; color: var(--muted); font-size: 10.5px; }
.ml-evaluation { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.ml-model-card { display: grid; gap: 8px; min-height: 158px; align-content: start; }
.ml-card-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; color: var(--muted); font-size: 10px; }
.ml-card-result { color: var(--ink); font-size: 21px; letter-spacing: -.035em; font-variant-numeric: tabular-nums; }
.ml-model-card p { min-height: 32px; margin: 0; color: var(--ink); font-size: 10.5px; line-height: 1.5; }
.ml-model-card > small { color: var(--muted); font-size: 9.5px; line-height: 1.45; }
.ml-split-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; gap: 12px; }
.ml-split-panel { min-width: 0; padding: 0; overflow: hidden; }
.ml-split-heading { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 15px 16px 11px; }
.ml-split-heading h2 { margin: 0; font-size: 15px; }
.ml-split-heading p { margin: 4px 0 0; color: var(--muted); font-size: 10px; }
.ml-search { display: block; padding: 0 16px 10px; }
.ml-table-wrap { max-height: 580px; overflow: auto; border-top: 1px solid var(--line); }
.ml-table { min-width: 560px; }
.ml-table td:first-child { max-width: 195px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ml-table a { color: var(--ink); font-weight: 560; text-decoration: none; }
.ml-table a:hover { color: var(--primary); text-decoration: underline; }
.ml-table .numeric { text-align: right; font-variant-numeric: tabular-nums; }
.ml-empty { color: var(--muted); text-align: center; }
.ml-pagination { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 9px 12px; border-top: 1px solid var(--line); color: var(--muted); font-size: 10px; }
.ml-pagination > div { display: flex; align-items: center; gap: 5px; }
.ml-pagination :deep(.button) { min-height: 27px; padding: 0 7px; font-size: 9px; }
.ml-coverage-warning { padding: 9px 12px; border: 1px solid color-mix(in srgb, var(--amber) 35%, var(--line)); border-radius: var(--radius-sm); color: var(--muted); background: color-mix(in srgb, var(--amber) 7%, var(--surface)); font-size: 10px; }
.ml-note { display: flex; align-items: flex-start; gap: 7px; margin: 0; color: var(--muted); font-size: 10px; line-height: 1.55; }
.ml-note :deep(svg) { flex: 0 0 auto; margin-top: 1px; }
.ml-state { display: grid; justify-items: start; gap: 8px; color: var(--muted); font-size: 12px; }
.ml-state strong { color: var(--ink); }
.ml-state--error { border-color: color-mix(in srgb, var(--red) 35%, var(--line)); }
@media (max-width: 1000px) { .ml-evaluation { grid-template-columns: 1fr; } .ml-model-card { min-height: 0; } }
@media (max-width: 760px) { .ml-split-grid { grid-template-columns: 1fr; } }
</style>
