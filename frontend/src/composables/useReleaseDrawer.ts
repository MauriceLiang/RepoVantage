import type { ReleaseRecord } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import { useDataSource } from './useDataSource'

let requestSequence = 0

/** 打开版本详情；只允许最新请求更新当前抽屉。 */
export function useReleaseDrawer(repositoryId: () => string) {
  const ui = useUiStore()
  const dataSource = useDataSource()

  async function openRelease(release: ReleaseRecord) {
    const repoId = repositoryId()
    const requestId = String(++requestSequence)
    const payload: Record<string, string> = {
      repositoryId: repoId,
      requestId,
      tag: release.tag,
      identifierType: release.identifierType ?? 'tag',
      date: release.publishedAt,
      type: release.prerelease ? '预发布（prerelease）' : '正式发布',
      interval: release.intervalDays === null ? '—' : `${release.intervalDays.toLocaleString('en-US', { maximumFractionDigits: 1 })} 天`,
      bodyStatus: 'loading',
    }
    ui.openDrawer('release', payload)
    try {
      const detail = await dataSource.getReleaseDetails(repoId, release.tag)
      if (ui.drawerKind !== 'release' || ui.drawerPayload?.requestId !== requestId) return
      ui.openDrawer('release', { ...payload, bodyStatus: 'ready', body: detail.body ?? '', releaseName: detail.name ?? '' })
    } catch (error) {
      if (ui.drawerKind !== 'release' || ui.drawerPayload?.requestId !== requestId) return
      ui.openDrawer('release', { ...payload, bodyStatus: 'error', bodyError: error instanceof Error ? error.message : '无法读取该版本的发布说明' })
    }
  }

  return { openRelease }
}
