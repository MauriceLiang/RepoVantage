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
              <h2 id="about-project-background-title" class="m-0 text-[16px] font-semibold">项目背景</h2>
              <div class="mt-3 flex flex-col gap-4 text-[14px] leading-[1.85] text-muted">
                <p class="m-0">作为一名个人开发者，我曾在项目开发中面对多个功能相近的 GitHub 开源方案，却很难判断哪个更适合自己。只看项目介绍和 Star 数，我仍不知道该选哪一个，还得逐个查看 Commit、Issue、PR 和 Release，手动梳理项目的维护与协作情况。</p>
                <p class="m-0">为了减少选型时的反复查找，我创建了 RepoVantage。它从 GitHubDA 逐步发展而来，把开发活动、Issue 与 PR 处理、版本发布整理成趋势与时间线，并支持按一致的观察范围比较多个仓库。</p>
              </div>
              <h3 class="mb-0 mt-5 border-t border-line pt-4 text-[13px] font-semibold text-ink">使用示例：团队选择开源组件</h3>
              <div class="mt-3 flex flex-col gap-4 text-[14px] leading-[1.85] text-muted">
                <p class="m-0">例如，挑选开源组件时，可以同时观察几个候选仓库的近期 Commit 活动、Issue 与 PR 处理时长和 Release 节奏，先找出值得继续了解的项目。</p>
                <p class="m-0">如果发现某个项目的更新减少，或版本间隔明显拉长，再查看趋势和版本记录，并结合功能、许可证与安全性判断它是否适用。</p>
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
