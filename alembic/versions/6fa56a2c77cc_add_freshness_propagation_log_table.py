"""add freshness_propagation_log table

Revision ID: 6fa56a2c77cc
Revises: 7e0659554ab2
Create Date: 2026-02-20 22:04:00.240840
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "6fa56a2c77cc"
down_revision: Union[str, None] = "7e0659554ab2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "freshness_propagation_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name_company_hash", sa.String(length=64), nullable=False),
        sa.Column("signal_type", sa.String(length=50), nullable=False),
        sa.Column(
            "consensus_value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("contacts_updated", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_propagation_log_hash_type",
        "freshness_propagation_log",
        ["name_company_hash", "signal_type", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_freshness_propagation_log_name_company_hash"),
        "freshness_propagation_log",
        ["name_company_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_freshness_propagation_log_name_company_hash"),
        table_name="freshness_propagation_log",
    )
    op.drop_index(
        "idx_propagation_log_hash_type",
        table_name="freshness_propagation_log",
    )
    op.drop_table("freshness_propagation_log")
