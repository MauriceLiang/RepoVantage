import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: () => import('@/pages/Overview/OverviewPage.vue'), meta: { crumb: '工作区', title: '概览', nav: 'overview' } },
    { path: '/repositories', name: 'repositories', component: () => import('@/pages/Repositories/RepositoriesPage.vue'), meta: { crumb: '工作台', title: '仓库', nav: 'repositories' } },
    {
      path: '/repositories/:id/:tab?', name: 'repository',
      component: () => import('@/pages/RepositoryAnalysis/RepositoryAnalysisPage.vue'),
      beforeEnter: (to) => to.params.tab === 'analysis'
        ? { name: 'repository', params: { id: to.params.id, tab: 'overview' }, replace: true }
        : true,
      meta: { crumb: '仓库', title: '仓库详情', nav: 'repositories' },
    },
    { path: '/compare', name: 'compare', component: () => import('@/pages/Comparison/ComparisonPage.vue'), meta: { crumb: '仓库', title: '项目比较', nav: 'repositories' } },
    { path: '/research', redirect: { name: 'overview' } },
    { path: '/research/ml-data', redirect: { name: 'machine-learning-data' } },
    { path: '/research/:pathMatch(.*)*', redirect: { name: 'overview' } },
    { path: '/machine-learning', name: 'machine-learning-data', component: () => import('@/pages/Research/MachineLearningDataPage.vue'), meta: { crumb: '工作区', title: '机器学习数据', nav: 'machine-learning' } },
    { path: '/selection', redirect: { name: 'repositories' } },
    { path: '/selection/candidates', redirect: { name: 'repositories' } },
    { path: '/tasks', name: 'tasks', component: () => import('@/pages/Tasks/TasksPage.vue'), meta: { crumb: '工作台', title: '任务', nav: 'tasks' } },
    { path: '/settings', name: 'settings', component: () => import('@/pages/Settings/SettingsPage.vue'), meta: { crumb: '工作台', title: '设置', nav: 'settings' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((to) => {
  const title = to.meta.title ?? ''
  document.title = title ? `${title} · RepoVantage` : 'RepoVantage · 开源项目数据分析'
})

export default router
