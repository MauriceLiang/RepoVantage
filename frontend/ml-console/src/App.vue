<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

type Score = { macro_f1: number | null; balanced_accuracy: number | null }
type Benchmark = {
  id: string
  name: string
  selected: boolean
  validation: Score
  test: Score
}
type TestScatterPoint = {
  repository_id: number
  repository: string
  cluster_id: string
  cluster_name: string | null
  active_week_ratio: number
  no_commit_week_ratio: number
  commits_12w: number | null
}
type ValidationPoint = {
  label: string
  as_of: string
  samples: number | null
  macro_f1: number | null
  baseline_macro_f1: number | null
  balanced_accuracy: number | null
  baseline_balanced_accuracy: number | null
}
type ModelEvaluation = {
  id: 'M1' | 'M2'
  name: string
  version: string
  algorithm: string
  kind: string
  feature_schema_version: string
  samples: Record<string, number | null>
  selected_clusters?: number
  silhouette?: { train: number | null; seed_mean: number | null; test: number | null }
  size_only_train_silhouette?: number | null
  test_clusters?: { id: string; name: string | null; repositories: number }[]
  test_points?: TestScatterPoint[]
  candidates?: { clusters: number; train_silhouette: number | null; size_only_train_silhouette: number | null; seed_silhouette_mean: number | null; selected: boolean }[]
  validation?: Score
  test?: Score
  test_confusion_matrix?: { labels: string[]; values: number[][] } | null
  benchmarks?: Benchmark[]
  validation_series?: ValidationPoint[]
  label_definition?: string
  notes?: string[]
}
type Dashboard = {
  status: 'available' | 'unavailable'
  reason?: string
  dataset?: {
    id: string
    status: string
    repositories: number
    weekly_rows: number
    weeks_per_repository: number
    split: { train: number; validation: number | null; test: number }
    split_version?: string | null
    feature_schema_version: string
    source_sha256: string
    scope: string
  }
  models?: ModelEvaluation[]
}
type ModelStatus = { model_id: string; status: string; reason: string; version?: string | null; loaded_status?: string | null }[]
type Monitoring = { counters: Record<string, number>; latency_ms_p50: number | null; latency_ms_p95: number | null; latency_samples: number; peak_rss_bytes_max: number | null; cache_entries: number; note: string }
type Envelope<T> = { data: T }

const dashboard = ref<Dashboard | null>(null)
const statuses = ref<ModelStatus>([])
const monitoring = ref<Monitoring | null>(null)
const loading = ref(true)
const loadError = ref('')
const activeModel = ref<'M1' | 'M2'>('M1')

const selectedModel = computed(() => dashboard.value?.models?.find((model) => model.id === activeModel.value) ?? null)
const testTotal = computed(() => dashboard.value?.dataset?.split.test ?? 0)
const clusterTicks = [0, 0.25, 0.5, 0.75, 1]

const testScatterPoints = computed(() => {
  const model = selectedModel.value
  if (model?.id !== 'M1') return []
  const offsets = new Map<string, number>()
  return (model.test_points ?? []).map((point) => {
    const rawX = 72 + point.active_week_ratio * 468
    const rawY = 290 - point.no_commit_week_ratio * 260
    const coordinateKey = `${point.active_week_ratio.toFixed(4)}:${point.no_commit_week_ratio.toFixed(4)}`
    const offsetIndex = offsets.get(coordinateKey) ?? 0
    offsets.set(coordinateKey, offsetIndex + 1)
    const angle = offsetIndex * 2.3999632297
    const distance = offsetIndex === 0 ? 0 : Math.min(12, 2 + Math.sqrt(offsetIndex) * 1.6)
    return {
      ...point,
      cx: Math.max(72, Math.min(540, rawX + Math.cos(angle) * distance)),
      cy: Math.max(30, Math.min(290, rawY + Math.sin(angle) * distance)),
    }
  })
})

const trendChartRows = computed(() => {
  const model = selectedModel.value
  if (model?.id !== 'M2') return []
  return (model.validation_series ?? []).map((point, index) => {
    const currentX = trendScoreX(point.macro_f1)
    const baselineX = trendScoreX(point.baseline_macro_f1)
    const y = 44 + index * 74
    return { ...point, currentX, baselineX, currentY: y, baselineY: y + 19 }
  })
})

