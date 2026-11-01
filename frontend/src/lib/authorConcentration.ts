export interface AuthorDistributionBucket {
  commits: number
  authors: number
}

/**
 * Summarize identified authors in the collected sample, not all GitHub history.
 * Buckets are ordered by contributions to build the Lorenz curve; trapezoid
 * areas yield the Gini coefficient. A reverse pass finds how many top authors
 * account for at least half of those identified commits.
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
