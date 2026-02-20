"""add would_refer column to contacts

Revision ID: 650d855b89ea
Revises: a1f2b3c4d5e6
Create Date: 2026-02-20 21:30:24.564166
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "650d855b89ea"
down_revision: Union[str, None] = "a1f2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "contacts", sa.Column("would_refer", sa.String(length=20), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("contacts", "would_refer")
