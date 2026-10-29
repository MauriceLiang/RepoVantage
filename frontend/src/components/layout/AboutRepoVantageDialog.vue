<script setup lang="ts">
import { Info, X } from 'lucide-vue-next'
import { DialogClose, DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle, DialogTrigger } from 'reka-ui'
</script>

<template>
  <DialogRoot :modal="true">
    <DialogTrigger as-child>
      <button
        type="button"
        aria-label="关于 RepoVantage"
        title="关于 RepoVantage"
        data-testid="about-repovantage-trigger"
        class="grid size-[30px] shrink-0 place-items-center rounded-md text-muted transition-colors hover:bg-track hover:text-ink"
      >
        <Info :size="16" aria-hidden="true" />
      </button>
    </DialogTrigger>

    <DialogPortal>
      <DialogOverlay class="gd-about-overlay fixed inset-0 z-40 bg-black/32" />
      <DialogContent
        aria-modal="true"
        data-testid="about-repovantage-dialog"
        class="gd-about-dialog fixed left-1/2 top-1/2 z-50 flex -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-xl border border-line bg-panel shadow-[0_18px_60px_rgb(0_0_0/0.24)] outline-none"
      >
        <header class="flex shrink-0 items-start justify-between gap-4 border-b border-line px-4 py-3.5 sm:px-6 sm:py-4">
          <div class="min-w-0">
            <DialogTitle class="m-0 text-[18px] font-semibold leading-snug">关于 RepoVantage</DialogTitle>
            <DialogDescription class="mt-1 text-[12px] leading-relaxed text-muted">项目背景、意义与使用边界</DialogDescription>
          </div>
          <DialogClose as-child>
            <button
              type="button"
              aria-label="关闭关于 RepoVantage"
              title="关闭"
              data-testid="about-repovantage-close"
              class="grid size-8 shrink-0 place-items-center rounded-md text-muted transition-colors hover:bg-track hover:text-ink"
            >
              <X :size="17" aria-hidden="true" />
            </button>
          </DialogClose>
        </header>

        <div
          data-testid="about-repovantage-scroll"
          role="region"
          aria-label="项目背景与意义内容"
          tabindex="0"
          class="gd-about-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4 sm:px-6 sm:py-5"
        >
          <div class="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)] lg:gap-7">
            <section aria-labelledby="about-project-background-title" class="min-w-0">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <h2 id="about-project-background-title" class="m-0 text-[16px] font-semibold">项目背景</h2>
                <span class="rounded-full border border-line bg-soft px-2 py-1 text-[10.5px] font-medium text-muted">常见团队选型情境</span>
              </div>
              <p class="mb-0 mt-2 text-[12px] leading-[1.7] text-muted">这是常见的团队选型情境示例，不代表 RepoVantage 的真实创始经历。</p>
              <div class="mt-4 flex flex-col gap-4 text-[14px] leading-[1.85] text-muted">
                <p class="m-0">一个团队准备为新项目选择开源组件，搜索后发现几个功能相近的 GitHub 仓库。它们都有介绍文档，也有不同数量的 Stars 和 Forks。但要进一步了解这些项目，还会遇到许多具体问题：最近是否持续有开发活动？已经关闭的 Issue 通常经历了多长时间？PR 的协作情况如何？过去一年发布过哪些版本，发布之间的间隔又是怎样的？</p>
                <p class="m-0">这些信息虽然都能在 GitHub 上找到，却分布在提交记录、Issue、PR 和 Release 等不同页面。查看一个仓库需要来回切换；比较多个仓库时，还需要手动整理时间范围和统计口径。仅看某个数字或某一天的状态，也很难理解项目在一段时间内的变化。</p>
                <p class="m-0">RepoVantage 希望把这些分散的信息组织成更容易阅读和比较的数据。用户输入公开仓库后，系统采集可用的开发与协作数据，通过趋势、分布和时间线展示项目在所选时间范围内发生了什么。用户既可以观察单个项目，也可以在满足数据条件时比较多个项目，或围绕选定样本开展研究。</p>
              </div>
            </section>

            <section aria-labelledby="about-project-meaning-title" class="min-w-0">
              <h2 id="about-project-meaning-title" class="m-0 text-[16px] font-semibold">项目的意义</h2>
              <ol class="mt-3 m-0 list-none divide-y divide-line p-0">
                <li class="flex min-w-0 gap-3 py-3 first:pt-0">
                  <span aria-hidden="true" class="flex size-7 shrink-0 items-center justify-center rounded-full bg-soft font-mono text-[10px] font-semibold text-muted">01</span>
                  <p class="m-0 min-w-0 text-[13px] leading-[1.75]"><strong class="font-semibold text-ink">更快认识陌生项目：</strong><span class="text-muted">把提交、协作和发布信息集中起来，帮助使用者从多个维度了解项目近况，减少在不同页面之间反复查找和整理的工作。</span></p>
                </li>
                <li class="flex min-w-0 gap-3 py-3">
                  <span aria-hidden="true" class="flex size-7 shrink-0 items-center justify-center rounded-full bg-soft font-mono text-[10px] font-semibold text-muted">02</span>
                  <p class="m-0 min-w-0 text-[13px] leading-[1.75]"><strong class="font-semibold text-ink">为技术选型提供线索：</strong><span class="text-muted">比较候选项目的活动变化、已结束 Issue 和 PR 的处理耗时及发布节奏，帮助团队发现需要继续核查的问题。例如，两个项目都很受关注，但近期发布节奏不同，就可以进一步查看版本内容和维护情况。</span></p>
                </li>
                <li class="flex min-w-0 gap-3 py-3">
                  <span aria-hidden="true" class="flex size-7 shrink-0 items-center justify-center rounded-full bg-soft font-mono text-[10px] font-semibold text-muted">03</span>
                  <p class="m-0 min-w-0 text-[13px] leading-[1.75]"><strong class="font-semibold text-ink">支持项目观察与复盘：</strong><span class="text-muted">维护者和参与者可以查看一段时间内的开发活动和协作数据，发现值得追问的变化，再结合具体 Issue、PR 或版本记录分析原因。</span></p>
                </li>
                <li class="flex min-w-0 gap-3 py-3">
                  <span aria-hidden="true" class="flex size-7 shrink-0 items-center justify-center rounded-full bg-soft font-mono text-[10px] font-semibold text-muted">04</span>
                  <p class="m-0 min-w-0 text-[13px] leading-[1.75]"><strong class="font-semibold text-ink">帮助开展开源研究：</strong><span class="text-muted">围绕明确的样本查看分组统计和数据分布，导出样本成员与统计结果，为研究者整理材料和讨论现象提供支持。研究结论仍需结合样本范围与数据质量理解。</span></p>
                </li>
                <li class="flex min-w-0 gap-3 py-3 last:pb-0">
                  <span aria-hidden="true" class="flex size-7 shrink-0 items-center justify-center rounded-full bg-soft font-mono text-[10px] font-semibold text-muted">05</span>
                  <p class="m-0 min-w-0 text-[13px] leading-[1.75]"><strong class="font-semibold text-ink">让讨论有清楚的数据依据：</strong><span class="text-muted">展示采集时间、观察范围和覆盖状态，让使用者知道数据来自哪里、能说明什么，也能看见尚未采到或样本不足的部分。</span></p>
                </li>
              </ol>
              <p class="mb-0 mt-4 border-t border-line pt-3 text-[13px] leading-[1.75] text-muted">RepoVantage 提供的是观察和比较的依据。项目是否适合某个具体用途，还需要结合功能、兼容性、安全和许可证等因素进一步判断。</p>
            </section>
          </div>
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.gd-about-dialog {
  width: min(980px, calc(100vw - 32px));
  max-height: min(88vh, 820px);
  max-height: min(88dvh, 820px);
}
.gd-about-scroll:focus-visible {
  outline: 2px solid var(--gd-ink);
  outline-offset: -3px;
}
.gd-about-overlay[data-state='open'] { animation: gd-about-fade-in 0.18s ease; }
.gd-about-overlay[data-state='closed'] { animation: gd-about-fade-out 0.16s ease; }
@media (max-width: 480px) {
  .gd-about-dialog {
    width: calc(100vw - 24px);
    max-height: calc(100dvh - 24px);
  }
}
@keyframes gd-about-fade-in { from { opacity: 0 } to { opacity: 1 } }
@keyframes gd-about-fade-out { from { opacity: 1 } to { opacity: 0 } }
</style>
