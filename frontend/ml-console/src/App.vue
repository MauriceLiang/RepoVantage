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
type ModelEvaluation = {
  id: 'M1' | 'M2'
  name: string
  version: string
  algorithm: string
  kind: string
  feature_schema_version: string
  samples: Record<string, number | null>
  selected_clusters?: number
  silhouette?: { train: number | null; validation: number | null; test: number | null }
  size_only_validation_silhouette?: number | null
  test_clusters?: { id: string; name: string | null; repositories: number }[]
  candidates?: { clusters: number; validation_silhouette: number | null; size_only_validation_silhouette: number | null; selected: boolean }[]
  validation?: Score
  test?: Score
  test_confusion_matrix?: { labels: string[]; values: number[][] } | null
  benchmarks?: Benchmark[]
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
    split: { train: number; validation: number; test: number }
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
    available: '可用于推理',
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
        <span class="port-label"><i></i>独立前端 · 8502</span>
        <a class="main-link" href="http://127.0.0.1:8501/">返回用户主站 <span aria-hidden="true">↗</span></a>
        <button class="refresh" type="button" :disabled="loading" @click="connect">{{ loading ? '读取中…' : '刷新评估' }}</button>
      </div>
    </header>

    <section class="intro">
      <div class="intro-copy">
        <p class="eyebrow">MODEL OBSERVABILITY <span>·</span> INTERNAL CONSOLE</p>
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
        <div class="section-heading"><div><p class="eyebrow">DATASET / PROVENANCE</p><h2>数据集与验证切分</h2></div><span class="version-pill">{{ dashboard.dataset.id }}</span></div>
        <div class="split-row">
          <div class="split-item"><span>训练集 · M1</span><strong>{{ dashboard.dataset.split.train }}</strong><small>仓库</small></div>
          <div class="split-item"><span>验证集 · M1</span><strong>{{ dashboard.dataset.split.validation }}</strong><small>仓库</small></div>
          <div class="split-item"><span>留出集 · M1</span><strong>{{ dashboard.dataset.split.test }}</strong><small>仓库</small></div>
          <div class="split-track" aria-hidden="true"><span :style="{ width: `${dashboard.dataset.split.train / dashboard.dataset.repositories * 100}%` }"></span><span :style="{ width: `${dashboard.dataset.split.validation / dashboard.dataset.repositories * 100}%` }"></span><span :style="{ width: `${dashboard.dataset.split.test / dashboard.dataset.repositories * 100}%` }"></span></div>
        </div>
        <div class="dataset-foot"><span>特征规范 <code>{{ dashboard.dataset.feature_schema_version }}</code></span><span>来源指纹 <code>{{ dashboard.dataset.source_sha256?.slice(0, 16) }}…</code></span></div>
        <p class="scope-note">{{ dashboard.dataset.scope }} M1 使用固定 train / validation / test 切分；M2 另按时间窗口滚动验证并对 45 个仓库做留出评估。</p>
      </section>

      <section class="evaluation-card">
        <div class="section-heading evaluation-heading">
          <div><p class="eyebrow">OFFLINE EVALUATION</p><h2>模型拟合与泛化表现</h2></div>
          <div class="model-switch" role="group" aria-label="选择模型">
            <button v-for="model in dashboard.models" :key="model.id" type="button" :aria-pressed="activeModel === model.id" :class="{ active: activeModel === model.id }" @click="activeModel = model.id">{{ model.id }} <span>{{ model.name }}</span></button>
          </div>
        </div>

        <template v-if="selectedModel?.id === 'M1'">
          <div class="model-meta"><span class="model-kind">{{ selectedModel.kind }}</span><strong>{{ selectedModel.name }}</strong><span>{{ selectedModel.algorithm }} · {{ selectedModel.version }}</span><span class="meta-divider"></span><span>选择 {{ selectedModel.selected_clusters }} 个活动模式</span></div>
          <div class="metric-grid silhouette-grid">
            <article v-for="item in [{ key: 'train', label: '训练集' }, { key: 'validation', label: '验证集' }, { key: 'test', label: '独立留出集' }]" :key="item.key" class="metric-card">
              <div class="metric-card-head"><span>{{ item.label }}轮廓系数</span><strong>{{ selectedModel.silhouette?.[item.key as 'train' | 'validation' | 'test']?.toFixed(3) ?? '—' }}</strong></div>
              <div class="metric-track silhouette-track"><span aria-hidden="true"></span><i :style="{ width: silhouetteWidth(selectedModel.silhouette?.[item.key as 'train' | 'validation' | 'test']) }"></i></div>
              <small>范围 −1 至 1，越高通常表示簇内更紧密、簇间更分离</small>
            </article>
          </div>
          <div class="detail-grid">
            <div class="detail-panel">
              <div class="panel-heading"><h3>不同簇数的验证表现</h3><span>对比仅按提交规模分组</span></div>
              <div class="candidate-table-wrap"><table class="candidate-table"><thead><tr><th>簇数 K</th><th>聚类模型</th><th>仅按规模</th><th>差值</th></tr></thead><tbody><tr v-for="item in selectedModel.candidates" :key="item.clusters" :class="{ chosen: item.selected }"><td><strong>K={{ item.clusters }}</strong><span v-if="item.selected" class="chosen-tag">当前</span></td><td>{{ item.validation_silhouette?.toFixed(3) ?? '—' }}</td><td>{{ item.size_only_validation_silhouette?.toFixed(3) ?? '—' }}</td><td>{{ item.validation_silhouette != null && item.size_only_validation_silhouette != null ? `+${(item.validation_silhouette - item.size_only_validation_silhouette).toFixed(3)}` : '—' }}</td></tr></tbody></table></div>
            </div>
            <div class="detail-panel">
              <div class="panel-heading"><h3>留出集簇分布</h3><span>{{ selectedModel.samples.test_repositories }} 个仓库</span></div>
              <div class="cluster-list"><div v-for="cluster in selectedModel.test_clusters" :key="cluster.id" class="cluster-row"><span class="cluster-name"><i :class="`cluster-color color-${cluster.id}`"></i>{{ cluster.name ?? `簇 ${cluster.id}` }}</span><div class="cluster-track"><i :class="`color-${cluster.id}`" :style="{ width: `${cluster.repositories / (selectedModel.samples.test_repositories ?? 1) * 100}%` }"></i></div><strong>{{ cluster.repositories }}</strong></div></div>
            </div>
          </div>
          <div class="caveat-line"><strong>解读：</strong>训练与验证轮廓系数相差 {{ selectedModel.silhouette?.train != null && selectedModel.silhouette?.validation != null ? Math.abs(selectedModel.silhouette.train - selectedModel.silhouette.validation).toFixed(3) : '—' }}；独立留出集为 {{ selectedModel.silhouette?.test?.toFixed(3) ?? '—' }}。轮廓系数反映聚类结构，不是趋势预测准确率，也不能说明仓库优劣。</div>
        </template>

        <template v-else-if="selectedModel?.id === 'M2'">
          <div class="model-meta"><span class="model-kind">{{ selectedModel.kind }}</span><strong>{{ selectedModel.name }}</strong><span>{{ selectedModel.algorithm }} · {{ selectedModel.version }}</span><span class="meta-divider"></span><span>训练 {{ selectedModel.samples.training_repositories }} 仓库 · 验证 {{ selectedModel.samples.validation_repositories }} 仓库 / {{ selectedModel.samples.validation_folds }} 个滚动窗口 · 测试 {{ selectedModel.samples.test_repositories }} 仓库</span></div>
          <div class="m2-summary">
            <article class="m2-score"><span>验证集 Macro-F1</span><strong>{{ percent(selectedModel.validation?.macro_f1) }}</strong><small>{{ selectedModel.samples.validation_repositories }} 仓库 · {{ selectedModel.samples.validation_folds }} 个滚动窗口</small></article>
            <article class="m2-score m2-score--accent"><span>独立测试 Macro-F1</span><strong>{{ percent(selectedModel.test?.macro_f1) }}</strong><small>{{ selectedModel.samples.test_repositories }} 个留出仓库</small></article>
            <article class="m2-score"><span>测试集平衡准确率</span><strong>{{ percent(selectedModel.test?.balanced_accuracy) }}</strong><small>按类别召回率取平均</small></article>
            <article class="m2-score"><span>测试集对近期趋势基线</span><strong>+{{ (((selectedModel.test?.macro_f1 ?? 0) - (selectedModel.benchmarks?.find((item) => item.id === 'recent_trend_baseline')?.test.macro_f1 ?? 0)) * 100).toFixed(1) }} <small>分</small></strong><small>Macro-F1 绝对差</small></article>
          </div>
          <div class="detail-grid m2-detail-grid">
            <div class="detail-panel">
              <div class="panel-heading"><h3>基线对比</h3><span>越高越好 · 0–100%</span></div>
              <div class="benchmark-table-wrap"><table class="benchmark-table"><thead><tr><th>模型</th><th>验证 Macro-F1</th><th>测试 Macro-F1</th><th>测试平衡准确率</th></tr></thead><tbody><tr v-for="item in selectedModel.benchmarks" :key="item.id" :class="{ chosen: item.selected }"><td>{{ item.name }}<span v-if="item.selected" class="chosen-tag">当前</span></td><td><div class="table-score"><span>{{ percent(item.validation.macro_f1) }}</span><i><b :style="{ width: scoreWidth(item.validation.macro_f1) }"></b></i></div></td><td><div class="table-score"><span>{{ percent(item.test.macro_f1) }}</span><i><b :style="{ width: scoreWidth(item.test.macro_f1) }"></b></i></div></td><td>{{ percent(item.test.balanced_accuracy) }}</td></tr></tbody></table></div>
            </div>
            <div class="detail-panel">
              <div class="panel-heading"><h3>独立测试混淆矩阵</h3><span>行：真实 · 列：预测</span></div>
              <div v-if="selectedModel.test_confusion_matrix" class="matrix-wrap"><table class="matrix-table"><thead><tr><th>真实 \ 预测</th><th v-for="label in selectedModel.test_confusion_matrix.labels" :key="label">{{ label }}</th></tr></thead><tbody><tr v-for="(row, rowIndex) in selectedModel.test_confusion_matrix.values" :key="rowIndex"><th>{{ selectedModel.test_confusion_matrix.labels[rowIndex] }}</th><td v-for="(value, colIndex) in row" :key="colIndex" :class="{ diagonal: rowIndex === colIndex }">{{ value }}</td></tr></tbody></table></div>
              <p class="matrix-caption">模型会漏判一部分“上升”样本；请结合类别样本量和业务用途理解预测，不应单独作为决策依据。</p>
            </div>
          </div>
          <div class="caveat-line"><strong>标签定义：</strong>{{ selectedModel.label_definition }} <span v-for="note in selectedModel.notes" :key="note">{{ note }}</span></div>
        </template>
      </section>

      <section class="runtime-card">
        <div class="section-heading"><div><p class="eyebrow">RUNTIME / REGISTRY</p><h2>模型部署与服务状态</h2></div><span class="live-pill"><i></i>当前进程</span></div>
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

    <footer class="page-footer"><span>RepoVantage Model Observability</span><span>用户主站 <a href="http://127.0.0.1:8501/">127.0.0.1:8501</a> <b>·</b> ML 控制台 127.0.0.1:8502</span></footer>
  </main>
</template>

<style scoped>
.silhouette-track{position:relative}
.silhouette-track>span{position:absolute;z-index:1;top:-2px;bottom:-2px;left:50%;width:1px;background:#fff;box-shadow:0 0 0 1px rgba(70,92,118,.35)}
.silhouette-track>i{position:relative}
</style>
