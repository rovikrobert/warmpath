"""add user_feedback table and intro_messages updated_at

Revision ID: b32dd2c767c0
Revises: e3f4a5b6c7d8
Create Date: 2026-02-18 02:43:42.703380
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b32dd2c767c0'
down_revision: Union[str, None] = 'e3f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New table: user_feedback
    op.create_table('user_feedback',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('feature', sa.String(length=100), nullable=False),
    sa.Column('rating', sa.Integer(), nullable=False),
    sa.Column('resource_id', sa.UUID(), nullable=True),
    sa.Column('comment', sa.String(length=1000), nullable=True),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_feedback_feature'), 'user_feedback', ['feature'], unique=False)
    op.create_index(op.f('ix_user_feedback_user_id'), 'user_feedback', ['user_id'], unique=False)

    # New column: intro_messages.updated_at
    op.add_column('intro_messages', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('intro_messages', 'updated_at')
    op.drop_index(op.f('ix_user_feedback_user_id'), table_name='user_feedback')
    op.drop_index(op.f('ix_user_feedback_feature'), table_name='user_feedback')
    op.drop_table('user_feedback')
