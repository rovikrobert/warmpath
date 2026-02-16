"""add missing columns: warm_scores.referral_likelihood, search_requests.results_data/error_message

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-02-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("warm_scores", sa.Column("referral_likelihood", sa.String(50)))
    op.add_column("search_requests", sa.Column("results_data", postgresql.JSONB()))
    op.add_column("search_requests", sa.Column("error_message", sa.Text()))


def downgrade() -> None:
    op.drop_column("search_requests", "error_message")
    op.drop_column("search_requests", "results_data")
    op.drop_column("warm_scores", "referral_likelihood")
