"""add recommendation_demand_signals table

Revision ID: 69910c73664d
Revises: a990e5aba873
Create Date: 2026-02-20 08:42:22.461340
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "69910c73664d"
down_revision: Union[str, None] = "a990e5aba873"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recommendation_demand_signals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("target_role", sa.String(length=255), nullable=False),
        sa.Column("target_location", sa.String(length=255), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_demand_signals_company",
        "recommendation_demand_signals",
        ["company_name"],
        unique=False,
    )
    op.create_index(
        "ix_demand_signals_role_company",
        "recommendation_demand_signals",
        ["target_role", "company_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_demand_signals_role_company",
        table_name="recommendation_demand_signals",
    )
    op.drop_index(
        "ix_demand_signals_company",
        table_name="recommendation_demand_signals",
    )
    op.drop_table("recommendation_demand_signals")
