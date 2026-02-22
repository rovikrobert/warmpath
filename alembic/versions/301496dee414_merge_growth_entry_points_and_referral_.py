"""merge growth-entry-points and referral-signal migrations

Revision ID: 301496dee414
Revises: 0d40873b5f1d, 18460d029587
Create Date: 2026-02-22 15:43:15.784045
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '301496dee414'
down_revision: Union[str, None] = ('0d40873b5f1d', '18460d029587')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
