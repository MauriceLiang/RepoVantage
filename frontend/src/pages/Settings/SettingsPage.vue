<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Check, ExternalLink, KeyRound, RefreshCw, Save, Trash2 } from 'lucide-vue-next'
import { useDataSource } from '@/composables/useDataSource'
import { useUiStore } from '@/stores/ui'
import type { GitHubTokenSettings } from '@/services/types'

const source = useDataSource()
const ui = useUiStore()
const token = ref('')
const settings = ref<GitHubTokenSettings>({ configured: false, managedByEnvironment: false })
const loading = ref(true)
const saving = ref(false)
const removing = ref(false)
const error = ref('')
const saved = ref(false)
const busy = computed(() => saving.value || removing.value)

async function loadSettings() {
  loading.value = true
  error.value = ''
  saved.value = false
  try {
    settings.value = await source.getGitHubTokenSettings()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '读取设置失败'
  } finally { loading.value = false }
}

async function saveToken() {
  const value = token.value.trim()
  if (!value || loading.value || busy.value || settings.value.managedByEnvironment) return
  saving.value = true
  error.value = ''
  saved.value = false
  try {
    settings.value = await source.saveGitHubToken(value)
    token.value = ''
    saved.value = true
    ui.toast('GitHub token 已保存到本机环境文件')
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '保存 token 失败'
  } finally { saving.value = false }
}

async function removeToken() {
  if (loading.value || busy.value || !settings.value.configured || settings.value.managedByEnvironment) return
  removing.value = true
  error.value = ''
  saved.value = false
  try {
    settings.value = await source.deleteGitHubToken()
    token.value = ''
    saved.value = true
    ui.toast('GitHub token 已从本机环境文件移除')
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '移除 token 失败'
  } finally { removing.value = false }
}

onMounted(() => { void loadSettings() })
</script>

<template>
  <div class="stack app-page">
    <UiPageHeader title="设置" description="配置个人 GitHub 访问令牌，为本机采集增加 API 请求额度。">
      <template #actions><UiButton variant="quiet" :disabled="loading || busy" @click="loadSettings"><RefreshCw :size="13" />重新读取</UiButton></template>
    </UiPageHeader>

    <div class="settings-content stack">
      <section class="settings-section" aria-labelledby="github-token-title">
        <div class="settings-section-heading">
          <div>
            <h2 id="github-token-title" class="panel-title"><KeyRound :size="17" aria-hidden="true" /> GitHub API 令牌</h2>
            <p class="settings-description">使用个人 token 发起 GitHub API 请求，可提高请求额度。token 保存在项目根目录的 <code>.env</code> 中，仅由本机后端读取；页面不会再次读取或显示 token 内容。</p>
          </div>
          <span class="token-status" :class="settings.configured ? 'is-configured' : 'is-empty'" role="status">
            <span class="status-dot" aria-hidden="true" />{{ loading ? '读取中' : settings.configured ? '已配置' : '未配置' }}
          </span>
        </div>

        <form class="token-form" @submit.prevent="saveToken">
          <label for="github-token" class="settings-label">个人访问令牌</label>
          <div class="token-input-row">
            <input
              id="github-token"
              v-model="token"
              class="field field--md"
              type="password"
              name="github-token"
              autocomplete="new-password"
              autocapitalize="off"
              spellcheck="false"
              maxlength="500"
              :placeholder="settings.configured ? '输入新 token 以替换当前令牌' : '粘贴 GitHub token'"
              :disabled="loading || busy || settings.managedByEnvironment"
              aria-describedby="github-token-help"
            >
            <UiButton type="submit" variant="primary" :disabled="loading || busy || settings.managedByEnvironment || !token.trim()" :loading="saving">
              <Save v-if="!saving" :size="14" />{{ saving ? '保存中' : settings.configured ? '替换令牌' : '保存令牌' }}
            </UiButton>
          </div>
          <p id="github-token-help" class="small muted">保存后只返回配置状态，不会回显令牌。令牌由当前机器的 API 与 Worker 用于读取 GitHub 数据。</p>

          <p v-if="settings.managedByEnvironment" class="settings-note" role="status">当前令牌由启动进程的 <code>GITHUB_TOKEN</code> 环境变量提供。请修改该环境变量并重启服务，页面不能覆盖它。</p>

          <div class="settings-feedback" aria-live="polite">
            <p v-if="error" class="settings-error" role="alert">{{ error }}</p>
            <p v-else-if="saved" class="settings-success" role="status"><Check :size="14" />操作已完成</p>
          </div>

          <div class="token-actions">
            <UiButton v-if="settings.configured && !settings.managedByEnvironment" variant="danger" :disabled="loading || busy" :loading="removing" @click="removeToken">
              <Trash2 v-if="!removing" :size="14" />{{ removing ? '移除中' : '移除令牌' }}
            </UiButton>
          </div>
        </form>
      </section>

      <section class="settings-section" aria-labelledby="github-token-instructions">
        <h2 id="github-token-instructions" class="panel-title">如何获取 GitHub token</h2>
        <ol class="token-instructions">
          <li>打开 <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noreferrer">Fine-grained personal access token 创建页 <ExternalLink :size="12" aria-hidden="true" /></a>，也可从 GitHub 头像菜单进入 Settings → Developer settings → Personal access tokens → Fine-grained tokens。</li>
          <li>填写名称和有效期。公开仓库只读分析通常不需要额外权限；如需读取私有仓库，只选择需要的仓库并授予必要的只读权限。组织令牌可能需要管理员批准。</li>
          <li>生成后立即复制 token，粘贴到上方并保存。GitHub 只在创建时显示完整 token；如果过期或泄露，请在 GitHub 撤销后重新创建并替换。</li>
        </ol>
        <p class="settings-description">GitHub REST API 的主额度通常为未认证 60 次/小时、个人认证请求 5,000 次/小时；具体仍受账户共享额度和次级限流影响。查看 <a href="https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api" target="_blank" rel="noreferrer">官方限流说明 <ExternalLink :size="12" aria-hidden="true" /></a>。</p>
      </section>

    </div>
  </div>
