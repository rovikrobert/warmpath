"""drop old auth columns from users

Revision ID: f62b1e3852e9
Revises: 33c30032607d
Create Date: 2026-02-19 23:56:37.253264
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f62b1e3852e9'
down_revision: Union[str, None] = '33c30032607d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old auth columns from users table
    op.drop_index('ix_users_oauth_provider_id', table_name='users', if_exists=True)
    op.drop_constraint('uq_user_oauth_identity', 'users', type_='unique')
    op.drop_column('users', 'oauth_provider_id')
    op.drop_column('users', 'oauth_provider')
    op.drop_column('users', 'password_hash')
    op.drop_column('users', 'token_version')
    op.drop_column('users', 'failed_login_attempts')
    op.drop_column('users', 'locked_until')
    op.drop_column('users', 'email_verification_token')
    op.drop_column('users', 'email_verification_sent_at')
    op.drop_column('users', 'password_reset_token')
    op.drop_column('users', 'password_reset_sent_at')


def downgrade() -> None:
    # Re-add old auth columns
    op.add_column('users', sa.Column('password_reset_sent_at', postgresql.TIMESTAMP(timezone=True), nullable=True))
    op.add_column('users', sa.Column('password_reset_token', sa.VARCHAR(length=255), nullable=True))
    op.add_column('users', sa.Column('email_verification_sent_at', postgresql.TIMESTAMP(timezone=True), nullable=True))
    op.add_column('users', sa.Column('email_verification_token', sa.VARCHAR(length=255), nullable=True))
    op.add_column('users', sa.Column('locked_until', postgresql.TIMESTAMP(timezone=True), nullable=True))
    op.add_column('users', sa.Column('failed_login_attempts', sa.INTEGER(), server_default=sa.text('0'), nullable=False))
    op.add_column('users', sa.Column('token_version', sa.INTEGER(), server_default=sa.text('0'), nullable=False))
    op.add_column('users', sa.Column('password_hash', sa.VARCHAR(length=255), nullable=True))
    op.add_column('users', sa.Column('oauth_provider', sa.VARCHAR(length=50), nullable=True))
    op.add_column('users', sa.Column('oauth_provider_id', sa.VARCHAR(length=255), nullable=True))
    op.create_unique_constraint('uq_user_oauth_identity', 'users', ['oauth_provider', 'oauth_provider_id'])
    op.create_index('ix_users_oauth_provider_id', 'users', ['oauth_provider_id'])
