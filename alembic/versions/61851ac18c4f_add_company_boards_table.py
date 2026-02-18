"""add company_boards table

Revision ID: 61851ac18c4f
Revises: 2e8f0c091d3a
Create Date: 2026-02-18 11:04:13.924114
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '61851ac18c4f'
down_revision: Union[str, None] = '2e8f0c091d3a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('company_boards',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('company_key', sa.String(length=255), nullable=False, comment='Normalized lowercase key'),
    sa.Column('display_name', sa.String(length=500), nullable=False, comment='Human-readable company name'),
    sa.Column('board_source', sa.String(length=50), nullable=False, comment='greenhouse, lever, ashby, or career_page'),
    sa.Column('board_slug', sa.String(length=255), nullable=True, comment='ATS board slug (null for career_page source)'),
    sa.Column('career_page_url', sa.String(length=1000), nullable=True, comment='Fallback career page URL'),
    sa.Column('region', sa.String(length=100), nullable=True, comment='Geographic region grouping'),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True, comment='Last successful ATS probe timestamp'),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('company_key')
    )
    op.create_index('idx_company_boards_key', 'company_boards', ['company_key'], unique=True)
    op.create_index('idx_company_boards_region', 'company_boards', ['region'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_company_boards_region', table_name='company_boards')
    op.drop_index('idx_company_boards_key', table_name='company_boards')
    op.drop_table('company_boards')
