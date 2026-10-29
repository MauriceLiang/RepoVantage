<script setup lang="ts">
import { Activity, ArrowDownRight, ArrowRight, ArrowUpRight, CalendarDays, ChevronRight, RefreshCw, Search } from 'lucide-vue-next'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import GdBadge from '@/components/ui/GdBadge.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import GdInput from '@/components/ui/GdInput.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useDataSource } from '@/composables/useDataSource'
import type { RepositorySummary, TaskItem } from '@/services/types'
import { useAnalysisStore } from '@/stores/analysis'
import { useUiStore } from '@/stores/ui'

const router = useRouter()
const ui = useUiStore()
const analysis = useAnalysisStore()
const source = useDataSource()

const input = ref('')
const invalid = ref(false)
const submitting = ref(false)
const submitError = ref<string | null>(null)
const { data: repositories, loading, error, reload: reloadRepositories } = useAsyncData(() => source.listRepositories())
const { data: tasks, loading: tasksLoading, error: tasksError, reload: reloadTasks } = useAsyncData(() => source.listTasks())

const recent = computed(() => (repositories.value ?? []).slice(0, 5))
const activeTasks = computed(() => (tasks.value ?? []).filter((task) => ['queued', 'running', 'analyzing'].includes(task.status)))
const activityChanges = ref<{ repo: RepositorySummary; changePercent: number }[]>([])
const changesLoading = ref(false)
const changesError = ref<string | null>(null)
const changeCandidateCount = ref(0)
let changesRequestId = 0
let pollTimer: number | undefined

watch(repositories, async (items) => {
  const requestId = ++changesRequestId
  activityChanges.value = []
  changesError.value = null
  if (!items) {
    changesLoading.value = false
    return
  }

  // The library list is already ordered by last collection. Keep the dashboard
  // read bounded and rank the latest five analyzable repositories by change.
  const candidates = items.filter((repo) => repo.status === 'ready' || repo.status === 'partial').slice(0, 5)
  changeCandidateCount.value = candidates.length
  if (!candidates.length) {
    changesLoading.value = false
    return
  }

  changesLoading.value = true
  const results = await Promise.allSettled(candidates.map(async (repo) => ({
    repo,
    changePercent: await source.getActivityChangePercent(repo.id),
  })))
  if (requestId !== changesRequestId) return

  const rejected = results.filter((result) => result.status === 'rejected')
  const available: { repo: RepositorySummary; changePercent: number }[] = []
  for (const result of results) {
    if (result.status === 'fulfilled' && result.value.changePercent !== null) {
      available.push({ repo: result.value.repo, changePercent: result.value.changePercent })
    }
  }
  activityChanges.value = available.sort((left, right) => Math.abs(right.changePercent) - Math.abs(left.changePercent)).slice(0, 3)
  if (rejected.length === candidates.length) {
    const failure = rejected[0]
    changesError.value = failure.status === 'rejected'
      ? String(failure.reason?.message ?? '趋势数据读取失败')
      : '趋势数据读取失败'
  } else if (rejected.length) {
    changesError.value = `${rejected.length} 个仓库的趋势暂时无法读取`
  }
  changesLoading.value = false
}, { immediate: true })

const changes = computed(() => activityChanges.value.map(({ repo, changePercent }) => {
  const roundedChange = Number(changePercent.toFixed(1))
  return {
    repo,
    changePercent: roundedChange,
    text: roundedChange === 0
      ? '近 4 个完整周的 Commit 数与前 4 周基本持平。'
      : `近 4 个完整周的 Commit 数较前 4 周${roundedChange < 0 ? '减少' : '增加'} ${Math.abs(roundedChange)}%。`,
  }
}))

const taskStatusLabel: Record<string, string> = {
  queued: '排队中', running: '执行中', analyzing: '分析中',
}
const taskModuleLabel: Record<string, string> = {
  profile: '仓库概况', commits: 'Commit 采集', issues: 'Issue 采集', pulls: 'PR 采集', releases: 'Release 采集',
  collect_repository: '仓库采集', repository: '仓库分析',
}
const taskEmptyState = computed(() => tasks.value?.length
  ? { badge: '队列空闲', title: '当前没有待处理任务', description: '最近任务均已结束，可在任务中心查看记录。' }
  : { badge: '等待开始', title: '还没有分析任务', description: '添加仓库并开始分析后，采集进度会显示在这里。' })

