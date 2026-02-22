"""add warm_sco[RESEND_KEY_REDACTED] to contacts

Revision ID: 4abd204836a1
Revises: 301496dee414
Create Date: 2026-02-22 19:58:44.791551
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4abd204836a1"
down_revision: Union[str, None] = "301496dee414"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "contacts", sa.Column("warm_sco[RESEND_KEY_REDACTED]", sa.Float(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("contacts", "warm_sco[RESEND_KEY_REDACTED]")
