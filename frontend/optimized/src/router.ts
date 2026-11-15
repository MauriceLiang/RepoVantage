import { createRouter, createWebHistory } from 'vue-router'
import OverviewPage from '@/pages/Overview/OverviewPage.vue'
import RepositoriesPage from '@/pages/Repositories/RepositoriesPage.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: OverviewPage, meta: { crumb: '工作台', title: '总览', nav: 'overview' } },
    { path: '/repositories', name: 'repositories', component: RepositoriesPage, meta: { crumb: '工作台', title: '仓库', nav: 'repositories' } },
    { path: '/repositories/:id/:tab?', name: 'repository', component: () => import('@/pages/RepositoryAnalysis/RepositoryAnalysisPage.vue'), meta: { crumb: '仓库', title: '仓库分析', nav: 'repositories' } },
    { path: '/compare', name: 'compare', component: () => import('@/pages/Comparison/ComparisonPage.vue'), meta: { crumb: '仓库', title: '项目比较', nav: 'repositories' } },
    { path: '/research', name: 'research', component: () => import('./pages/ResearchAtlasPage.vue'), meta: { crumb: '工作台', title: '仓库研究图谱', nav: 'research' } },
    { path: '/selection', name: 'selection', component: () => import('./pages/SelectionStudioPage.vue'), meta: { crumb: '研究分析', title: '技术选型工作台', nav: 'selection' } },
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
