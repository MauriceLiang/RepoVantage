<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Info, RefreshCw } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import type { G2Spec } from '@antv/g2'
import G2Chart from '@/components/charts/G2Chart.vue'
import DonutChart from '@/components/charts/DonutChart.vue'
import RadarChart from '@/components/charts/RadarChart.vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiPageHeader from '@/components/ui/UiPageHeader.vue'
import UiPanel from '@/components/ui/UiPanel.vue'
import ResearchAtlasPage from './ResearchAtlasPage.vue'
import type { AtlasPoint, AtlasResponse, CourseMachineLearningEvaluation, CourseMlPerformance } from '@/data/researchTypes'
import { getBrowserApiData } from '@/services/httpRepositoryDataSource'
import { useUiStore } from '@/stores/ui'

const pageSize = 15
const route = useRoute()
const router = useRouter()
const showResearchDetails = computed(() => route.query.view === 'research')
const result = ref<AtlasResponse | null>(null)
const evaluation = ref<CourseMachineLearningEvaluation | null>(null)
const loading = ref(!showResearchDetails.value)
const error = ref('')
const evaluationError = ref('')
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
const ui = useUiStore()
const { theme } = storeToRefs(ui)
const m2Performance = computed(() => evaluation.value?.m2.selected_candidate ?? null)
const m2RadarDimensions = ['macro_f1', 'balanced_accuracy', 'up_precision', 'up_recall', 'up_f1']
const m2RadarLabels = ['Macro-F1', 'Balanced Accuracy', '上升 Precision', '上升 Recall', '上升 F1']
const m2RadarRows = computed(() => {
  const metrics = m2Performance.value
  if (!metrics) return []
  return [{
    model: metrics.label,
    macro_f1: Number((metrics.macro_f1 * 100).toFixed(1)),
    balanced_accuracy: Number((metrics.balanced_accuracy * 100).toFixed(1)),
    up_precision: Number((metrics.up_precision * 100).toFixed(1)),
    up_recall: Number((metrics.up_recall * 100).toFixed(1)),
    up_f1: Number((metrics.up_f1 * 100).toFixed(1)),
  }]
})
const m2ComparisonRows = computed(() => {
  const report = evaluation.value?.m2
  if (!report) return []
  const performances = [report.selected_candidate, ...report.baselines]
  const dimensions = [
    { key: 'macro_f1', label: 'Macro-F1' },
    { key: 'balanced_accuracy', label: 'Balanced Accuracy' },
    { key: 'up_precision', label: '上升 Precision' },
    { key: 'up_recall', label: '上升 Recall' },
  ] as const
  return performances.flatMap((performance) => dimensions.map((dimension) => ({
    metric: dimension.label,
    model: performance.label,
    value: Number((performance[dimension.key] * 100).toFixed(1)),
  })))
})
const confusionRows = computed(() => {
  const report = evaluation.value?.m2
  if (!report) return []
  return report.confusion_matrix.flatMap((row, actualIndex) => row.map((count, predictedIndex) => ({
    actual: report.confusion_matrix_labels[actualIndex],
    predicted: report.confusion_matrix_labels[predictedIndex],
    count,
  })))
})
const confusionSpec = computed<G2Spec>(() => ({
  type: 'cell',
  data: confusionRows.value,
  encode: { x: 'predicted', y: 'actual', color: 'count' },
  scale: { color: { range: theme.value === 'dark' ? ['#27313b', '#4d8ed6'] : ['#edf2f7', '#3574bd'] } },
  axis: { x: { title: '预测类别' }, y: { title: '真实类别' } },
  legend: { color: { title: '样本数' } },
  style: { inset: 2 },
  labels: [{ text: 'count', position: 'inside', fill: theme.value === 'dark' ? '#fff' : '#17212a', fontSize: 11 }],
  tooltip: { title: 'actual', items: [{ field: 'predicted', name: '预测类别' }, { field: 'count', name: '样本数' }] },
}))

function pct(value: number | undefined) {
  return value === undefined ? '—' : `${(value * 100).toFixed(1)}%`
}

