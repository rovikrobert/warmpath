"""add coaching_sessions table

Revision ID: 8be588bf721c
Revises: cb07e4671c98
Create Date: 2026-02-18 22:30:22.981222
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8be588bf721c'
down_revision: Union[str, None] = 'cb07e4671c98'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('coaching_sessions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('session_number', sa.Integer(), nullable=False),
    sa.Column('coaching_stage', sa.String(length=50), nullable=False),
    sa.Column('topics_covered', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('message_count', sa.Integer(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_coaching_sessions_user_id'), 'coaching_sessions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_coaching_sessions_user_id'), table_name='coaching_sessions')
    op.drop_table('coaching_sessions')
