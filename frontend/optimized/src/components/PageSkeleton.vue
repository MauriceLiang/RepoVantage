<template>
  <div class="page-skeleton" role="status" aria-label="页面加载中">
    <div>
      <div class="skeleton-block skeleton-title" />
      <div class="skeleton-block skeleton-copy" />
    </div>
    <div class="skeleton-kpis" aria-hidden="true">
      <div v-for="item in 4" :key="item" class="skeleton-block skeleton-kpi" />
    </div>
    <div class="skeleton-panels" aria-hidden="true">
      <section v-for="item in 2" :key="item" class="skeleton-card skeleton-card--chart">
        <div class="skeleton-block skeleton-line" />
        <div class="skeleton-block skeleton-line--wide" />
        <div class="skeleton-block skeleton-chart" />
      </section>
    </div>
  </div>
</template>
