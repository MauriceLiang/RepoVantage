<script setup lang="ts">
import { ref } from 'vue'
import { Activity, Check, CircleAlert, Database } from 'lucide-vue-next'

const loading = ref(false)
const selectedNav = ref('overview')
const search = ref('')
const language = ref('全部语言')
const languageOptions = [
  { value: '全部语言', label: '全部语言' },
  { value: 'TypeScript', label: 'TypeScript' },
  { value: 'Python', label: 'Python' },
  { value: 'Go', label: 'Go' },
]
const weight = ref(62.5)
const errorInput = ref('')

function showLoading() {
  if (loading.value) return
  loading.value = true
  window.setTimeout(() => { loading.value = false }, 950)
}

const navigation = [
  { id: 'overview', label: '总览', icon: Activity },
  { id: 'repositories', label: '仓库', icon: Database },
  { id: 'alerts', label: '运行告警', icon: CircleAlert },
]
</script>

<template>
  <main class="component-gallery">
    <UiPageHeader title="组件样例" description="共享组件的尺寸、状态和窄屏表现。以下内容为本地合成样例。">
      <template #title-extra><UiBadge tone="accent">UI 预览</UiBadge></template>
    </UiPageHeader>

    <div class="component-gallery__grid">
      <UiPanel as="section">
        <div class="panel-heading"><div><h2 class="panel-title">操作按钮</h2><p class="panel-description">统一 36px 高度，主次动作、图标和状态使用相同控件尺寸。</p></div></div>
        <div class="component-gallery__row">
          <UiButton variant="primary" @click="showLoading"><Check :size="13" />主要操作</UiButton>
          <UiButton variant="outline">次要操作</UiButton>
          <UiButton variant="quiet">轻操作</UiButton>
          <UiButton variant="danger">移除样例</UiButton>
        </div>
        <div class="component-gallery__row" style="margin-top:13px">
          <UiButton variant="primary" @click="showLoading">带图标操作 <Check :size="13" /></UiButton>
          <UiButton variant="primary" :loading="loading">{{ loading ? '处理中' : '点击预览加载态' }}</UiButton>
          <UiButton variant="outline" disabled>不可用</UiButton>
        </div>
      </UiPanel>

      <UiPanel as="section">
        <div class="panel-heading"><div><h2 class="panel-title">状态标签</h2><p class="panel-description">颜色与文字共同表达状态，不依赖色彩单独传递信息。</p></div></div>
        <div class="component-gallery__row">
          <UiBadge>默认状态</UiBadge>
          <UiBadge tone="accent">Mock 样例</UiBadge>
          <UiBadge tone="success"><span class="status-dot" />已完成</UiBadge>
          <UiBadge tone="warning">等待处理</UiBadge>
          <UiBadge tone="danger">需要关注</UiBadge>
        </div>
        <p class="component-gallery__note" style="margin:15px 0 0">长对象路径在内容区换行或截断，状态标签本身保持紧凑：organization/example-project-with-a-long-name</p>
      </UiPanel>

      <UiPanel as="section">
        <div class="panel-heading"><div><h2 class="panel-title">表单控件</h2><p class="panel-description">输入、下拉选择、数值和校验反馈使用统一的尺寸与焦点规则。</p></div></div>
        <div class="component-gallery__fields">
          <label class="component-gallery__field">搜索仓库
            <UiInput v-model="search" type="search" aria-label="搜索仓库样例" placeholder="owner/repository" />
            <span class="small">输入值：{{ search || '尚未输入' }}</span>
          </label>
          <label class="component-gallery__field">手动权重（%）
            <UiInput v-model.number="weight" type="number" min="0" max="100" step="0.1" class="mono" aria-label="样例权重" />
            <span class="small">精确到小数点后一位：{{ weight }}%</span>
          </label>
          <label class="component-gallery__field">仓库语言
            <UiSelect v-model="language" label="样例仓库语言" :options="languageOptions" style="width:100%" />
            <span class="small">当前选择：{{ language }}</span>
          </label>
          <label class="component-gallery__field">无效值示例
            <UiInput v-model="errorInput" :invalid="errorInput.length > 0" aria-describedby="gallery-error" placeholder="请输入仓库名称" />
            <span id="gallery-error" class="component-gallery__error">{{ errorInput ? '该字段格式不正确，请检查输入。' : '输入内容后显示错误反馈。' }}</span>
          </label>
        </div>
        <label class="component-gallery__field" style="max-width:300px;margin-top:12px">不可编辑
          <UiInput model-value="只读样例" disabled aria-label="不可编辑样例" />
        </label>
      </UiPanel>

      <UiPanel as="section">
        <div class="panel-heading"><div><h2 class="panel-title">导航与数值摘要</h2><p class="panel-description">选中状态有文字、图标和背景提示；紧凑空间下仍能完整点击。</p></div></div>
        <div class="component-gallery__grid">
          <nav class="component-gallery__nav" aria-label="组件样例导航">
            <UiNavItem v-for="item in navigation" :key="item.id" :id="item.id" :label="item.label" :icon="item.icon" :active="selectedNav === item.id" @select="selectedNav = $event" />
          </nav>
          <UiMetricCard class="component-gallery__metric" label="可用仓库样例" :value="300" note="数据完全在本地生成">
            <template #icon><Database :size="12" style="margin-right:4px;vertical-align:-2px" /></template>
          </UiMetricCard>
        </div>
        <p class="component-gallery__note" style="margin:14px 0 0">当前导航：{{ navigation.find((item) => item.id === selectedNav)?.label }}</p>
      </UiPanel>

      <UiPanel as="section" class="component-gallery__panel">
        <div class="panel-heading"><div><h2 class="panel-title">内容面板</h2><p class="panel-description">表面只用于区分独立内容区域，卡片之间使用统一间距。</p></div></div>
        <div class="component-gallery__row">
          <UiPanel as="article" tight style="flex:1 1 190px">
            <span class="eyebrow">紧凑面板</span>
            <div class="panel-title" style="margin-top:7px">更高信息密度</div>
            <p class="component-gallery__note" style="margin:5px 0 0">用于表格辅助内容和排名明细。</p>
          </UiPanel>
          <UiPanel as="article" style="flex:1 1 190px">
            <span class="eyebrow">标准面板</span>
            <div class="panel-title" style="margin-top:7px">常规内容分组</div>
            <p class="component-gallery__note" style="margin:5px 0 0">用于图表、指标区和编辑表单。</p>
          </UiPanel>
        </div>
      </UiPanel>
    </div>
    <p class="helper-note" style="margin-top:16px"><Database :size="12" style="vertical-align:-2px" /> 该展示页仅用于检查共享组件，不连接数据库、GitHub 或后台 API。</p>
  </main>
</template>
