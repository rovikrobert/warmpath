"""add referral_codes and referral_conversions tables

Revision ID: 2e8f0c091d3a
Revises: d7514583a198
Create Date: 2026-02-18 10:33:22.095945
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '2e8f0c091d3a'
down_revision: Union[str, None] = 'd7514583a198'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('referral_codes',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('referral_type', sa.String(length=20), nullable=False),
    sa.Column('target_email', sa.String(length=255), nullable=True),
    sa.Column('target_company_id', sa.UUID(), nullable=True),
    sa.Column('max_uses', sa.Integer(), nullable=True),
    sa.Column('uses_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('credits_per_conversion', sa.Integer(), server_default='25', nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['target_company_id'], ['companies.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_index('idx_referral_codes_code', 'referral_codes', ['code'], unique=True)
    op.create_index('idx_referral_codes_owner', 'referral_codes', ['owner_id'], unique=False)
    op.create_index('idx_referral_codes_target_email', 'referral_codes', ['target_email'], unique=False)
    op.create_table('referral_conversions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('referral_code_id', sa.UUID(), nullable=False),
    sa.Column('referred_user_id', sa.UUID(), nullable=False),
    sa.Column('conversion_event', sa.String(length=30), nullable=False),
    sa.Column('credits_awarded', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['referral_code_id'], ['referral_codes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['referred_user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('referral_code_id', 'referred_user_id', 'conversion_event', name='uq_referral_conversion')
    )
    op.create_index('idx_referral_conversions_code', 'referral_conversions', ['referral_code_id'], unique=False)
    op.create_index('idx_referral_conversions_user', 'referral_conversions', ['referred_user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_referral_conversions_user', table_name='referral_conversions')
    op.drop_index('idx_referral_conversions_code', table_name='referral_conversions')
    op.drop_table('referral_conversions')
    op.drop_index('idx_referral_codes_target_email', table_name='referral_codes')
    op.drop_index('idx_referral_codes_owner', table_name='referral_codes')
    op.drop_index('idx_referral_codes_code', table_name='referral_codes')
    op.drop_table('referral_codes')
