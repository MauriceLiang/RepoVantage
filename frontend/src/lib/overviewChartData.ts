import type { RepositorySummary } from '@/services/types'

export const UNKNOWN_LANGUAGE = '未知语言'
const DAY_MS = 24 * 60 * 60 * 1000

export type PushBucketKey = '7d' | '30d' | '90d' | '365d' | 'older' | 'missing' | 'future'

export interface LanguageDatum {
  key: string
  label: string
  count: number
  percent: number
  color: string
  languageKeys: string[]
  repositoryIds: string[]
}

export interface StarsBucketDatum {
  key: string
  label: string
  min: number
  max: number
  count: number
  percent: number
  color: string
  repositoryIds: string[]
}

export interface StarsPoint {
  repositoryId: string
  fullName: string
  stars: number
  xPlot: number
  lane: number
  bucketKey: string
}

export interface PopularityPoint {
  repositoryId: string
  fullName: string
  language: string
  stars: number
  forks: number
  xPlot: number
  yPlot: number
  pointSize: number
  opacity: number
  isOutlier: boolean
}

export interface PushPoint {
  repositoryId: string
  fullName: string
  pushedAt: string | null
  ageDays: number | null
  bucketKey: PushBucketKey
}

export interface OverviewChartData {
  repositories: RepositorySummary[]
  languageRows: LanguageDatum[]
  languageKeys: string[]
  starsBuckets: StarsBucketDatum[]
  starsPoints: StarsPoint[]
  validStarsCount: number
  invalidStarsCount: number
  popularityPoints: PopularityPoint[]
  popularityMedianStars: number | null
  popularityMedianForks: number | null
  popularityOverlapGroups: Array<{ fullName: string; repositoryIds: string[]; count: number }>
  pushPoints: PushPoint[]
  active30Count: number
  active30Rate: number
  missingPushCount: number
  invalidPushCount: number
  futurePushCount: number
}

const STAR_BUCKETS = [
  { key: 'zero', label: '0', min: 0, max: 0, color: '#718096' },
  { key: 'b1', label: '1–100', min: 1, max: 100, color: '#b6c8db' },
  { key: 'b2', label: '101–1k', min: 101, max: 1_000, color: '#8da9c4' },
  { key: 'b3', label: '1k–10k', min: 1_001, max: 10_000, color: '#6689ac' },
  { key: 'b4', label: '10k–100k', min: 10_001, max: 100_000, color: '#477196' },
  { key: 'b5', label: '100k+', min: 100_001, max: Number.POSITIVE_INFINITY, color: '#315a7a' },
] as const

const FIXED_LANGUAGE_COLORS: Record<string, string> = {
  Python: '#3776ab', JavaScript: '#d4a72c', TypeScript: '#3178c6', Java: '#b07219', Go: '#00add8',
  Rust: '#b7410e', 'C#': '#68217a', 'C++': '#f34b7d', C: '#555555', Ruby: '#701516', Swift: '#f05138',
  Kotlin: '#a97bff', PHP: '#4f5d95', Dart: '#00b4ab', Shell: '#89e051', 'Jupyter Notebook': '#da5b0b',
}
const LANGUAGE_SERIES = ['#4f7cac', '#42a88a', '#cd9a42', '#9575b8', '#cf7188', '#5489a2', '#7e8d9b', '#46a9b5', '#8b9c63', '#b57954']

export function languageColor(language: string): string {
  const label = language.trim() || UNKNOWN_LANGUAGE
  if (label === UNKNOWN_LANGUAGE || label === '其他语言') return '#89939e'
  const fixed = FIXED_LANGUAGE_COLORS[label]
  if (fixed) return fixed
  let hash = 0
  for (let index = 0; index < label.length; index += 1) hash = (hash * 31 + label.charCodeAt(index)) >>> 0
  return LANGUAGE_SERIES[hash % LANGUAGE_SERIES.length]
}

function uniqueRepositories(repositories: RepositorySummary[]): RepositorySummary[] {
  const seen = new Set<string>()
  return repositories.filter((repository) => {
    if (!repository.id || seen.has(repository.id)) return false
    seen.add(repository.id)
    return true
  })
}

function normalizedLanguage(language: string | null | undefined): string {
  return language?.trim() || UNKNOWN_LANGUAGE
}

function isCount(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value) && Number.isInteger(value) && value >= 0
}

export function getStarsBucketKey(stars: number | null | undefined): string | null {
  if (!isCount(stars)) return null
  return STAR_BUCKETS.find((bucket) => stars >= bucket.min && stars <= bucket.max)?.key ?? null
}

