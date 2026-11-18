<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Check, RefreshCw, Save } from 'lucide-vue-next'
import { useDataSource } from '@/composables/useDataSource'
import { useUiStore } from '@/stores/ui'

const source = useDataSource()
const ui = useUiStore()
const pageLimit = ref<number | null>(10)
const savedPageLimit = ref(10)
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const saved = ref(false)
const valid = computed(() => Number.isInteger(pageLimit.value) && (pageLimit.value ?? 0) >= 1 && (pageLimit.value ?? 0) <= 100)
const dirty = computed(() => pageLimit.value !== savedPageLimit.value)
const maxRecords = computed(() => valid.value && pageLimit.value ? pageLimit.value * 100 : null)
const fieldDescription = computed(() => valid.value
  ? 'github-max-pages-help'
  : 'github-max-pages-help github-max-pages-error')

async function loadSettings() {
  loading.value = true
  error.value = ''
  saved.value = false
  try {
    const settings = await source.getCollectionSettings()
    pageLimit.value = settings.githubMaxPages
    savedPageLimit.value = settings.githubMaxPages
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '读取设置失败'
  } finally { loading.value = false }
}

async function saveSettings() {
  if (!valid.value || pageLimit.value === null || saving.value) return
  saving.value = true
  error.value = ''
  saved.value = false
  try {
    const settings = await source.saveCollectionSettings({ githubMaxPages: pageLimit.value })
    pageLimit.value = settings.githubMaxPages
    savedPageLimit.value = settings.githubMaxPages
    saved.value = true
    ui.toast('采集设置已保存')
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '保存设置失败'
  } finally { saving.value = false }
}
onMounted(() => { void loadSettings() })
</script>

<template>
  <div class="stack app-page">
    <UiPageHeader title="设置" description="调整采集范围，控制数据覆盖、耗时与 GitHub API 请求量。">
      <template #actions><UiButton variant="quiet" :disabled="loading || saving" @click="loadSettings"><RefreshCw :size="13" />重新读取</UiButton></template>
    </UiPageHeader>
    <form class="settings-form" aria-labelledby="settings-collection-title" @submit.prevent="saveSettings">
      <section class="settings-option">
        <div class="settings-copy">
          <label id="settings-collection-title" for="github-max-pages" class="settings-label">每个接口最多采集页数</label>
          <p id="github-max-pages-help" class="settings-description">
            应用于 Commit、Issue、PR 和 Release 接口。每页最多 100 条，当前上限约为
            {{ maxRecords === null ? '—' : maxRecords.toLocaleString() }} 条 / 接口，实际数量取决于仓库数据量。
          </p>
          <p class="settings-description">
            达到页数上限后按该标准完成。请求失败或事件校验异常时仍可能部分完成。提高上限会增加采集时间和 API 请求，保存后对新启动的任务生效。
          </p>
        </div>
        <div class="settings-control">
          <input
            id="github-max-pages"
            v-model.number="pageLimit"
            class="field field--md settings-number"
            type="number"
            min="1"
            max="100"
            step="1"
            :disabled="loading || saving"
            :aria-invalid="!valid && !loading"
            :aria-describedby="fieldDescription"
          >
          <span class="small muted">页 / 接口</span>
        </div>
      </section>
      <p v-if="!valid && !loading" id="github-max-pages-error" class="settings-error" role="alert">
        请输入 1 到 100 之间的整数。
      </p>
      <div class="settings-footer">
        <div class="settings-feedback" aria-live="polite">
          <p v-if="error" class="settings-error" role="alert">{{ error }}</p>
          <p v-else-if="saved" class="settings-success" role="status"><Check :size="14" />设置已保存</p>
          <p v-else class="small muted">可设置 1–100 页，默认 10 页。</p>
        </div>
        <UiButton variant="primary" type="submit" :disabled="loading || saving || !dirty || !valid" :loading="loading || saving">
          <Save v-if="!loading && !saving" :size="14" />{{ loading ? '读取中' : saving ? '保存中' : '保存设置' }}
        </UiButton>
      </div>
    </form>
  </div>
</template>

<style scoped>
.settings-form { width: min(100%, 980px); }
.settings-option {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 32px;
  padding: 22px 0;
  border-block: 1px solid var(--line);
}
.settings-label { display: block; margin-bottom: 7px; font-size: 14px; font-weight: 650; }
.settings-description { max-width: 690px; margin: 6px 0 0; color: var(--muted); font-size: 12px; line-height: 1.6; }
.settings-control { display: flex; align-items: center; gap: 9px; }
.settings-number { width: 96px; min-height: 42px; font-size: 14px; }
.settings-form > .settings-error { margin: 9px 0 0; }
.settings-footer { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding-top: 14px; }
.settings-footer p { margin: 0; }
.settings-error { color: var(--red); font-size: 12px; }
.settings-success { display: flex; align-items: center; gap: 5px; color: var(--green); font-size: 12px; }
@media(max-width:640px) {
  .settings-option { grid-template-columns: minmax(0, 1fr); align-items: start; gap: 14px; padding: 18px 0; }
  .settings-footer { align-items: flex-start; }
}
</style>
