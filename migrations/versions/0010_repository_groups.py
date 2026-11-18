"""Add groups for repositories in the personal library."""
import sqlalchemy as sa
from alembic import op

revision = "0010_repository_groups"
down_revision = "0009_selection_scenarios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repository_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
    )
    op.create_table(
        "repository_group_members",
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("repository_groups.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("repository_id", sa.Integer(), primary_key=True),
        sa.Column("dataset_id", sa.String(100), nullable=False),
        sa.CheckConstraint("dataset_id = 'library-default'", name="ck_repository_group_library"),
        sa.ForeignKeyConstraint(
            ["dataset_id", "repository_id"],
            ["dataset_repositories.dataset_id", "dataset_repositories.repository_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_repository_group_member_library", "repository_group_members", ["dataset_id", "repository_id"])


def downgrade() -> None:
    op.drop_table("repository_group_members")
    op.drop_table("repository_groups")