function trendScoreX(value: number | null | undefined) {
  return 194 + Math.max(0, Math.min(0.65, value ?? 0)) / 0.65 * 456
}

function clusterColor(id: string) {
  const colors: Record<string, string> = { '0': '#4878d0', '1': '#49a195', '2': '#e4a047', '3': '#cc6786' }
  return colors[id] ?? '#7b8794'
}

function confusionRowTotal(rowIndex: number) {
  return selectedModel.value?.test_confusion_matrix?.values[rowIndex]?.reduce((sum, value) => sum + value, 0) ?? 0
}

function confusionCellStyle(value: number, rowIndex: number) {
  const total = confusionRowTotal(rowIndex)
  const opacity = total > 0 ? 0.07 + value / total * 0.48 : 0.07
  return { backgroundColor: `rgba(53,116,232,${opacity})` }
}

async function getData<T>(path: string): Promise<T> {
  const response = await fetch(`/api/browser/v1${path}`, {
    credentials: 'same-origin',
    headers: { 'X-GDA-Request': 'browser', Accept: 'application/json' },
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { error?: { message?: string } }
    throw new Error(payload.error?.message ?? `请求失败（${response.status}）`)
  }
  const payload = await response.json() as Envelope<T>
  return payload.data
}

async function connect() {
  loading.value = true
  loadError.value = ''
  try {
    const session = await fetch('/api/browser/session', {
      credentials: 'same-origin',
      headers: { 'X-GDA-Request': 'browser' },
    })
    if (!session.ok) throw new Error('无法建立本机浏览器会话，请确认主站正在 8501 端口运行。')
    const [evaluation, modelStatus, modelMonitoring] = await Promise.all([
      getData<Dashboard>('/models/evaluation'),
      getData<{ models: ModelStatus }>('/models/status'),
      getData<Monitoring>('/models/monitoring'),
    ])
    dashboard.value = evaluation
    statuses.value = modelStatus.models ?? []
    monitoring.value = modelMonitoring
    if (evaluation.status !== 'available') loadError.value = evaluation.reason ?? '模型评估数据暂不可用。'
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '读取机器学习评估数据失败。'
  } finally {
    loading.value = false
  }
}

function percent(value: number | null | undefined) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`
}

function scoreWidth(value: number | null | undefined) {
  return `${Math.max(0, Math.min(100, (value ?? 0) * 100))}%`
}

function silhouetteWidth(value: number | null | undefined) {
  return `${Math.max(0, Math.min(100, ((value ?? -1) + 1) * 50))}%`
}

function count(value: number | null | undefined) {
  return value == null ? '—' : new Intl.NumberFormat('zh-CN').format(value)
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    available: '评估文件可用',
    research_only: '仅研究使用',
    disabled: '已停用',
    shadow: '影子验证',
    canary: '小流量验证',
    active: '运行中',
    model_unavailable: '模型文件不可用',
    baseline_only: '统计基线',
  }
  return labels[status] ?? status
}

onMounted(connect)
</script>

<template>
  <main class="shell">
    <header class="topbar">
      <a class="brand" href="/" aria-label="机器学习观测台首页">
        <span class="brand-mark">RV</span>
        <span><strong>RepoVantage</strong><small>机器学习观测台</small></span>
      </a>
      <div class="topbar-actions">
        <span class="port-label">研究环境 · 8502</span>
        <a class="main-link" href="http://127.0.0.1:8501/">返回用户主站 <span aria-hidden="true">↗</span></a>
        <button class="refresh" type="button" :disabled="loading" @click="connect">{{ loading ? '读取中…' : '刷新评估' }}</button>
      </div>
    </header>

    <section class="intro">
      <div class="intro-copy">
        <h1>模型评估与运行观测</h1>
        <p>集中查看离线评估、拟合与泛化表现、基线对比，以及当前运行状态。</p>
      </div>
      <div class="intro-badge"><span class="badge-dot"></span>研究评估数据，不代表仓库质量</div>
    </section>

    <div v-if="loadError" class="notice" role="status">
      <span class="notice-icon">!</span>
      <div><strong>暂时无法读取模型数据</strong><p>{{ loadError }}</p></div>
      <button type="button" @click="connect">重试</button>
    </div>

    <template v-if="dashboard?.status === 'available' && dashboard.dataset">
      <section class="summary-grid" aria-label="评估数据概览">
        <article class="summary-card"><span class="summary-label">研究仓库</span><strong>{{ count(dashboard.dataset.repositories) }}</strong><span class="summary-foot">固定研究样本</span></article>
        <article class="summary-card"><span class="summary-label">周级观测</span><strong>{{ count(dashboard.dataset.weekly_rows) }}</strong><span class="summary-foot">每仓 {{ dashboard.dataset.weeks_per_repository }} 周</span></article>
        <article class="summary-card"><span class="summary-label">独立留出仓库</span><strong>{{ count(testTotal) }}</strong><span class="summary-foot">用于最终泛化评估</span></article>
        <article class="summary-card"><span class="summary-label">当前研究模型</span><strong>{{ dashboard.models?.length ?? 0 }} <small>个</small></strong><span class="summary-foot">M1 聚类 · M2 趋势分类</span></article>
      </section>

      <section class="dataset-card">
        <div class="section-heading"><div><h2>数据集与验证切分</h2><p class="section-description">固定研究样本与训练、验证、留出集的划分方式</p></div><span class="version-pill">{{ dashboard.dataset.id }}</span></div>
        <div class="split-row">
          <div class="split-item"><span>训练集 · M1</span><strong>{{ dashboard.dataset.split.train }}</strong><small>仓库</small></div>
          <div class="split-item"><span>验证集 · M1</span><strong>{{ dashboard.dataset.split.validation ?? '—' }}</strong><small>{{ dashboard.dataset.split.validation == null ? '固定切分未单列' : '仓库' }}</small></div>
          <div class="split-item"><span>留出集 · M1</span><strong>{{ dashboard.dataset.split.test }}</strong><small>仓库</small></div>
          <div class="split-track" aria-hidden="true"><span :style="{ width: `${dashboard.dataset.split.train / dashboard.dataset.repositories * 100}%` }"></span><span :style="{ width: `${(dashboard.dataset.split.validation ?? 0) / dashboard.dataset.repositories * 100}%` }"></span><span :style="{ width: `${dashboard.dataset.split.test / dashboard.dataset.repositories * 100}%` }"></span></div>
        </div>
        <div class="dataset-foot"><span>特征规范 <code>{{ dashboard.dataset.feature_schema_version }}</code></span><span>样本划分 <code>{{ dashboard.dataset.split_version ?? '未注明' }}</code></span><span>来源指纹 <code>{{ dashboard.dataset.source_sha256?.slice(0, 16) }}…</code></span></div>
        <p class="scope-note">{{ dashboard.dataset.scope }} 本页按冻结的 150 / 150 分组展示：M1 用 150 个仓库训练、150 个独立留出；M2 在训练组内滚动验证，并用同一留出组做最终测试。</p>
      </section>

      <section class="evaluation-card">
        <div class="section-heading evaluation-heading">
          <div><h2>模型拟合与泛化表现</h2><p class="section-description">查看训练结果、验证表现与独立留出集上的模型输出</p></div>
          <div class="model-switch" role="group" aria-label="选择模型">
            <button v-for="model in dashboard.models" :key="model.id" type="button" :aria-pressed="activeModel === model.id" :class="{ active: activeModel === model.id }" @click="activeModel = model.id">{{ model.id }} <span>{{ model.name }}</span></button>
          </div>
        </div>

        <template v-if="selectedModel?.id === 'M1'">
          <div class="model-meta"><span class="model-kind">{{ selectedModel.kind }}</span><strong>{{ selectedModel.name }}</strong><span>{{ selectedModel.algorithm }} · {{ selectedModel.version }}</span><span class="meta-divider"></span><span>选择 {{ selectedModel.selected_clusters }} 个活动模式</span></div>
          <div class="metric-grid silhouette-grid">
            <article v-for="item in [{ key: 'train', label: '训练集' }, { key: 'seed_mean', label: '训练多随机种子均值' }, { key: 'test', label: '150 个独立留出仓库' }]" :key="item.key" class="metric-card">
              <div class="metric-card-head"><span>{{ item.label }}轮廓系数</span><strong>{{ selectedModel.silhouette?.[item.key as 'train' | 'seed_mean' | 'test']?.toFixed(3) ?? '—' }}</strong></div>
              <div class="metric-track silhouette-track"><span aria-hidden="true"></span><i :style="{ width: silhouetteWidth(selectedModel.silhouette?.[item.key as 'train' | 'seed_mean' | 'test']) }"></i></div>
              <small>{{ item.key === 'seed_mean' ? '多个随机初始化的均值，用于观察聚类稳定性' : '范围 −1 至 1，越高通常表示簇内更紧密、簇间更分离' }}</small>
            </article>
          </div>
          <div class="detail-panel profile-chart-panel">
            <div class="panel-heading">
              <div><h3>独立测试集的模型聚类结果</h3><p>每个点是一个留出仓库；位置是实际特征值，颜色是训练后模型给出的簇标签。</p></div>
              <span>{{ selectedModel.samples.test_repositories }} 个留出仓库 · {{ testScatterPoints.length }} 个可绘点</span>
            </div>
            <div class="chart-legend scatter-legend" aria-label="模型预测簇分布">
              <span v-for="cluster in selectedModel.test_clusters" :key="cluster.id"><i :style="{ backgroundColor: clusterColor(cluster.id) }"></i>{{ cluster.name ?? `簇 ${cluster.id}` }} · n={{ cluster.repositories }}</span>
            </div>
            <div v-if="testScatterPoints.length" class="chart-frame">
              <svg class="profile-chart" viewBox="0 0 680 380" role="img" aria-labelledby="m1-chart-title m1-chart-desc">
                <title id="m1-chart-title">K-Means 模型在独立测试集上的簇分配</title>
                <desc id="m1-chart-desc">散点展示固定留出测试集中的仓库真实输入特征，点颜色表示已训练 K-Means 模型预测的簇标签。此处不展示实时仓库数据。</desc>
                <g class="chart-grid">
                  <g v-for="tick in clusterTicks" :key="`x-${tick}`">
                    <line x1="72" x2="540" :y1="290 - tick * 260" :y2="290 - tick * 260" />
                    <text x="60" :y="294 - tick * 260" text-anchor="end">{{ Math.round(tick * 100) }}%</text>
                    <line :x1="72 + tick * 468" :x2="72 + tick * 468" y1="30" y2="290" />
                    <text :x="72 + tick * 468" y="310" text-anchor="middle">{{ Math.round(tick * 100) }}%</text>
                  </g>
                </g>
                <text class="chart-axis-title" x="306" y="354" text-anchor="middle">活跃周占比</text>
                <text class="chart-axis-title" x="18" y="160" text-anchor="middle" transform="rotate(-90 18 160)">最长连续无提交周占比</text>
                <g v-for="point in testScatterPoints" :key="point.repository_id" class="test-scatter-point">
                  <circle :cx="point.cx" :cy="point.cy" r="4.5" :fill="clusterColor(point.cluster_id)">
                    <title>{{ point.repository }} · {{ point.cluster_name ?? `簇 ${point.cluster_id}` }}：活跃周占比 {{ percent(point.active_week_ratio) }}，最长连续无提交周占比 {{ percent(point.no_commit_week_ratio) }}，12 周提交 {{ count(point.commits_12w) }}</title>
                  </circle>
                </g>
              </svg>
            </div>
            <div v-else class="chart-empty">评估文件中没有可绘制的留出集模型预测结果。</div>
            <p class="chart-caption">这里只绘制冻结留出集上的模型预测，不是线上仓库当前状态。相同坐标的点会做轻微错位以便辨认；悬停可查看原始特征值。</p>
          </div>
          <div class="detail-grid">
            <div class="detail-panel">
              <div class="panel-heading"><h3>不同簇数的训练表现</h3><span>150 个训练仓库 · 随机种子稳定性</span></div>
              <div class="candidate-table-wrap"><span class="table-scroll-hint">可横向滑动查看完整数据</span><table class="candidate-table"><thead><tr><th>簇数 K</th><th>聚类模型</th><th>仅按提交规模</th><th>差值</th><th>多种子均值</th></tr></thead><tbody><tr v-for="item in selectedModel.candidates" :key="item.clusters" :class="{ chosen: item.selected }"><td><strong>K={{ item.clusters }}</strong><span v-if="item.selected" class="chosen-tag">当前</span></td><td>{{ item.train_silhouette?.toFixed(3) ?? '—' }}</td><td>{{ item.size_only_train_silhouette?.toFixed(3) ?? '—' }}</td><td>{{ item.train_silhouette != null && item.size_only_train_silhouette != null ? `+${(item.train_silhouette - item.size_only_train_silhouette).toFixed(3)}` : '—' }}</td><td>{{ item.seed_silhouette_mean?.toFixed(3) ?? '—' }}</td></tr></tbody></table></div>
            </div>
            <div class="detail-panel">
              <div class="panel-heading"><h3>留出集簇分布</h3><span>{{ selectedModel.samples.test_repositories }} 个仓库</span></div>
              <div class="cluster-list"><div v-for="cluster in selectedModel.test_clusters" :key="cluster.id" class="cluster-row"><span class="cluster-name"><i :class="`cluster-color color-${cluster.id}`"></i>{{ cluster.name ?? `簇 ${cluster.id}` }}</span><div class="cluster-track"><i :class="`color-${cluster.id}`" :style="{ width: `${cluster.repositories / (selectedModel.samples.test_repositories ?? 1) * 100}%` }"></i></div><strong>{{ cluster.repositories }}</strong></div></div>
            </div>
          </div>
          <div class="caveat-line"><strong>解读：</strong>训练集轮廓系数 {{ selectedModel.silhouette?.train?.toFixed(3) ?? '—' }}，多随机种子均值 {{ selectedModel.silhouette?.seed_mean?.toFixed(3) ?? '—' }}；独立 150 仓库留出集为 {{ selectedModel.silhouette?.test?.toFixed(3) ?? '—' }}。轮廓系数反映聚类结构，不是趋势预测准确率，也不能说明仓库优劣。</div>
        </template>

        <template v-else-if="selectedModel?.id === 'M2'">
          <div class="model-meta"><span class="model-kind">{{ selectedModel.kind }}</span><strong>{{ selectedModel.name }}</strong><span>{{ selectedModel.algorithm }} · {{ selectedModel.version }}</span><span class="meta-divider"></span><span>训练组 {{ selectedModel.samples.training_repositories }} 仓库 · 组内滚动验证 {{ selectedModel.samples.validation_folds }} 折（每折 {{ selectedModel.samples.validation_samples_per_fold }} 个样本） · 独立测试 {{ selectedModel.samples.test_repositories }} 仓库</span></div>
          <div class="m2-summary">
            <article class="m2-score"><span>滚动验证 Macro-F1</span><strong>{{ percent(selectedModel.validation?.macro_f1) }}</strong><small>训练组内 {{ selectedModel.samples.validation_folds }} 个窗口 · 每折 {{ selectedModel.samples.validation_samples_per_fold }} 个样本</small></article>
            <article class="m2-score m2-score--accent"><span>独立测试 Macro-F1</span><strong>{{ percent(selectedModel.test?.macro_f1) }}</strong><small>{{ selectedModel.samples.test_repositories }} 个留出仓库</small></article>
            <article class="m2-score"><span>测试集平衡准确率</span><strong>{{ percent(selectedModel.test?.balanced_accuracy) }}</strong><small>按类别召回率取平均</small></article>
            <article class="m2-score"><span>测试集对近期趋势基线</span><strong>+{{ (((selectedModel.test?.macro_f1 ?? 0) - (selectedModel.benchmarks?.find((item) => item.id === 'recent_trend_baseline')?.test.macro_f1 ?? 0)) * 100).toFixed(1) }} <small>分</small></strong><small>Macro-F1 绝对差</small></article>
          </div>
          <div class="detail-panel trend-chart-panel">
            <div class="panel-heading">
              <div><h3>滚动验证与独立测试：Macro-F1</h3><p>横向比较每个数据切分上的逻辑回归与近期趋势基线。</p></div>
              <span>越高越好 · 0–65%</span>
            </div>
            <div class="chart-legend" aria-label="图例">
              <span><i class="legend-current"></i>{{ selectedModel.algorithm }}（当前候选）</span>
              <span><i class="legend-baseline"></i>近期趋势基线</span>
            </div>
            <div v-if="trendChartRows.length" class="chart-frame trend-chart-frame">
              <svg class="trend-chart" viewBox="0 0 720 302" role="img" aria-labelledby="m2-chart-title m2-chart-desc">
                <title id="m2-chart-title">近期活动趋势模型的 Macro-F1 基线对比</title>
                <desc id="m2-chart-desc">并列水平条比较当前逻辑回归与近期趋势基线在两个滚动验证折和独立测试集上的 Macro-F1。每一行是一个独立评估切分，不表示连续时间趋势。</desc>
                <g class="chart-grid trend-grid">
                  <g v-for="tick in [0, 0.2, 0.4, 0.6]" :key="tick">
                    <line :x1="trendScoreX(tick)" :x2="trendScoreX(tick)" y1="26" y2="266" />
                    <text :x="trendScoreX(tick)" y="287" text-anchor="middle">{{ percent(tick) }}</text>
                  </g>
                </g>
                <g v-for="row in trendChartRows" :key="row.label" class="trend-row">
                  <text class="trend-row-title" x="8" :y="row.currentY + 7">{{ row.label }}</text>
                  <text class="trend-row-meta" x="8" :y="row.currentY + 23">{{ row.as_of }} · n={{ row.samples ?? '—' }}</text>
                  <rect v-if="row.macro_f1 != null" class="trend-bar trend-bar-current" x="194" :y="row.currentY" :width="Math.max(1, row.currentX - 194)" height="12" rx="4">
                    <title>{{ row.label }} · 当前候选：Macro-F1 {{ percent(row.macro_f1) }}</title>
                  </rect>
                  <text v-if="row.macro_f1 != null" class="trend-value" :x="row.currentX + 8" :y="row.currentY + 10">{{ percent(row.macro_f1) }}</text>
                  <rect v-if="row.baseline_macro_f1 != null" class="trend-bar trend-bar-baseline" x="194" :y="row.baselineY" :width="Math.max(1, row.baselineX - 194)" height="12" rx="4">
                    <title>{{ row.label }} · 近期趋势基线：Macro-F1 {{ percent(row.baseline_macro_f1) }}</title>
                  </rect>
                  <text v-if="row.baseline_macro_f1 != null" class="trend-value" :x="row.baselineX + 8" :y="row.baselineY + 10">{{ percent(row.baseline_macro_f1) }}</text>
                </g>
              </svg>
            </div>
            <div v-else class="chart-empty">当前评估文件没有可绘制的逐折结果。</div>
            <p class="chart-caption">各行代表不同验证/测试样本，不应解读为模型随时间升降；独立测试用于最终留出评估。Macro-F1 是三类 F1 的宏平均。</p>
          </div>
          <div class="detail-grid m2-detail-grid">
            <div class="detail-panel">
              <div class="panel-heading"><h3>基线对比</h3><span>越高越好 · 0–100%</span></div>
              <div class="benchmark-table-wrap"><span class="table-scroll-hint">可横向滑动查看完整数据</span><table class="benchmark-table"><thead><tr><th>模型</th><th>验证 Macro-F1</th><th>测试 Macro-F1</th><th>测试平衡准确率</th></tr></thead><tbody><tr v-for="item in selectedModel.benchmarks" :key="item.id" :class="{ chosen: item.selected }"><td>{{ item.name }}<span v-if="item.selected" class="chosen-tag">当前</span></td><td><div class="table-score"><span>{{ percent(item.validation.macro_f1) }}</span><i><b :style="{ width: scoreWidth(item.validation.macro_f1) }"></b></i></div></td><td><div class="table-score"><span>{{ percent(item.test.macro_f1) }}</span><i><b :style="{ width: scoreWidth(item.test.macro_f1) }"></b></i></div></td><td>{{ percent(item.test.balanced_accuracy) }}</td></tr></tbody></table></div>
            </div>
            <div class="detail-panel">
              <div class="panel-heading"><h3>独立测试集预测结果</h3><span>真实类别 × 模型预测 · 行内占比</span></div>
              <div v-if="selectedModel.test_confusion_matrix" class="matrix-wrap"><table class="matrix-table"><thead><tr><th>真实 \ 预测</th><th v-for="label in selectedModel.test_confusion_matrix.labels" :key="label">{{ label }}</th></tr></thead><tbody><tr v-for="(row, rowIndex) in selectedModel.test_confusion_matrix.values" :key="rowIndex"><th>{{ selectedModel.test_confusion_matrix.labels[rowIndex] }}</th><td v-for="(value, colIndex) in row" :key="colIndex" :class="{ diagonal: rowIndex === colIndex }" :style="confusionCellStyle(value, rowIndex)"><strong>{{ value }}</strong><small>{{ percent(confusionRowTotal(rowIndex) ? value / confusionRowTotal(rowIndex) : null) }}</small></td></tr></tbody></table></div>
              <p class="matrix-caption">每行按真实类别归一为 100%；对角线表示分类正确。数据来自独立 150 仓库留出测试，不是线上仓库状态。</p>
            </div>
          </div>
          <div class="caveat-line"><strong>标签定义：</strong>{{ selectedModel.label_definition }} <span v-for="note in selectedModel.notes" :key="note">{{ note }}</span></div>
        </template>
      </section>

      <section class="runtime-card">
        <div class="section-heading"><div><h2>评估模型与运行诊断</h2><p class="section-description">研究模型文件状态与当前进程内推理指标</p></div><span class="live-pill"><i></i>当前进程</span></div>
        <div class="runtime-grid">
          <article v-for="model in statuses" :key="model.model_id" class="runtime-model">
            <div class="runtime-title"><span>{{ model.model_id }}</span><strong>{{ model.version ?? '未绑定版本' }}</strong></div>
            <span class="runtime-status" :class="`state-${model.status}`">{{ statusLabel(model.status) }}</span>
            <p>{{ model.reason }}</p>
          </article>
          <article class="runtime-model runtime-model--metrics">
            <div class="runtime-title"><span>推理诊断</span><strong>{{ monitoring?.latency_samples ?? 0 }} 条耗时</strong></div>
            <div class="runtime-kpis"><span>P50 <strong>{{ monitoring?.latency_ms_p50 == null ? '—' : `${monitoring.latency_ms_p50.toFixed(1)} ms` }}</strong></span><span>P95 <strong>{{ monitoring?.latency_ms_p95 == null ? '—' : `${monitoring.latency_ms_p95.toFixed(1)} ms` }}</strong></span><span>峰值内存 <strong>{{ monitoring?.peak_rss_bytes_max == null ? '—' : `${(monitoring.peak_rss_bytes_max / 1024 / 1024).toFixed(1)} MB` }}</strong></span></div>
            <p>{{ monitoring?.note ?? '进程内统计；重启后清空。' }}</p>
          </article>
        </div>
        <p class="runtime-footnote">研究评估模型与在线推理注册表是两套状态：评估可用不代表已批准上线；运行指标仅反映当前进程，不是服务等级监控。</p>
      </section>
    </template>
    <div v-else-if="loading" class="loading-card"><span class="spinner"></span><strong>正在读取评估数据</strong><span>连接本机 API 与模型注册表</span></div>

    <footer class="page-footer"><span>RepoVantage · 机器学习研究评估</span><span>用户主站 <a href="http://127.0.0.1:8501/">127.0.0.1:8501</a> <b>·</b> ML 控制台 127.0.0.1:8502</span></footer>
  </main>
</template>

<style scoped>
.silhouette-track{position:relative}
.silhouette-track>span{position:absolute;z-index:1;top:-2px;bottom:-2px;left:50%;width:1px;background:#fff;box-shadow:0 0 0 1px rgba(70,92,118,.35)}
.silhouette-track>i{position:relative}
</style>
