<script lang="ts">
export type GroupAction =
  | { type: 'create' }
  | { type: 'assign'; repositoryIds: string[] }
  | { type: 'pick'; groupId: string }
</script>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle } from 'reka-ui'
import { useDataSource } from '@/composables/useDataSource'
import type { RepositoryGroup, RepositorySummary } from '@/services/types'

const props = defineProps<{
  action: GroupAction | null
  repositories: RepositorySummary[]
  groups: RepositoryGroup[]
}>()
const emit = defineEmits<{ close: []; saved: [group: RepositoryGroup, added: number] }>()
const source = useDataSource()
const newGroup = 'new'
const name = ref('')
const targetGroupId = ref('')
const pickerQuery = ref('')
const chosenIds = ref<string[]>([])
const error = ref('')
const saving = ref(false)
let trigger: HTMLElement | null = null

const pickedGroup = computed(() => {
  const action = props.action
  return action?.type === 'pick' ? props.groups.find((group) => group.id === action.groupId) : undefined
})
const availableRepositories = computed(() => {
  const members = new Set(pickedGroup.value?.repositoryIds)
  return props.repositories.filter((repository) => !members.has(repository.id))
})
const pickerRows = computed(() => {
  const term = pickerQuery.value.trim().toLocaleLowerCase()
  return availableRepositories.value.filter((repository) => repository.fullName.toLocaleLowerCase().includes(term))
})
const assignmentOptions = computed(() => {
  const action = props.action
  if (action?.type !== 'assign') return []
  return [
    ...props.groups.filter((group) => action.repositoryIds.some((id) => !group.repositoryIds.includes(id)))
      .map((group) => ({ value: group.id, label: group.name })),
    { value: newGroup, label: '新建分组' },
  ]
})
const creating = computed(() => props.action?.type === 'create' || targetGroupId.value === newGroup)
const title = computed(() => props.action?.type === 'create' ? '新建分组' : props.action?.type === 'pick' ? '添加仓库' : '加入分组')
const canSave = computed(() => {
  if (creating.value) return Boolean(name.value.trim())
  if (props.action?.type === 'pick') return Boolean(chosenIds.value.length)
  return Boolean(targetGroupId.value)
})

watch(() => props.action, (action) => {
  if (!action) return
  trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
  name.value = ''
  targetGroupId.value = action.type === 'assign' && assignmentOptions.value.length === 1 ? newGroup : ''
  pickerQuery.value = ''
  chosenIds.value = []
  error.value = ''
})

function close() {
  if (!saving.value) emit('close')
}

function restoreFocus(event: Event) {
  if (trigger?.isConnected && !trigger.matches(':disabled')) {
    event.preventDefault()
    trigger.focus()
  }
  trigger = null
}

async function save() {
  const action = props.action
  if (!action || !canSave.value || saving.value) return
  const ids = action.type === 'assign' ? action.repositoryIds : chosenIds.value
  const groupId = action.type === 'pick' ? action.groupId : targetGroupId.value
  const previousIds = new Set(props.groups.find((group) => group.id === groupId)?.repositoryIds)
  saving.value = true
  error.value = ''
  try {
    const group = creating.value
      ? await source.createRepositoryGroup(name.value.trim(), ids)
      : await source.addRepositoriesToGroup(groupId, ids)
    emit('saved', group, ids.filter((id) => !previousIds.has(id)).length)
    emit('close')
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '保存分组失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <DialogRoot :open="action !== null" @update:open="(value) => !value && close()">
    <DialogPortal to=".app-layout">
      <DialogOverlay class="group-dialog-overlay" />
      <DialogContent class="group-dialog" @close-auto-focus="restoreFocus">
        <DialogTitle class="group-dialog-title">{{ title }}</DialogTitle>
        <DialogDescription v-if="action?.type === 'pick'" class="muted">将「我的仓库」中的项目添加到「{{ pickedGroup?.name }}」。</DialogDescription>
        <DialogDescription v-else-if="action?.type === 'assign'" class="muted">已选择 {{ action.repositoryIds.length }} 个仓库。</DialogDescription>
        <DialogDescription v-else class="sr-only">输入名称以创建仓库分组。</DialogDescription>

        <form class="stack" @submit.prevent="save">
          <UiSelect
            v-if="action?.type === 'assign' && assignmentOptions.length > 1"
            v-model="targetGroupId"
            class="group-dialog-select"
            label="目标分组"
            placeholder="选择分组"
            :options="assignmentOptions"
            :disabled="saving"
            searchable
            floating
          />

          <label v-if="creating" class="group-dialog-field">
            分组名称
            <UiInput v-model="name" maxlength="80" required placeholder="例如 前端工具" :disabled="saving" />
          </label>

          <template v-if="action?.type === 'pick'">
            <UiInput v-model="pickerQuery" type="search" aria-label="搜索可添加的仓库" placeholder="搜索仓库名称" :disabled="saving" />
            <ul v-if="pickerRows.length" class="group-picker" aria-label="可添加的仓库">
              <li v-for="repository in pickerRows" :key="repository.id">
                <label>
                  <input v-model="chosenIds" type="checkbox" class="checkbox" :value="repository.id" :disabled="saving" />
                  <span>{{ repository.fullName }}</span>
                </label>
              </li>
            </ul>
            <p v-else class="muted">{{ availableRepositories.length ? '没有匹配的仓库' : '没有可添加的仓库' }}</p>
          </template>

          <p v-if="error" class="small group-dialog-error" role="alert">{{ error }}</p>
          <div class="group-dialog-footer">
            <span v-if="action?.type === 'pick'" class="small muted">已选 {{ chosenIds.length }} 个</span>
            <UiButton variant="quiet" :disabled="saving" @click="close">取消</UiButton>
            <UiButton variant="primary" type="submit" :disabled="!canSave" :loading="saving">
              {{ creating ? (action?.type === 'assign' ? '创建并加入' : '创建分组') : '添加到分组' }}
            </UiButton>
          </div>
        </form>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.group-dialog-overlay {
  position: fixed;
  z-index: 40;
  inset: 0;
  background: rgb(0 0 0 / 32%);
}
.group-dialog {
  /* Center without a transform so the fixed dropdown can escape this scroll container. */
  position: fixed;
  z-index: 50;
  inset: 0;
  margin: auto;
  width: min(440px, calc(100% - 32px));
  height: fit-content;
  max-height: calc(100dvh - 32px);
  overflow: auto;
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: 0 16px 50px rgb(22 29 35 / 20%);
}
.group-dialog-title { margin: 0 0 6px; font-size: 17px; font-weight: 650; }
.group-dialog p { margin: 0; }
.group-dialog form { gap: 12px; margin-top: 16px; }
.group-dialog-select { width: 100%; }
.group-dialog-field { display: grid; gap: 6px; font-size: 12px; font-weight: 600; }
.group-dialog-error { color: var(--red); }
.group-dialog-footer { display: flex; gap: 8px; align-items: center; justify-content: flex-end; }
.group-dialog-footer span { margin-right: auto; }
.group-picker {
  max-height: min(260px, 36dvh);
  overflow: auto;
  margin: 0;
  padding: 4px;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.group-picker label { display: flex; align-items: center; gap: 10px; padding: 8px; cursor: pointer; }
.group-picker label:hover { background: var(--surface-soft); }
.group-picker input { flex: none; }
.group-picker span { overflow-wrap: anywhere; }
</style>
