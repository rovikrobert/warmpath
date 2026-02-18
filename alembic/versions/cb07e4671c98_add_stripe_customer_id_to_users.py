"""add stripe_customer_id to users

Revision ID: cb07e4671c98
Revises: c4d5e6f7a8b9
Create Date: 2026-02-18 21:40:17.734428
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "cb07e4671c98"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("stripe_customer_id", sa.String(length=255), nullable=True)
    )
    op.create_index(
        op.f("ix_users_stripe_customer_id"),
        "users",
        ["stripe_customer_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_users_stripe_customer_id"), table_name="users")
    op.drop_column("users", "stripe_customer_id")
