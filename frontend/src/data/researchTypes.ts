export interface MetricEvidence {
  value: number | null
  unit: string
  sample_count: number | null
  window_start: string | null
  window_end_exclusive: string | null
  as_of: string
  coverage_status: string
  coverage_ratio: number | null
  methodology_version: string
  source_dataset: string
  notes: string | null
}

export interface CapabilityEvidence {
  capability_key: string
  status: 'supported' | 'unsupported' | 'conditional' | 'unknown'
  applicable_version: string | null
  evidence_url: string
  source_checked_at: string
  rationale: string
}

export interface ScenarioCandidate {
  repository_id: number
  full_name: string
  html_url: string
  description: string | null
  language: string | null
  license_spdx: string | null
  eligibility: 'eligible' | 'conditional' | 'ineligible' | 'unknown'
  role: 'compare' | 'reference' | 'supplement'
  reference_group: string | null
  metrics_ready: boolean
  metric_collection_status: string
  inclusion_reason: string
  evidence_refs: string[]
  metrics: Record<string, MetricEvidence>
  capabilities: CapabilityEvidence[]
  capability_evidence_status: 'reviewed' | 'not_reviewed'
}

export interface ScenarioSummary {
  slug: string
  title: string
  category: string
  version: string
  status: string
  published_at: string | null
  as_of: string | null
  candidate_count: number
  ready_count: number
  pending_count: number
}

export interface ScenarioDetail {
  slug: string
  title: string
  category: string
  purpose: string
  hard_constraints: string[]
  version: string
  status: string
  as_of: string | null
  source_datasets: string[]
  window_policy: { activity?: { start: string; end_exclusive: string; weeks: number }; release?: { start: string; end_exclusive: string; days: number } }
  immutable_fingerprint: string | null
  candidates: ScenarioCandidate[]
}

export interface SelectionWeek {
  week_start: string
  commits: number
  prs_opened: number
}

export interface ScenarioVizCandidate {
  repository_id: number
  full_name: string
  role: ScenarioCandidate['role']
  eligibility: ScenarioCandidate['eligibility']
  metrics_ready: boolean
  x: MetricEvidence | undefined
  y: MetricEvidence | undefined
  dimensions: Array<MetricEvidence | null | undefined>
  metrics: Record<string, MetricEvidence>
  capabilities: CapabilityEvidence[]
  weekly_activity: SelectionWeek[] | null
}

export interface ScenarioViz {
  scenario: string
  snapshot_version: string
  as_of: string | null
  activity_window: { start: string; end_exclusive: string; weeks: number } | null
  release_window: { start: string; end_exclusive: string; days: number } | null
  candidates: ScenarioVizCandidate[]
  ranking_available: false
  ranking_reason: string
}