</template>

<style scoped>
.settings-content { width:min(100%, 1040px); gap:28px; }
.settings-section { padding:20px 0 24px; border-block-end:1px solid var(--line); }
.settings-section-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:24px; }
.panel-title { display:flex; align-items:center; gap:8px; margin:0; font-size:15px; font-weight:650; }
.settings-description { max-width:800px; margin:8px 0 0; color:var(--muted); font-size:12px; line-height:1.65; }
.settings-description code,.settings-note code { color:var(--text); font-size:.95em; }
.token-status { display:inline-flex; align-items:center; gap:7px; flex:none; padding:6px 9px; border-radius:999px; background:var(--surface-soft); color:var(--muted); font-size:11px; }
.token-status.is-configured { color:var(--green); }
.status-dot { width:7px; height:7px; border-radius:50%; background:currentColor; }
.token-form { display:grid; gap:8px; max-width:760px; margin-top:22px; }
.settings-label { font-size:12px; font-weight:620; }
.token-input-row { display:flex; align-items:center; gap:10px; }
.token-input-row .field { flex:1; min-width:0; }
.token-form > .small { margin:0; line-height:1.55; }
.settings-note { margin:3px 0 0; padding:9px 11px; border-radius:6px; background:var(--primary-soft); color:var(--muted); font-size:12px; line-height:1.6; }
.settings-feedback { min-height:0; }
.settings-feedback p { margin:3px 0 0; }
.token-actions { display:flex; justify-content:flex-end; }
.settings-error { color:var(--red); font-size:12px; }
.settings-success { display:flex; align-items:center; gap:5px; color:var(--green); font-size:12px; }
.token-instructions { display:grid; gap:10px; max-width:840px; margin:14px 0 0; padding-inline-start:22px; color:var(--muted); font-size:12px; line-height:1.7; }
.token-instructions a,.settings-description a { display:inline-flex; align-items:center; gap:3px; color:var(--primary); text-decoration:underline; text-underline-offset:2px; }
@media(max-width:640px) {
  .settings-section-heading { flex-direction:column; gap:14px; }
  .token-input-row { align-items:stretch; flex-direction:column; }
  .token-input-row .field { width:100%; }
  .token-input-row :deep(.button) { width:100%; }
  .token-actions { justify-content:flex-start; }
}
</style>
