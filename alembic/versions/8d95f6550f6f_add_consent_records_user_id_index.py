"""add consent_records user_id index

Revision ID: 8d95f6550f6f
Revises: b32dd2c767c0
Create Date: 2026-02-18 02:51:26.653629
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8d95f6550f6f'
down_revision: Union[str, None] = 'b32dd2c767c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(op.f('ix_consent_records_user_id'), 'consent_records', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_consent_records_user_id'), table_name='consent_records')
