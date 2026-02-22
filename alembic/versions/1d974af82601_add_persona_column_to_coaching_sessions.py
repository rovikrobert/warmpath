"""add persona column to coaching_sessions

Revision ID: 1d974af82601
Revises: 4abd204836a1
Create Date: 2026-02-22 20:10:47.115528
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1d974af82601"
down_revision: Union[str, None] = "4abd204836a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "coaching_sessions",
        sa.Column(
            "persona", sa.String(length=20), nullable=False, server_default="keevs"
        ),
    )


def downgrade() -> None:
    op.drop_column("coaching_sessions", "persona")
