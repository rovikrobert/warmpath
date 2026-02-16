"""add csv_upload detail columns (contacts_created, duplicates_skipped)

Revision ID: d4e7f1a23b56
Revises: c3f8a2b91d45
Create Date: 2026-02-16 22:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e7f1a23b56"
down_revision: Union[str, None] = "c3f8a2b91d45"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "csv_uploads",
        sa.Column("contacts_created", sa.Integer(), server_default="0", nullable=True),
    )
    op.add_column(
        "csv_uploads",
        sa.Column(
            "duplicates_skipped", sa.Integer(), server_default="0", nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("csv_uploads", "duplicates_skipped")
    op.drop_column("csv_uploads", "contacts_created")
