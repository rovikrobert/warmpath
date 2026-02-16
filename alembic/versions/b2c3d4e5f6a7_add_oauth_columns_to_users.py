"""add oauth_provider, oauth_provider_id to users; make password_hash nullable

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=True)
    op.add_column("users", sa.Column("oauth_provider", sa.String(50), nullable=True))
    op.add_column(
        "users",
        sa.Column("oauth_provider_id", sa.String(255), nullable=True),
    )
    op.create_index("ix_users_oauth_provider_id", "users", ["oauth_provider_id"])
    op.create_unique_constraint(
        "uq_user_oauth_identity", "users", ["oauth_provider", "oauth_provider_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_user_oauth_identity", "users", type_="unique")
    op.drop_index("ix_users_oauth_provider_id", table_name="users")
    op.drop_column("users", "oauth_provider_id")
    op.drop_column("users", "oauth_provider")
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=False)
