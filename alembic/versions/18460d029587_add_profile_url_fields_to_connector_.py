"""add profile url fields to connector_profiles

Revision ID: 18460d029587
Revises: 5ac89c395c68
Create Date: 2026-02-22 14:58:30.347204
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "18460d029587"
down_revision: Union[str, None] = "5ac89c395c68"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "connector_profiles",
        sa.Column("github_url", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "connector_profiles",
        sa.Column("portfolio_url", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "connector_profiles",
        sa.Column("personal_site_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("connector_profiles", "personal_site_url")
    op.drop_column("connector_profiles", "portfolio_url")
    op.drop_column("connector_profiles", "github_url")
