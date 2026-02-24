"""merge migration heads

Revision ID: e6ae7c7339ca
Revises: 593e11669e01, 5cb0628b05f9
Create Date: 2026-02-24 20:50:34.141962
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "e6ae7c7339ca"
down_revision: Union[str, None] = ("593e11669e01", "5cb0628b05f9")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