export function getPushBucketKey(pushedAt: string | null | undefined, asOfMs: number): PushBucketKey {
  if (!pushedAt) return 'missing'
  const timestamp = Date.parse(pushedAt)
  if (!Number.isFinite(timestamp)) return 'missing'
  const elapsedMs = asOfMs - timestamp
  if (elapsedMs < 0) return 'future'
  const ageDays = elapsedMs / DAY_MS
  if (ageDays <= 7) return '7d'
  if (ageDays <= 30) return '30d'
  if (ageDays <= 90) return '90d'
  if (ageDays <= 365) return '365d'
  return 'older'
}

export function getMedian(values: number[]): number | null {
  if (!values.length) return null
  const sorted = [...values].sort((left, right) => left - right)
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2
}

function buildLanguageRows(repositories: RepositorySummary[]): { rows: LanguageDatum[]; languages: string[] } {
  const idsByLanguage = new Map<string, string[]>()
  for (const repository of repositories) {
    const language = normalizedLanguage(repository.language)
    idsByLanguage.set(language, [...(idsByLanguage.get(language) ?? []), repository.id])
  }
  const languages = [...idsByLanguage.keys()].sort((left, right) =>
    (idsByLanguage.get(right)?.length ?? 0) - (idsByLanguage.get(left)?.length ?? 0) || left.localeCompare(right))
  const known = languages.filter((language) => language !== UNKNOWN_LANGUAGE)
  const topLanguages = known.slice(0, 5)
  const remainder = known.slice(5)
  const descriptors: Array<{ key: string; label: string; languageKeys: string[] }> = topLanguages.map((language) => ({ key: `language:${language}`, label: language, languageKeys: [language] }))
  if (remainder.length) descriptors.push({ key: 'other', label: '其他语言', languageKeys: remainder })
  if (idsByLanguage.has(UNKNOWN_LANGUAGE)) descriptors.push({ key: 'unknown', label: UNKNOWN_LANGUAGE, languageKeys: [UNKNOWN_LANGUAGE] })
  const total = repositories.length
  return {
    languages,
    rows: descriptors.map((descriptor) => {
      const repositoryIds = descriptor.languageKeys.flatMap((language) => idsByLanguage.get(language) ?? [])
      return {
        ...descriptor,
        count: repositoryIds.length,
        percent: total ? repositoryIds.length / total * 100 : 0,
        color: descriptor.key === 'other' || descriptor.key === 'unknown' ? languageColor(descriptor.label) : languageColor(descriptor.languageKeys[0]),
        repositoryIds,
      }
    }),
  }
}

function buildStars(repositories: RepositorySummary[]) {
  const buckets: StarsBucketDatum[] = STAR_BUCKETS.map((bucket) => ({ ...bucket, count: 0, percent: 0, repositoryIds: [] }))
  const valid = repositories.flatMap((repository) => {
    const value = repository.stars
    if (!isCount(value)) return []
    const bucket = buckets.find((item) => value >= item.min && value <= item.max)
    if (!bucket) return []
    bucket.count += 1
    bucket.repositoryIds.push(repository.id)
    return [{ repository, stars: value, bucketKey: bucket.key }]
  })
  const validCount = valid.length
  for (const bucket of buckets) bucket.percent = validCount ? bucket.count / validCount * 100 : 0

  const duplicates = new Map<number, typeof valid>()
  for (const point of valid) duplicates.set(point.stars, [...(duplicates.get(point.stars) ?? []), point])
  const starsPoints = valid.map(({ repository, stars, bucketKey }) => {
    const sameValue = duplicates.get(stars) ?? []
    const index = sameValue.findIndex((item) => item.repository.id === repository.id)
    const lane = sameValue.length <= 1 ? 0.5 : 0.15 + (index / (sameValue.length - 1)) * 0.7
    return { repositoryId: repository.id, fullName: repository.fullName, stars, xPlot: Math.log1p(stars), lane, bucketKey }
  })
  return { buckets, valid, starsPoints }
}

