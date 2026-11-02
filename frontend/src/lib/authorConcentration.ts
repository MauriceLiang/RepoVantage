export interface AuthorDistributionBucket {
  commits: number
  authors: number
}

/**
 * 汇总本次采集样本中可识别的作者，不代表 GitHub 的全部历史。
 * 按提交量从小到大排列分组并构造洛伦兹曲线，以梯形面积计算基尼系数；
 * 再倒序累计，求出贡献至少一半已识别提交所需的最少作者数。
 */
export function summarizeAuthorDistribution(buckets: AuthorDistributionBucket[]) {
  const sorted = [...buckets].sort((a, b) => a.commits - b.commits)
  const authors = sorted.reduce((sum, bucket) => sum + bucket.authors, 0)
  const commits = sorted.reduce((sum, bucket) => sum + bucket.commits * bucket.authors, 0)
  if (!authors || !commits) return null

  let cumulativeAuthors = 0
  let cumulativeCommits = 0
  let previousX = 0
  let previousY = 0
  let twiceArea = 0
  const points = [{ authors: 0, commits: 0, value: [0, 0] }]
  for (const bucket of sorted) {
    cumulativeAuthors += bucket.authors
    cumulativeCommits += bucket.commits * bucket.authors
    const x = cumulativeAuthors / authors
    const y = cumulativeCommits / commits
    twiceArea += (x - previousX) * (y + previousY)
    points.push({ authors: cumulativeAuthors, commits: cumulativeCommits, value: [x * 100, y * 100] })
    previousX = x
    previousY = y
  }

  let covered = 0
  let contributors = 0
  for (const bucket of sorted.reverse()) {
    const needed = Math.min(bucket.authors, Math.ceil((commits / 2 - covered) / bucket.commits))
    contributors += needed
    covered += needed * bucket.commits
    if (covered >= commits / 2) break
  }
  return { authors, commits, gini: Math.max(0, 1 - twiceArea), contributors, points }
}
