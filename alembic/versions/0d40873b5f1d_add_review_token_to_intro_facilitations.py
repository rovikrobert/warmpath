"""add review_token to intro_facilitations

Revision ID: 0d40873b5f1d
Revises: 5ac89c395c68
Create Date: 2026-02-22 14:53:41.813606
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0d40873b5f1d"
down_revision: Union[str, None] = "5ac89c395c68"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "intro_facilitations",
        sa.Column("review_token", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "intro_facilitations",
        sa.Column("review_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_intro_facilitations_review_token"),
        "intro_facilitations",
        ["review_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_intro_facilitations_review_token"), table_name="intro_facilitations"
    )
    op.drop_column("intro_facilitations", "review_token_expires_at")
    op.drop_column("intro_facilitations", "review_token")
