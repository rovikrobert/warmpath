"""add clerk_user_id to users

Revision ID: 33c30032607d
Revises: 5da346403a79
Create Date: 2026-02-19 22:12:28.818033
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '33c30032607d'
down_revision: Union[str, None] = '5da346403a79'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('clerk_user_id', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_users_clerk_user_id'), 'users', ['clerk_user_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_users_clerk_user_id'), table_name='users')
    op.drop_column('users', 'clerk_user_id')
