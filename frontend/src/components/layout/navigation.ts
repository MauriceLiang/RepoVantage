import { Folder, Gauge } from 'lucide-vue-next'

export const primaryNavigation = [
  { key: 'overview', label: '概览', to: '/', icon: Gauge },
  { key: 'repositories', label: '仓库', to: '/repositories', icon: Folder },
] as const
