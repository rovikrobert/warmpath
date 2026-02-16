"""add intro referral sequence columns

Revision ID: e5f8a3c02d67
Revises: d4e7f1a23b56
Create Date: 2026-02-16 23:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f8a3c02d67"
down_revision: Union[str, None] = "d4e7f1a23b56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IntroMessage: multi-step sequence columns
    op.add_column(
        "intro_messages", sa.Column("sequence_step", sa.Integer(), nullable=True)
    )
    op.add_column(
        "intro_messages", sa.Column("step_label", sa.String(100), nullable=True)
    )
    op.add_column(
        "intro_messages",
        sa.Column("send_after_days", sa.Integer(), server_default="0", nullable=True),
    )
    op.add_column(
        "intro_messages", sa.Column("coaching_notes", sa.Text(), nullable=True)
    )

    # IntroRequest: link to job opening
    op.add_column(
        "intro_requests",
        sa.Column(
            "job_opening_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job_openings.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("intro_requests", "job_opening_id")
    op.drop_column("intro_messages", "coaching_notes")
    op.drop_column("intro_messages", "send_after_days")
    op.drop_column("intro_messages", "step_label")
    op.drop_column("intro_messages", "sequence_step")
