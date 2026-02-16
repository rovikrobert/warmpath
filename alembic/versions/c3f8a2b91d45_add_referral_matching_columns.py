"""add referral matching columns

- search_requests: target_role, target_seniority
- match_results: cultural_context

Revision ID: c3f8a2b91d45
Revises: bc05a5432f12
Create Date: 2026-02-16 20:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c3f8a2b91d45"
down_revision: Union[str, None] = "bc05a5432f12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Search request: referral-specific fields
    op.add_column(
        "search_requests",
        sa.Column("target_role", sa.String(255), nullable=True),
    )
    op.add_column(
        "search_requests",
        sa.Column("target_seniority", sa.String(100), nullable=True),
    )

    # Match result: cultural context blob
    op.add_column(
        "match_results",
        sa.Column("cultural_context", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("match_results", "cultural_context")
    op.drop_column("search_requests", "target_seniority")
    op.drop_column("search_requests", "target_role")
