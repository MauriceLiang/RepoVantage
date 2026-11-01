import type { RepositoryDataSource } from '@/services/repositoryDataSource'
import { MockRepositoryDataSource } from '@/services/mockRepositoryDataSource'
import { HttpRepositoryDataSource } from '@/services/httpRepositoryDataSource'

let instance: RepositoryDataSource | null = null

/**
 * 页面访问数据的统一入口。
 *
 * 只有显式选择 mock 模式才使用演示数据；普通开发和生产环境使用本机浏览器网关。
 * 内部 API 密钥由服务端持有，不会进入浏览器构建产物。
 */
export function useDataSource(): RepositoryDataSource {
  if (!instance) {
    instance = import.meta.env.VITE_DATA_MODE === 'mock'
      ? new MockRepositoryDataSource()
      : new HttpRepositoryDataSource()
  }
  return instance
}