function taskProgress(task: TaskItem): number | null {
  const value = task.progressPercent
  if (task.progressKind !== 'stages' || typeof value !== 'number' || !Number.isFinite(value)) return null
  return Math.max(0, Math.min(100, value))
}

onMounted(() => {
  pollTimer = window.setInterval(() => {
    if (activeTasks.value.length) void reloadTasks()
  }, 3000)
})
onBeforeUnmount(() => { if (pollTimer !== undefined) window.clearInterval(pollTimer) })

const statusLabel: Record<RepositorySummary['status'], { text: string; cls: string }> = {
  ready: { text: '已完成', cls: '' },
  partial: { text: '部分数据', cls: 'warn' },
  running: { text: '正在更新', cls: '' },
  failed: { text: '采集失败', cls: 'warn' },
  idle: { text: '尚未分析', cls: 'plain' },
}

async function submit() {
  const raw = input.value.trim()
  if (!raw) {
    invalid.value = true
    return
  }
  invalid.value = false
  submitError.value = null
  submitting.value = true
  try {
    const result = await source.addRepository(raw)
    analysis.remember(result.repositoryId)
    ui.toast(result.taskId ? '仓库已加入，采集任务已排队' : '仓库已加入分析库')
    void router.push(`/repositories/${result.repositoryId}/overview`)
  } catch (error) {
    submitError.value = error instanceof Error ? error.message : '提交分析失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-[18px] px-4 pb-8 pt-5 sm:px-7 sm:pt-[22px]">
    <header>
      <h1 class="m-0 text-[26px] font-semibold tracking-[-0.3px]">仓库数据分析</h1>
      <p class="mt-1.5 text-muted">输入 GitHub 开源仓库，查看开发活动、Issue / PR 协作与发布节奏。</p>
    </header>

    <GdCard padding="none" class="gap-2.5 p-4 sm:p-[22px]">
      <div class="flex flex-col gap-2 sm:flex-row sm:items-start">
        <div class="min-w-0 flex-1">
          <div class="flex min-w-0 items-center gap-2">
            <GdInput v-model="input" class="min-w-0 flex-1" placeholder="owner/repo 或 GitHub 链接，例如 vuejs/core" :invalid="invalid" @enter="submit">
              <template #icon><Search :size="16" class="text-muted" /></template>
            </GdInput>
            <GdButton class="h-11 px-4" :disabled="submitting" @click="submit">{{ submitting ? '正在提交…' : '开始分析' }}</GdButton>
          </div>
          <p v-if="invalid" class="mt-1.5 text-[12px] text-danger">请输入 owner/repo 或完整的 GitHub 仓库链接</p>
          <p v-else-if="submitError" class="mt-1.5 text-[12px] text-danger">{{ submitError }}</p>
          <p v-else class="mt-2 text-[11.5px] text-muted">支持公开仓库；分析结果包含采集时点与覆盖状态。</p>
        </div>
      </div>
    </GdCard>

    <section aria-labelledby="project-background-title" class="flex flex-col gap-3.5">
      <div class="flex flex-wrap items-end justify-between gap-2">
        <div>
          <p class="mb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">RepoVantage</p>
          <h2 id="project-background-title" class="m-0 text-[20px] font-semibold tracking-[-0.2px]">项目背景与意义</h2>
          <p class="mt-1.5 text-[12px] leading-relaxed text-muted">把分散的开发与协作信息整理为可阅读、可比较的数据。</p>
        </div>
        <GdBadge variant="plain">产品说明</GdBadge>
      </div>

      <div class="grid items-stretch gap-3.5 xl:grid-cols-[0.92fr_1.08fr]">
        <article class="min-w-0 rounded-[10px] border border-line bg-panel p-4 sm:p-5">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <h3 class="m-0 text-[15px] font-semibold">项目背景</h3>
            <GdBadge variant="plain">常见团队选型情境</GdBadge>
          </div>
          <div class="mt-4 flex flex-col gap-4 text-[14px] leading-[1.85] text-muted">
            <p class="m-0">一个团队准备为新项目选择开源组件，搜索后发现几个功能相近的 GitHub 仓库。它们都有介绍文档，也有不同数量的 Stars 和 Forks。但要进一步了解这些项目，还会遇到许多具体问题：最近是否持续有开发活动？已经关闭的 Issue 通常经历了多长时间？PR 的协作情况如何？过去一年发布过哪些版本，发布之间的间隔又是怎样的？</p>
            <p class="m-0">这些信息虽然都能在 GitHub 上找到，却分布在提交记录、Issue、PR 和 Release 等不同页面。查看一个仓库需要来回切换；比较多个仓库时，还需要手动整理时间范围和统计口径。仅看某个数字或某一天的状态，也很难理解项目在一段时间内的变化。</p>
            <p class="m-0">RepoVantage 希望把这些分散的信息组织成更容易阅读和比较的数据。用户输入公开仓库后，系统采集可用的开发与协作数据，通过趋势、分布和时间线展示项目在所选时间范围内发生了什么。用户既可以观察单个项目，也可以在满足数据条件时比较多个项目，或围绕选定样本开展研究。</p>
          </div>
        </article>

        <article class="min-w-0 rounded-[10px] border border-line bg-panel p-4 sm:p-5">
          <h3 class="m-0 text-[15px] font-semibold">项目的意义</h3>
          <ol class="mt-3 m-0 list-none divide-y divide-line p-0">
            <li class="flex gap-3 py-3 first:pt-0">
              <span class="flex size-7 shrink-0 items-center justify-center rounded-full bg-soft font-mono text-[10px] font-semibold text-muted">01</span>
              <p class="m-0 min-w-0 text-[12.5px] leading-[1.75]"><strong class="font-semibold text-ink">更快认识陌生项目：</strong><span class="text-muted">把提交、协作和发布信息集中起来，帮助使用者从多个维度了解项目近况，减少在不同页面之间反复查找和整理的工作。</span></p>
            </li>
            <li class="flex gap-3 py-3">
              <span class="flex size-7 shrink-0 items-center justify-center rounded-full bg-soft font-mono text-[10px] font-semibold text-muted">02</span>
              <p class="m-0 min-w-0 text-[12.5px] leading-[1.75]"><strong class="font-semibold text-ink">为技术选型提供线索：</strong><span class="text-muted">比较候选项目的活动变化、已结束 Issue 和 PR 的处理耗时及发布节奏，帮助团队发现需要继续核查的问题。例如，两个项目都很受关注，但近期发布节奏不同，就可以进一步查看版本内容和维护情况。</span></p>
            </li>
            <li class="flex gap-3 py-3">
              <span class="flex size-7 shrink-0 items-center justify-center rounded-full bg-soft font-mono text-[10px] font-semibold text-muted">03</span>
              <p class="m-0 min-w-0 text-[12.5px] leading-[1.75]"><strong class="font-semibold text-ink">支持项目观察与复盘：</strong><span class="text-muted">维护者和参与者可以查看一段时间内的开发活动和协作数据，发现值得追问的变化，再结合具体 Issue、PR 或版本记录分析原因。</span></p>
            </li>
            <li class="flex gap-3 py-3">
              <span class="flex size-7 shrink-0 items-center justify-center rounded-full bg-soft font-mono text-[10px] font-semibold text-muted">04</span>
              <p class="m-0 min-w-0 text-[12.5px] leading-[1.75]"><strong class="font-semibold text-ink">帮助开展开源研究：</strong><span class="text-muted">围绕明确的样本查看分组统计和数据分布，导出样本成员与统计结果，为研究者整理材料和讨论现象提供支持。研究结论仍需结合样本范围与数据质量理解。</span></p>
            </li>
            <li class="flex gap-3 py-3 last:pb-0">
              <span class="flex size-7 shrink-0 items-center justify-center rounded-full bg-soft font-mono text-[10px] font-semibold text-muted">05</span>
              <p class="m-0 min-w-0 text-[12.5px] leading-[1.75]"><strong class="font-semibold text-ink">让讨论有清楚的数据依据：</strong><span class="text-muted">展示采集时间、观察范围和覆盖状态，让使用者知道数据来自哪里、能说明什么，也能看见尚未采到或样本不足的部分。</span></p>
            </li>
          </ol>
          <p class="mb-0 mt-4 border-t border-line pt-3 text-[12px] leading-[1.75] text-muted">RepoVantage 提供的是观察和比较的依据。项目是否适合某个具体用途，还需要结合功能、兼容性、安全和许可证等因素进一步判断。</p>
        </article>
      </div>
    </section>

    <section aria-labelledby="how-to-use-title" class="flex flex-col gap-3.5">
      <div>
        <p class="mb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">GET STARTED</p>
        <h2 id="how-to-use-title" class="m-0 text-[20px] font-semibold tracking-[-0.2px]">开始使用</h2>
        <p class="mt-1.5 text-[12px] leading-relaxed text-muted">提交后会直接进入仓库详情；采集进度可以在总览任务卡或任务中心查看。</p>
      </div>

      <ol class="m-0 grid list-none grid-cols-1 gap-3 p-0 sm:grid-cols-2 xl:grid-cols-4">
        <li class="min-w-0 rounded-[10px] border border-line bg-panel p-4">
          <div class="flex items-center gap-2.5">
            <span class="flex size-8 shrink-0 items-center justify-center rounded-full bg-ink font-mono text-[11px] font-semibold text-bg">01</span>
            <h3 class="m-0 text-[13px] font-semibold">输入公开仓库</h3>
          </div>
          <p class="mb-0 mt-3 text-[12px] leading-[1.75] text-muted">输入 GitHub 仓库的 <code class="rounded bg-soft px-1 py-0.5 font-mono text-[11px] text-ink">owner/repo</code> 或完整链接，点击“开始分析”。</p>
        </li>
        <li class="min-w-0 rounded-[10px] border border-line bg-panel p-4">
          <div class="flex items-center gap-2.5">
            <span class="flex size-8 shrink-0 items-center justify-center rounded-full bg-ink font-mono text-[11px] font-semibold text-bg">02</span>
            <h3 class="m-0 text-[13px] font-semibold">进入详情看状态</h3>
          </div>
          <p class="mb-0 mt-3 text-[12px] leading-[1.75] text-muted">提交后立即进入该仓库详情，不需要等待采集完成。查看当前可用结果、采集时点和覆盖状态；从总览任务卡或<RouterLink to="/tasks" class="gd-link">任务中心</RouterLink>跟进进度。</p>
        </li>
        <li class="min-w-0 rounded-[10px] border border-line bg-panel p-4">
          <div class="flex items-center gap-2.5">
            <span class="flex size-8 shrink-0 items-center justify-center rounded-full bg-ink font-mono text-[11px] font-semibold text-bg">03</span>
            <h3 class="m-0 text-[13px] font-semibold">查看单仓库分析</h3>
          </div>
          <p class="mb-0 mt-3 text-[12px] leading-[1.75] text-muted">在开发活动、Issue、PR 和 Release 页签查看相应数据，并结合分析时间范围、样本和覆盖说明理解结果。</p>
        </li>
        <li class="min-w-0 rounded-[10px] border border-line bg-panel p-4">
          <div class="flex items-center gap-2.5">
            <span class="flex size-8 shrink-0 items-center justify-center rounded-full bg-ink font-mono text-[11px] font-semibold text-bg">04</span>
            <h3 class="m-0 text-[13px] font-semibold">按需比较或研究</h3>
          </div>
          <p class="mb-0 mt-3 text-[12px] leading-[1.75] text-muted">在<RouterLink to="/repositories" class="gd-link">仓库页</RouterLink>勾选 2–5 个候选仓库后，点击“进入比较”查看结果；需要研究时，前往<RouterLink to="/research" class="gd-link">研究分析</RouterLink>查看可用样本、分组统计与数据分布。</p>
        </li>
      </ol>
    </section>

    <GdCard>
      <div class="flex items-start justify-between gap-4">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">最近分析</h3>
          <p class="mt-0.5 text-[12px] text-muted">继续上次的分析，或查看采集状态</p>
        </div>
        <RouterLink to="/repositories" class="gd-link text-[12px]">全部仓库 <ArrowRight :size="12" /></RouterLink>
      </div>
      <div class="divide-y divide-line">
        <p v-if="error" class="py-3 text-[12px] text-danger">加载最近分析失败：{{ error }}</p>
        <div v-else-if="loading" class="divide-y divide-line">
          <div v-for="i in 4" :key="i" class="h-14 animate-pulse bg-track/60" />
        </div>
        <template v-else-if="recent.length">
          <RouterLink v-for="repo in recent" :key="repo.id" :to="`/repositories/${repo.id}/overview`"
            class="grid cursor-pointer grid-cols-1 items-center gap-3 py-3 transition-colors hover:bg-soft/40 sm:grid-cols-[1.6fr_1.4fr_auto_auto] sm:gap-5">
            <div class="min-w-0">
              <div class="truncate text-[13px] font-semibold">{{ repo.fullName }}</div>
              <div class="truncate text-[11.5px] text-muted">{{ repo.description }}</div>
            </div>
            <div class="text-[11.5px] text-muted">
              <template v-if="repo.status === 'ready' || repo.status === 'partial'">
                {{ repo.activityDelta === null ? '活动样本不足，未生成趋势判断' : `近 4 周较前 4 周 ${repo.activityDelta > 0 ? '+' : ''}${repo.activityDelta}%` }}
              </template>
              <template v-else>{{ repo.status === 'failed' ? '采集失败，可重试' : '尚未产出分析结果' }}</template>
            </div>
            <GdBadge :variant="(statusLabel[repo.status].cls as 'default' | 'warn' | 'plain')">
              {{ statusLabel[repo.status].text }}
            </GdBadge>
            <div class="flex items-center gap-2 text-[11.5px] text-muted">
              <span class="font-mono">{{ repo.lastAnalyzedAt ?? '—' }}</span>
              <ChevronRight :size="14" />
            </div>
          </RouterLink>
        </template>
        <div v-else class="flex flex-wrap items-center justify-between gap-3 py-4 text-[12px] text-muted">
          <span>还没有已加入的仓库。提交公开仓库后，会在这里保留最近分析记录。</span>
          <RouterLink to="/repositories" class="gd-link shrink-0">浏览仓库 <ArrowRight :size="12" /></RouterLink>
        </div>
      </div>
    </GdCard>

    <div class="grid items-stretch gap-[18px] lg:grid-cols-[1.4fr_1fr]">
      <GdCard class="h-[320px] min-h-0 overflow-hidden">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h3 class="m-0 text-[15.5px] font-semibold">近期值得关注的变化</h3>
            <p class="mt-0.5 text-[12px] text-muted">最近 5 个已分析仓库 · 前后各 4 个完整自然周</p>
          </div>
          <GdButton variant="ghost" size="sm" class="-mr-2" :disabled="loading || changesLoading" aria-label="刷新近期变化" @click="reloadRepositories">
            <RefreshCw :size="14" :class="changesLoading ? 'animate-spin' : ''" />
          </GdButton>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
          <div v-if="loading || changesLoading" class="flex h-full items-center gap-2 text-[12px] text-muted">
            <Activity :size="15" class="animate-pulse" /> 正在读取已保存的趋势分析…
          </div>
          <div v-else-if="error" class="flex h-full flex-col items-start justify-center gap-2 text-[12px] text-danger">
            <p class="m-0">仓库列表加载失败：{{ error }}</p>
            <GdButton variant="outline" size="sm" @click="reloadRepositories">重试</GdButton>
          </div>
          <div v-else-if="changesError && !changes.length" class="flex h-full flex-col items-start justify-center gap-2 text-[12px] text-danger">
            <p class="m-0">趋势读取失败：{{ changesError }}</p>
            <GdButton variant="outline" size="sm" @click="reloadRepositories">重试</GdButton>
          </div>
          <div v-else-if="changes.length" class="flex flex-col gap-3">
            <p v-if="changesError" class="m-0 text-[11px] text-muted">{{ changesError }}，以下展示可用结果。</p>
            <div v-for="item in changes" :key="item.repo.id" class="flex items-start gap-2.5 rounded-md border border-line px-3 py-2.5">
              <ArrowDownRight v-if="item.changePercent < 0" :size="16" class="mt-0.5 shrink-0 text-s1" />
              <ArrowUpRight v-else-if="item.changePercent > 0" :size="16" class="mt-0.5 shrink-0 text-s3" />
              <Activity v-else :size="15" class="mt-0.5 shrink-0 text-muted" />
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                  <RouterLink :to="`/repositories/${item.repo.id}/activity`" class="truncate text-[12.5px] font-semibold hover:underline">{{ item.repo.fullName }}</RouterLink>
                  <span class="shrink-0 font-mono text-[12px] font-semibold tabular-nums" :class="item.changePercent < 0 ? 'text-s1' : item.changePercent > 0 ? 'text-s3' : 'text-muted'">
                    {{ item.changePercent > 0 ? '+' : '' }}{{ item.changePercent }}%
                  </span>
                </div>
                <p class="mb-0 mt-1 text-[11.5px] leading-relaxed text-muted">{{ item.text }}</p>
              </div>
            </div>
          </div>
          <div v-else class="flex h-full flex-col items-start justify-center gap-2 text-[12px] text-muted">
            <p v-if="repositories?.length && !changeCandidateCount" class="m-0">当前仓库尚无已分析的 Commit 趋势。完成采集后，这里会检查前后各 4 个完整自然周。</p>
            <p v-else-if="repositories?.length" class="m-0">最近 5 个已分析仓库暂无可用趋势。Commit 覆盖需完整，且前后各有 4 个完整自然周；基期为 0 时不计算百分比。</p>
            <p v-else class="m-0">添加并完成仓库分析后，这里会展示近期 Commit 趋势变化。</p>
            <RouterLink to="/repositories" class="gd-link text-[11.5px]">查看仓库 <ArrowRight :size="12" /></RouterLink>
          </div>
        </div>
      </GdCard>

      <GdCard class="h-[320px] min-h-0 overflow-hidden">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h3 class="m-0 text-[15.5px] font-semibold">正在进行的分析</h3>
            <p class="mt-1 flex flex-wrap items-center gap-x-2 text-[11.5px] text-muted">
              <span class="inline-flex items-center gap-1.5"><span class="size-1.5 rounded-full bg-s3" />每 3 秒自动同步</span>
              <span class="text-line">·</span>
              <span>离开页面后任务仍在后台执行</span>
            </p>
          </div>
          <GdButton variant="ghost" size="sm" class="-mr-2" :disabled="tasksLoading" aria-label="刷新分析任务" @click="reloadTasks">
            <RefreshCw :size="14" :class="tasksLoading ? 'animate-spin' : ''" />
          </GdButton>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
          <div v-if="tasksError" class="flex h-full flex-col items-start justify-center gap-2 text-[12px] text-danger">
            <p class="m-0">任务加载失败：{{ tasksError }}</p>
            <GdButton variant="outline" size="sm" @click="reloadTasks">重试</GdButton>
          </div>
          <div v-else-if="tasksLoading && !tasks" class="flex flex-col gap-3 py-1">
            <div v-for="i in 3" :key="i" class="h-[54px] animate-pulse rounded bg-track/60" />
          </div>
          <div v-else-if="activeTasks.length" class="divide-y divide-line">
            <RouterLink v-for="task in activeTasks" :key="task.id" to="/tasks" class="block py-2.5 hover:bg-soft/40">
              <div class="flex items-center justify-between gap-3">
                <span class="min-w-0 truncate text-[12px] font-semibold">{{ task.repository }}</span>
                <GdBadge :variant="task.status === 'queued' ? 'plain' : 'default'">{{ taskStatusLabel[task.status] ?? '进行中' }}</GdBadge>
              </div>
              <div class="mt-1 flex items-center justify-between gap-3 text-[11px] text-muted">
                <span class="min-w-0 truncate" :title="task.stage">{{ taskModuleLabel[task.module] ?? task.module }} · {{ task.stage }}</span>
                <span class="shrink-0">{{ task.updatedAt }}</span>
              </div>
              <div v-if="taskProgress(task) !== null" class="mt-1.5 flex items-center gap-2">
                <div class="h-1 min-w-0 flex-1 overflow-hidden rounded bg-track">
                  <div class="h-full rounded bg-ink transition-[width] duration-500" :style="{ width: `${taskProgress(task)}%` }" />
                </div>
                <span class="shrink-0 font-mono text-[10.5px] tabular-nums text-muted">{{ Math.round(taskProgress(task)!) }}%</span>
              </div>
            </RouterLink>
          </div>
          <div v-else class="flex h-full items-center py-2">
            <div class="flex w-full items-start gap-3 rounded-lg border border-line bg-soft/30 p-3.5">
              <span class="flex size-9 shrink-0 items-center justify-center rounded-full border border-line bg-panel text-s3">
                <Activity :size="17" />
              </span>
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <p class="m-0 text-[13px] font-semibold text-ink">{{ taskEmptyState.title }}</p>
                  <GdBadge variant="plain">{{ taskEmptyState.badge }}</GdBadge>
                </div>
                <p class="mb-0 mt-1 text-[11.5px] leading-relaxed text-muted">{{ taskEmptyState.description }}</p>
                <RouterLink v-if="!tasks?.length" to="/repositories" class="gd-link mt-2 inline-flex text-[11.5px]">前往仓库 <ArrowRight :size="12" /></RouterLink>
              </div>
            </div>
          </div>
        </div>
        <div class="mt-auto flex items-center justify-between border-t border-line pt-2.5">
          <RouterLink to="/tasks" class="gd-link text-[12px]"><CalendarDays :size="13" /> 查看任务中心</RouterLink>
          <GdBadge v-if="activeTasks.length" variant="plain">{{ activeTasks.length }} 项进行中</GdBadge>
          <span v-else class="text-[11px] text-muted">查看近期任务状态</span>
        </div>
      </GdCard>
    </div>


  </div>
</template>
