"""add onboarding_completed_at to users

Revision ID: a990e5aba873
Revises: f62b1e3852e9
Create Date: 2026-02-20 02:42:28.933646
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a990e5aba873'
down_revision: Union[str, None] = 'f62b1e3852e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('onboarding_completed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'onboarding_completed_at')