function metricValue(performance: CourseMlPerformance | null, key: 'macro_f1' | 'balanced_accuracy' | 'up_precision' | 'up_recall' | 'up_f1') {
  const value = performance?.[key]
  return value === undefined ? '—' : `${(value * 100).toFixed(1)}%`
}

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
  evaluationError.value = ''
  try {
    const [atlasResult, evaluationResult] = await Promise.allSettled([
      getBrowserApiData<AtlasResponse>('/research/atlas?dataset_id=course-research-300-v1'),
      getBrowserApiData<CourseMachineLearningEvaluation>('/research/course-ml-evaluation'),
    ])
    if (atlasResult.status === 'rejected') throw atlasResult.reason
    result.value = atlasResult.value
    if (evaluationResult.status === 'fulfilled') evaluation.value = evaluationResult.value
    else {
      evaluation.value = null
      evaluationError.value = evaluationResult.reason instanceof Error ? evaluationResult.reason.message : '固定评估资料暂不可用'
    }
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

function toggleResearchDetails() {
  void router.push({ name: 'machine-learning-data', query: showResearchDetails.value ? {} : { view: 'research' } })
}

onMounted(() => { if (!showResearchDetails.value) void loadDataset() })
watch(showResearchDetails, (showDetails) => {
  if (!showDetails && !result.value && !loading.value) void loadDataset()
})
</script>

<template>
  <div class="app-page ml-data-page">
    <UiPageHeader :title="showResearchDetails ? '研究数据详情' : '机器学习数据'" :description="showResearchDetails ? '查看原研究中心的 300 仓库样本图谱、活动轨迹与分布分析。' : '300 个仓库按仓库 ID 固定分为训练组和留出测试组；两组名单、活动特征和模型评估分开展示。'">
      <template #actions>
        <UiButton variant="outline" @click="toggleResearchDetails">{{ showResearchDetails ? '返回机器学习数据' : '查看详细数据' }}</UiButton>
        <UiButton v-if="!showResearchDetails" variant="quiet" :loading="loading" @click="loadDataset"><RefreshCw :size="13" />刷新</UiButton>
      </template>
    </UiPageHeader>

    <ResearchAtlasPage v-if="showResearchDetails" :embedded="true" />
    <template v-else>
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

      <p class="ml-evaluation-notice"><Info :size="13" />图表展示固定版本 <strong>{{ evaluation?.dataset_version ?? 'course-150-150-v1' }}</strong> 的历史留出候选评估，数据截至 {{ evaluation?.data_as_of?.slice(0, 10) ?? '—' }}；不是当前生产模型，生产准入模型数为 0。</p>

      <section class="ml-evaluation" aria-label="模型历史评估">
        <UiPanel as="article" class="ml-model-card">
          <div class="ml-card-top"><span>M1 · 无监督聚类</span><UiBadge tone="accent">K-Means · K={{ evaluation?.m1.selected_k ?? '—' }}</UiBadge></div>
          <strong class="ml-card-result">测试轮廓系数 {{ evaluation?.m1.test_silhouette.toFixed(3) ?? '—' }}</strong>
          <p>训练 {{ evaluation?.m1.train_silhouette.toFixed(3) ?? '—' }} · 规模基线 {{ evaluation?.m1.size_only_test_silhouette.toFixed(3) ?? '—' }} · 10 个种子 ARI {{ evaluation?.m1.mean_seed_pairwise_ari.toFixed(3) ?? '—' }}</p>
          <small>描述近期提交模式；聚类不代表维护质量或健康度。</small>
        </UiPanel>
        <UiPanel as="article" class="ml-model-card">
          <div class="ml-card-top"><span>M2 · 未来 4 周趋势</span><UiBadge tone="accent">Logistic Regression</UiBadge></div>
          <strong class="ml-card-result">Macro-F1 {{ metricValue(m2Performance, 'macro_f1') }}</strong>
          <p>Balanced Accuracy {{ metricValue(m2Performance, 'balanced_accuracy') }} · 上升类 Recall {{ metricValue(m2Performance, 'up_recall') }}</p>
          <small>趋势类别仍有较多漏判；具体误差见留出混淆矩阵。</small>
        </UiPanel>
        <UiPanel as="article" class="ml-model-card ml-model-card--rule">
          <div class="ml-card-top"><span>M3 · 活动异常提示</span><UiBadge tone="neutral">统计规则</UiBadge></div>
          <strong class="ml-card-result">Median / MAD</strong>
          <p>{{ evaluation?.m3.rule ?? '以前 11 个完整周作为参照，达到稳健 Z 阈值时标记复核。' }}</p>
          <small>这是统计规则，不是训练出的异常分类器。</small>
        </UiPanel>
      </section>

      <section v-if="evaluation" class="ml-chart-grid" aria-label="机器学习评估图表">
        <UiPanel as="article" class="ml-chart-card ml-chart-card--radar">
          <header class="ml-chart-heading"><div><h2>M2 指标雷达图</h2><p>同一留出集；各项指标统一显示为百分比。</p></div><UiBadge tone="accent">候选模型</UiBadge></header>
          <RadarChart :rows="m2RadarRows" :dimensions="m2RadarDimensions" :dimension-labels="m2RadarLabels" series-field="model" label="M2 留出候选模型的五项分类指标雷达图，轴值为百分比" :height="300" />
          <div class="ml-radar-values"><span v-for="(label, index) in m2RadarLabels" :key="label">{{ label }} <strong>{{ pct([m2Performance?.macro_f1, m2Performance?.balanced_accuracy, m2Performance?.up_precision, m2Performance?.up_recall, m2Performance?.up_f1][index]) }}</strong></span></div>
        </UiPanel>

        <UiPanel as="article" class="ml-chart-card ml-chart-card--matrix">
          <header class="ml-chart-heading"><div><h2>M2 混淆矩阵</h2><p>行是真实类别，列是预测类别 · n={{ evaluation.m2.sample_count }}</p></div></header>
          <G2Chart :spec="confusionSpec" label="M2 候选模型在 150 个留出仓库上的混淆矩阵热力图" :height="300" />
        </UiPanel>

        <UiPanel as="article" class="ml-chart-card ml-chart-card--bars">
          <header class="ml-chart-heading"><div><h2>M2 候选与基线对比</h2><p>Macro-F1、Balanced Accuracy 与上升类 Precision / Recall。</p></div><span class="ml-unit-label">%</span></header>
          <G2Chart :spec="{
            type: 'interval', data: m2ComparisonRows, transform: [{ type: 'dodgeX' }],
            encode: { x: 'metric', y: 'value', color: 'model' },
            scale: { y: { domain: [0, 100] } },
            axis: { x: { labelAutoRotate: false }, y: { title: '百分比', min: 0, max: 100 } },
            legend: { color: { position: 'bottom' } },
            tooltip: { title: 'metric', items: [{ field: 'model', name: '模型' }, { field: 'value', name: '指标（%）' }] },
          } as G2Spec" label="M2 候选模型与两个基线的四项分类指标分组柱状图" :height="300" />
        </UiPanel>

        <UiPanel as="article" class="ml-chart-card ml-chart-card--labels">
          <header class="ml-chart-heading"><div><h2>留出集真实标签构成</h2><p>以 M2 测试目标的实际标签计数绘制。</p></div></header>
          <DonutChart :rows="Object.entries(evaluation.m2.actual_class_counts).map(([label, value]) => ({ label, value }))" :total="String(evaluation.m2.sample_count)" center-label="测试样本" label="M2 150 个留出测试样本的真实标签类别构成环形图" :height="245" />
        </UiPanel>

        <UiPanel as="article" class="ml-chart-card ml-chart-card--clusters">
          <header class="ml-chart-heading"><div><h2>M1 测试簇构成</h2><p>K={{ evaluation.m1.selected_k }} · 固定测试组。</p></div></header>
          <DonutChart :rows="evaluation.m1.cluster_counts.map((row) => ({ label: row.label, value: row.count }))" :total="String(evaluation.m1.test_repositories)" center-label="测试仓库" label="M1 留出测试组的 K-Means 簇构成环形图" :height="245" />
        </UiPanel>

        <UiPanel as="article" class="ml-chart-card ml-chart-card--anomaly">
          <header class="ml-chart-heading"><div><h2>M3 活动异常时间线</h2><p>Median / MAD 统计规则，不是训练出的异常分类器。</p></div><UiBadge tone="neutral">暂不可绘制</UiBadge></header>
          <div class="ml-timeline-empty"><Info :size="16" /><div><strong>{{ evaluation.m3.timeline_reason }}</strong><p>本页保留规则說明，不将一次性统计或缺失周数据伪装成时间序列。</p></div></div>
        </UiPanel>
      </section>
      <div v-else-if="evaluationError" class="ml-coverage-warning" role="status">评估图表暂不可用：{{ evaluationError }}；仓库名单仍可查看。</div>

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
    </template>
  </div>
