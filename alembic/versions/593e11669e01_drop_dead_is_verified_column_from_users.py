"""drop dead is_verified column from users

Revision ID: 593e11669e01
Revises: 1d974af82601
Create Date: 2026-02-24 11:07:57.388542
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "593e11669e01"
down_revision: Union[str, None] = "1d974af82601"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("users", "is_verified")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
    )
