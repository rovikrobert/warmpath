"""add intro_facilitations expires_at + indexes

Revision ID: bf86d10d81a7
Revises: 61851ac18c4f
Create Date: 2026-02-18 11:57:31.578168
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "bf86d10d81a7"
down_revision: Union[str, None] = "61851ac18c4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "intro_facilitations",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_intro_expires", "intro_facilitations", ["expires_at"], unique=False
    )
    op.create_index("idx_intro_status", "intro_facilitations", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_intro_status", table_name="intro_facilitations")
    op.drop_index("idx_intro_expires", table_name="intro_facilitations")
    op.drop_column("intro_facilitations", "expires_at")
