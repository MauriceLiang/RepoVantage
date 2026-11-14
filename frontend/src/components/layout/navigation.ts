import { ChartNoAxesCombined, Columns2, Folder, Gauge } from 'lucide-vue-next'

export const primaryNavigation = [
  { key: 'overview', label: '总览', to: '/', icon: Gauge },
  { key: 'repositories', label: '仓库', to: '/repositories', icon: Folder },
  { key: 'compare', label: '项目比较', to: '/compare', icon: Columns2 },
  { key: 'research', label: '研究分析', to: '/research', icon: ChartNoAxesCombined },
] as const
