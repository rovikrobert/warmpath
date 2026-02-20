"""add user_milestones table

Revision ID: dfb5f82de914
Revises: 6fa56a2c77cc
Create Date: 2026-02-20 22:04:24.322024
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "dfb5f82de914"
down_revision: Union[str, None] = "6fa56a2c77cc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_milestones",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("milestone_type", sa.String(length=50), nullable=False),
        sa.Column("milestone_value", sa.Integer(), nullable=False),
        sa.Column("credits_awarded", sa.Integer(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "milestone_type",
            "milestone_value",
            name="uq_user_milestones_user_type_value",
        ),
    )
    op.create_index(
        op.f("ix_user_milestones_user_id"), "user_milestones", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_milestones_user_id"), table_name="user_milestones")
    op.drop_table("user_milestones")
