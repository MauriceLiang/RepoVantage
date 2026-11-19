export interface AtlasPoint {
  repository_id: number
  full_name: string
  language: string
  sample_role: string | null
  stars: number | null
  weekly_commit_mean: number
  weekly_pr_open_mean: number
  observation_window: { start: string; end_exclusive: string; weeks: number }
  coverage: { commits: string; prs_opened: string }
  weekly_trace: Array<{ week_start: string; commits: number; prs_opened: number }>
}

export type AtlasViewMode = 'activity-mean' | 'activity-volatility' | 'pr-trend'

export type AtlasSelectionRange = [[number, number], [number, number]]

export interface AtlasChartPoint extends AtlasPoint {
  x_value: number
  y_value: number
  x_position: number
  y_position: number
  x_label: string
  y_label: string
  x_value_label: string
  y_value_label: string
}

export interface AtlasBrushSelection {
  repository_ids: number[]
  selection: AtlasSelectionRange
  reset: boolean
}

export interface AtlasResponse {
  dataset_id: string
  data_as_of: string
  observation_window: { start: string; end_exclusive: string; weeks: number }
  repository_count: number
  point_count: number
  excluded_count: number
  excluded_reasons: Record<string, number>
  weekly_record_count: number
  coordinates: { x: string; y: string; stars: string }
  points: AtlasPoint[]
}

export interface CourseMlPerformance {
  label: string
  model_id: string
  macro_f1: number
  balanced_accuracy: number
  up_precision: number
  up_recall: number
  up_f1: number
  class_metrics: Record<string, { precision: number; recall: number; f1: number; support: number }>
}

export interface CourseMachineLearningEvaluation {
  dataset_id: string
  dataset_version: string
  data_as_of: string
  m1: {
    status: 'candidate'
    selected_k: number
    training_repositories: number
    test_repositories: number
    train_silhouette: number
    test_silhouette: number
    size_only_test_silhouette: number
    mean_seed_pairwise_ari: number
    cluster_counts: Array<{ label: string; count: number }>
    limitations: string[]
  }
  m2: {
    status: 'candidate'
    selected_model_id: string
    test_origin: string
    training_repositories: number
    test_repositories: number
    sample_count: number
    actual_class_counts: Record<string, number>
    confusion_matrix_labels: string[]
    confusion_matrix: number[][]
    selected_candidate: CourseMlPerformance
    baselines: CourseMlPerformance[]
    limitations: string[]
  }
  m3: {
    status: 'preserved_mad_rule'
    method: 'statistical_rule'
    rule: string
    timeline_available: boolean
    timeline_reason: string
    limitations: string[]
  }
}

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
