"""add user_type column to users

Revision ID: d0a1b2c3d4e5
Revises: c9d0e1f23a45
Create Date: 2026-02-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d0a1b2c3d4e5"
down_revision: Union[str, None] = "c9d0e1f23a45"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "user_type",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'job_seeker'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "user_type")
