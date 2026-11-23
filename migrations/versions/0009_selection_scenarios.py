"""Add versioned same-scenario selection evidence."""
import sqlalchemy as sa
from alembic import op

revision = "0009_selection_scenarios"
down_revision = "0008_maintenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "selection_scenarios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("hard_constraints_json", sa.Text(), nullable=False),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_table(
        "selection_scenario_candidates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scenario_id", sa.Integer(), sa.ForeignKey("selection_scenarios.id", ondelete="CASCADE")),
        sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.repository_id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("reference_group", sa.String(100)),
        sa.Column("source_order", sa.Integer(), nullable=False),
        sa.Column("inclusion_reason", sa.Text(), nullable=False),
        sa.Column("eligibility", sa.String(20), nullable=False),
        sa.Column("evidence_refs_json", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("review_method", sa.String(100), nullable=False),
        sa.Column("exclude_reason", sa.Text()),
        sa.Column("metric_collection_status", sa.String(30), nullable=False),
        sa.UniqueConstraint("scenario_id", "repository_id", name="uq_selection_scenario_candidate"),
    )
    op.create_index("ix_selection_candidate_repository", "selection_scenario_candidates", ["repository_id"])
    op.create_table(
        "selection_metric_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scenario_id", sa.Integer(), sa.ForeignKey("selection_scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.repository_id", ondelete="CASCADE"), nullable=False),
        sa.Column("metric_key", sa.String(100), nullable=False),
        sa.Column("value", sa.Float()),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("sample_count", sa.Integer()),
        sa.Column("window_start", sa.DateTime()),
        sa.Column("window_end_exclusive", sa.DateTime()),
        sa.Column("data_cutoff_at", sa.DateTime(), nullable=False),
        sa.Column("source_dataset_id", sa.String(100), nullable=False),
        sa.Column("coverage_status", sa.String(30), nullable=False),
        sa.Column("coverage_ratio", sa.Float()),
        sa.Column("methodology_version", sa.String(100), nullable=False),
        sa.Column("calculated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.UniqueConstraint("scenario_id", "repository_id", "metric_key", "window_start", "window_end_exclusive", "methodology_version", name="uq_selection_metric_snapshot"),
    )
    op.create_index("ix_selection_metric_scenario_repo", "selection_metric_snapshots", ["scenario_id", "repository_id"])
    op.create_table(
        "selection_capability_evidence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scenario_id", sa.Integer(), sa.ForeignKey("selection_scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.repository_id", ondelete="CASCADE"), nullable=False),
        sa.Column("capability_key", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("applicable_version", sa.String(100)),
        sa.Column("evidence_url", sa.Text(), nullable=False),
        sa.Column("source_checked_at", sa.DateTime(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.UniqueConstraint("scenario_id", "repository_id", "capability_key", name="uq_selection_capability_evidence"),
    )
    op.create_index("ix_selection_capability_scenario_repo", "selection_capability_evidence", ["scenario_id", "repository_id"])
    op.create_table(
        "selection_snapshot_releases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scenario_id", sa.Integer(), sa.ForeignKey("selection_scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scenario_version", sa.String(100), nullable=False),
        sa.Column("source_dataset_refs_json", sa.Text(), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(), nullable=False),
        sa.Column("window_policy_json", sa.Text(), nullable=False),
        sa.Column("quality_report_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("immutable_fingerprint", sa.String(64), nullable=False),
        sa.Column("published_at", sa.DateTime()),
        sa.UniqueConstraint("scenario_id", "scenario_version", name="uq_selection_snapshot_release"),
    )
    op.create_index("ix_selection_release_scenario_published", "selection_snapshot_releases", ["scenario_id", "published_at"])


def downgrade() -> None:
    op.drop_index("ix_selection_release_scenario_published", table_name="selection_snapshot_releases")
    op.drop_table("selection_snapshot_releases")
    op.drop_index("ix_selection_capability_scenario_repo", table_name="selection_capability_evidence")
    op.drop_table("selection_capability_evidence")
    op.drop_index("ix_selection_metric_scenario_repo", table_name="selection_metric_snapshots")
    op.drop_table("selection_metric_snapshots")
    op.drop_index("ix_selection_candidate_repository", table_name="selection_scenario_candidates")
    op.drop_table("selection_scenario_candidates")
    op.drop_table("selection_scenarios")
