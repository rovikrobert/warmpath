"""add intent column to users

Revision ID: 5ba2f473915f
Revises: 8be588bf721c
Create Date: 2026-02-18 23:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5ba2f473915f'
down_revision: Union[str, None] = '8be588bf721c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('intent', sa.String(length=20), nullable=True))
    op.execute("""
        UPDATE users SET intent = CASE
            WHEN user_type = 'job_seeker' THEN 'find_referrals'
            WHEN user_type = 'network_holder' THEN 'share_network'
            WHEN user_type = 'both' THEN 'explore'
            ELSE NULL
        END
    """)


def downgrade() -> None:
    op.drop_column('users', 'intent')
