import math
from typing import Any, Literal

from pydantic import Field, StrictBool, field_validator, model_validator

from backend.app.schemas.common import DTO


class ActivityForecast(DTO):
    metric: str
    status: Literal["available", "insufficient_data", "not_applicable", "temporarily_unavailable"]
    method: Literal["statistical_baseline", "descriptive_only"]
    as_of: str | None
    horizon_weeks: int
    prediction: float | None
    prediction_interval: None = None
    interval_validated: bool = False
    model_id: None = None
    model_version: None = None
    data_coverage: str
    history_start: str | None
    history_end: str | None
    target_start: str | None
    target_end: str | None
    source_run_id: str | None
    source_collected_at: str | None
    unit: str
    notes: list[str]


class MaintenancePattern(DTO):
    status: Literal["available", "insufficient_data", "unclassified", "temporarily_unavailable"]
    method: Literal["none", "statistical_baseline", "machine_learning"]
    reason_code: str | None
    model_id: str | None
    model_version: str | None
    feature_schema_version: str | None
    pattern_id: str | None
    pattern_name: str | None
    display_name: str | None = None
    as_of_utc: str | None
    history_start: str | None
    source_run_id: str | None
    source_sha256: str | None
    collected_at: str | None
    coverage: dict[str, str]
    window_weeks: int
    evidence: dict[str, Any]
    limitations: list[str]


class CourseResearchSample(DTO):
    dataset_id: str
    dataset_version: str
    sample_role: Literal["train", "test"]
    data_as_of: str | None
    observation_start: str | None
    observation_end_exclusive: str | None


class RepositoryEvaluation(DTO):
    repository_id: int
    metrics: list[ActivityForecast]
    limitations: list[str]
    maintenance_pattern: MaintenancePattern
    recent_activity_change: dict[str, Any]
    activity_trend: dict[str, Any]
    activity_anomaly: dict[str, Any]
    research_sample: CourseResearchSample | None = None


class ModelDecision(DTO):
    model_id: str
    status: Literal["available", "model_unavailable", "baseline_only", "research_only", "disabled"]
    reason: str
    version: str | None = None
    artifact_hash: str | None = None
    feature_schema_version: str | None = None
    training_data_hash: str | None = None
    approval_status: str | None = None
    loaded_status: str | None = None
    supported_scope: list[int] = Field(default_factory=list)
    last_healthcheck: str | None = None
    fallback_method: str | None = None
    approved_at: str | None = None


class ModelDecisions(DTO):
    models: list[ModelDecision]


class SelectionWeights(DTO):
    commits_weekly_mean: float = Field(default=0, ge=0, le=10, allow_inf_nan=False)
    issue_median_hours: float = Field(default=0, ge=0, le=10, allow_inf_nan=False)
    pr_median_hours: float = Field(default=0, ge=0, le=10, allow_inf_nan=False)
    release_interval_days: float = Field(default=0, ge=0, le=10, allow_inf_nan=False)

    @model_validator(mode="after")
    def require_weight(self):
        total = sum(self.model_dump().values())
        if not total or not math.isfinite(total):
            raise ValueError("至少选择一个大于零的指标权重")
        return self


class SelectionRequest(DTO):
    repository_ids: list[int] = Field(min_length=2, max_length=5)
    scenario: str | None = Field(default=None, max_length=500)
    candidate_group: str | None = Field(default=None, max_length=200)
    candidates_confirmed: StrictBool | None = None
    window_days: Literal[30, 90, 180] = 90
    allowed_languages: list[str] = Field(default_factory=list, max_length=20)
    allowed_licenses: list[str] = Field(default_factory=list, max_length=20)
    weights: SelectionWeights

    @field_validator("repository_ids")
    @classmethod
    def distinct_repositories(cls, value):
        if len(set(value)) != len(value) or any(item <= 0 for item in value):
            raise ValueError("仓库 ID 必须为不重复的正整数")
        return value

    @field_validator("scenario", "candidate_group")
    @classmethod
    def nonblank_text(cls, value):
        if value is None:
            return None
        return value.strip() or None

    @field_validator("allowed_languages", "allowed_licenses")
    @classmethod
    def nonblank_filters(cls, value):
        if any(not item.strip() or len(item) > 100 for item in value):
            raise ValueError("筛选项不能为空或超过 100 字符")
        return [item.strip() for item in value]


class SelectionResult(DTO):
    status: Literal["available", "insufficient_data"]
    method: Literal["rule_based"]
    scoring_version: Literal["weighted-relative-v4"]
    scenario: str
    candidate_group: str
    comparison_basis: dict[str, Any]
    weights: dict[str, float]
    ranking: list[dict[str, Any]]
    excluded: list[dict[str, Any]]
    sensitivity: list[dict[str, Any]]
    maintenance: dict[str, Any]
    notes: list[str]
    report_markdown: str
    result_signature: str


class SelectionFeedbackCreate(DTO):
    selection: SelectionRequest
    result_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    chosen_repository_id: int = Field(gt=0)
    choice_kind: Literal["preference", "actual_choice"]
    reason: str = Field(default="", max_length=500)
    consent: StrictBool

    @field_validator("consent")
    @classmethod
    def consent_required(cls, value):
        if not value:
            raise ValueError("保存反馈需要明确同意")
        return value


class SelectionFeedback(DTO):
    feedback_id: str
    scenario: str
    candidate_group: str
    chosen_repository_id: int
    chosen_repository_name: str
    choice_kind: Literal["preference", "actual_choice"]
    reason: str
    created_at: str
    review_status: Literal["pending"]
