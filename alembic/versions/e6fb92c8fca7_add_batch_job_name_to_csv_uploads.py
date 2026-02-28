"""add batch_job_name to csv_uploads

Revision ID: e6fb92c8fca7
Revises: 316f5a16aa57
Create Date: 2026-02-28 16:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6fb92c8fca7"
down_revision: Union[str, None] = "316f5a16aa57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "csv_uploads",
        sa.Column("batch_job_name", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("csv_uploads", "batch_job_name")
