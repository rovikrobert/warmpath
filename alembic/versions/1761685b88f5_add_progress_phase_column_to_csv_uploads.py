"""add progress_phase column to csv_uploads

Revision ID: 1761685b88f5
Revises: dfb5f82de914
Create Date: 2026-02-21 00:36:37.797541
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "1761685b88f5"
down_revision: Union[str, None] = "dfb5f82de914"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "csv_uploads", sa.Column("progress_phase", sa.String(length=50), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("csv_uploads", "progress_phase")