</template>

<style scoped>
.ml-data-page { display: grid; gap: 14px; }
.ml-context-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; color: var(--muted); font-size: 10.5px; }
.ml-evaluation-notice { display: flex; align-items: flex-start; gap: 7px; margin: 0; color: var(--muted); font-size: 10px; line-height: 1.5; }
.ml-evaluation-notice :deep(svg) { flex: 0 0 auto; margin-top: 1px; }
.ml-evaluation-notice strong { color: var(--ink); }
.ml-evaluation { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.ml-model-card { display: grid; gap: 8px; min-height: 158px; align-content: start; }
.ml-card-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; color: var(--muted); font-size: 10px; }
.ml-card-result { color: var(--ink); font-size: 21px; letter-spacing: -.035em; font-variant-numeric: tabular-nums; }
.ml-model-card p { min-height: 32px; margin: 0; color: var(--ink); font-size: 10.5px; line-height: 1.5; }
.ml-model-card > small { color: var(--muted); font-size: 9.5px; line-height: 1.45; }
.ml-chart-grid { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 12px; }
.ml-chart-card { min-width: 0; padding: 12px; }
.ml-chart-card--radar { grid-column: span 7; }
.ml-chart-card--matrix { grid-column: span 5; }
.ml-chart-card--bars { grid-column: span 8; }
.ml-chart-card--labels, .ml-chart-card--clusters { grid-column: span 4; }
.ml-chart-card--anomaly { grid-column: span 8; }
.ml-chart-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; min-height: 37px; margin-bottom: 6px; }
.ml-chart-heading h2 { margin: 0; color: var(--ink); font-size: 12px; font-weight: 650; }
.ml-chart-heading p { margin: 3px 0 0; color: var(--muted); font-size: 9.5px; line-height: 1.45; }
.ml-unit-label { color: var(--muted); font-size: 10px; }
.ml-radar-values { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 6px; color: var(--muted); font-size: 8.5px; line-height: 1.4; }
.ml-radar-values span { display: grid; gap: 2px; }
.ml-radar-values strong { color: var(--ink); font-size: 10px; font-variant-numeric: tabular-nums; }
.ml-timeline-empty { display: flex; align-items: flex-start; gap: 9px; min-height: 102px; padding: 18px 12px; border: 1px dashed var(--line); border-radius: var(--radius-sm); color: var(--muted); background: var(--surface-2); font-size: 10px; line-height: 1.55; }
.ml-timeline-empty :deep(svg) { flex: 0 0 auto; margin-top: 1px; }
.ml-timeline-empty strong { color: var(--ink); font-weight: 560; }
.ml-timeline-empty p { margin: 5px 0 0; }
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
@media (max-width: 1000px) { .ml-evaluation { grid-template-columns: 1fr; } .ml-model-card { min-height: 0; } .ml-chart-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .ml-chart-card--radar, .ml-chart-card--matrix, .ml-chart-card--bars, .ml-chart-card--labels, .ml-chart-card--clusters, .ml-chart-card--anomaly { grid-column: span 1; } }
@media (max-width: 760px) { .ml-split-grid, .ml-chart-grid { grid-template-columns: 1fr; } .ml-chart-card--radar, .ml-chart-card--matrix, .ml-chart-card--bars, .ml-chart-card--labels, .ml-chart-card--clusters, .ml-chart-card--anomaly { grid-column: 1; } .ml-radar-values { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
</style>
