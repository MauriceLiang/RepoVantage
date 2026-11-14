"""保存可审计的 52 周维护活动及独立覆盖。"""
import sqlalchemy as sa
from alembic import op

revision = '0008_maintenance'
down_revision = '0007_selection_feedback'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('repository_maintenance_runs',
        sa.Column('run_id', sa.String(36), primary_key=True),
        sa.Column('repository_id', sa.Integer(), sa.ForeignKey('repositories.repository_id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('history_start', sa.DateTime(), nullable=False),
        sa.Column('history_end', sa.DateTime(), nullable=False),
        sa.Column('captured_at', sa.DateTime(), nullable=False),
        sa.Column('head_sha', sa.String(40), nullable=True),
        sa.Column('source_sha256', sa.String(64), nullable=True),
        sa.Column('archive_path', sa.Text(), nullable=True),
        sa.Column('details_json', sa.Text(), nullable=False))
    op.create_index('ix_maintenance_repo_captured', 'repository_maintenance_runs', ['repository_id', 'captured_at'])
    op.create_table('repository_maintenance_weeks',
        sa.Column('run_id', sa.String(36), sa.ForeignKey('repository_maintenance_runs.run_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('week_start', sa.DateTime(), primary_key=True),
        sa.Column('week_end', sa.DateTime(), nullable=False),
        sa.Column('commits', sa.Integer(), nullable=False),
        sa.Column('prs_created', sa.Integer(), nullable=False),
        sa.Column('commit_coverage', sa.String(30), nullable=False),
        sa.Column('pr_created_coverage', sa.String(30), nullable=False))


def downgrade() -> None:
    op.drop_table('repository_maintenance_weeks')
    op.drop_index('ix_maintenance_repo_captured', table_name='repository_maintenance_runs')
    op.drop_table('repository_maintenance_runs')