function buildPopularity(repositories: RepositorySummary[]) {
  const topLanguages = buildLanguageRows(repositories).languages.filter((language) => language !== UNKNOWN_LANGUAGE).slice(0, 5)
  const languageForColor = (repository: RepositorySummary) => {
    const language = normalizedLanguage(repository.language)
    return language === UNKNOWN_LANGUAGE || topLanguages.includes(language) ? language : '其他语言'
  }
  const paired = repositories.flatMap((repository) => {
    const stars = repository.stars
    const forks = repository.forks
    if (!isCount(stars) || !isCount(forks)) return []
    return [{ repository, stars, forks }]
  })
  const medianStars = getMedian(paired.map((item) => item.stars))
  const medianForks = getMedian(paired.map((item) => item.forks))
  const transformed = paired.map(({ repository, stars, forks }) => ({
    repository,
    stars,
    forks,
    xPlot: Math.log1p(stars),
    yPlot: Math.log1p(forks),
    distance: medianStars === null || medianForks === null ? 0 : Math.hypot(Math.log1p(stars) - Math.log1p(medianStars), Math.log1p(forks) - Math.log1p(medianForks)),
  }))
  const outlierIds = new Set([...transformed].sort((left, right) => right.distance - left.distance || left.repository.id.localeCompare(right.repository.id)).slice(0, Math.min(3, transformed.length)).map((item) => item.repository.id))
  const groups = new Map<string, typeof transformed>()
  for (const item of transformed) {
    const key = `${item.stars}:${item.forks}`
    groups.set(key, [...(groups.get(key) ?? []), item])
  }
  const points = transformed.map(({ repository, stars, forks, xPlot, yPlot }) => ({
    repositoryId: repository.id,
    fullName: repository.fullName,
    language: languageForColor(repository),
    stars,
    forks,
    xPlot,
    yPlot,
    pointSize: 8,
    opacity: 0.82,
    isOutlier: outlierIds.has(repository.id),
  }))
  const overlapGroups = [...groups.values()].filter((group) => group.length > 1).map((group) => ({
    fullName: group[0].repository.fullName,
    repositoryIds: group.map((item) => item.repository.id),
    count: group.length,
  }))
  return { points, medianStars, medianForks, overlapGroups }
}

function buildPush(repositories: RepositorySummary[], asOfMs: number) {
  let invalidPushCount = 0
  const points = repositories.map((repository): PushPoint => {
    const value = repository.pushedAt
    if (!value) return { repositoryId: repository.id, fullName: repository.fullName, pushedAt: null, ageDays: null, bucketKey: 'missing' }
    const timestamp = Date.parse(value)
    if (!Number.isFinite(timestamp)) {
      invalidPushCount += 1
      return { repositoryId: repository.id, fullName: repository.fullName, pushedAt: value, ageDays: null, bucketKey: 'missing' }
    }
    const ageDays = (asOfMs - timestamp) / DAY_MS
    const bucketKey = getPushBucketKey(value, asOfMs)
    return { repositoryId: repository.id, fullName: repository.fullName, pushedAt: value, ageDays, bucketKey }
  })
  const active30Count = points.filter((point) => point.bucketKey === '7d' || point.bucketKey === '30d').length
  const missingPushCount = points.filter((point) => point.bucketKey === 'missing').length
  const futurePushCount = points.filter((point) => point.bucketKey === 'future').length
  return {
    points: points.sort((left, right) => {
      if (left.ageDays === null && right.ageDays === null) return left.fullName.localeCompare(right.fullName)
      if (left.ageDays === null) return 1
      if (right.ageDays === null) return -1
      return left.ageDays - right.ageDays || left.fullName.localeCompare(right.fullName)
    }),
    active30Count,
    active30Rate: repositories.length ? active30Count / repositories.length * 100 : 0,
    missingPushCount,
    invalidPushCount,
    futurePushCount,
  }
}

export function buildOverviewChartData(input: { repositories: RepositorySummary[]; asOfMs: number }): OverviewChartData {
  const repositories = uniqueRepositories(input.repositories)
  const languages = buildLanguageRows(repositories)
  const stars = buildStars(repositories)
  const popularity = buildPopularity(repositories)
  const push = buildPush(repositories, input.asOfMs)
  return {
    repositories,
    languageRows: languages.rows,
    languageKeys: languages.languages,
    starsBuckets: stars.buckets,
    starsPoints: stars.starsPoints,
    validStarsCount: stars.valid.length,
    invalidStarsCount: repositories.filter((repository) => repository.stars !== null && !isCount(repository.stars)).length,
    popularityPoints: popularity.points,
    popularityMedianStars: popularity.medianStars,
    popularityMedianForks: popularity.medianForks,
    popularityOverlapGroups: popularity.overlapGroups,
    pushPoints: push.points,
    active30Count: push.active30Count,
    active30Rate: push.active30Rate,
    missingPushCount: push.missingPushCount,
    invalidPushCount: push.invalidPushCount,
    futurePushCount: push.futurePushCount,
  }
}
