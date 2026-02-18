"""drop user_type column from users

Revision ID: d5c351c415ce
Revises: 5ba2f473915f
Create Date: 2026-02-19 01:04:38.020468
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5c351c415ce'
down_revision: Union[str, None] = '5ba2f473915f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("users", "user_type")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "user_type",
            sa.String(20),
            nullable=False,
            server_default="job_seeker",
        ),
    )
