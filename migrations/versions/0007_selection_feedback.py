"""保存用户明确同意的本机选型反馈。"""
import sqlalchemy as sa
from alembic import op

revision = "0007_selection_feedback"
down_revision = "0006_dataset_import_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "selection_feedback",
        sa.Column("feedback_id", sa.String(length=36), primary_key=True),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("selection_feedback")
