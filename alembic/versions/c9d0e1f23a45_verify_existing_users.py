"""verify existing users — grandfather pre-verification accounts

Revision ID: c9d0e1f23a45
Revises: b8c9d0e12f34
Create Date: 2026-02-16 23:55:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d0e1f23a45"
down_revision: Union[str, None] = "b8c9d0e12f34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # All accounts created before S5 (email verification) should be
    # grandfathered in — they signed up when verification wasn't required.
    op.execute(
        sa.text("UPDATE users SET email_verified = true WHERE email_verified = false")
    )


def downgrade() -> None:
    # No-op: we can't know which users were "legitimately" verified vs grandfathered
    pass
