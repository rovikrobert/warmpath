"""add data_requests user_id and usage_logs created_at indexes

Revision ID: d7514583a198
Revises: 8d95f6550f6f
Create Date: 2026-02-18 09:53:49.891610
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7514583a198"
down_revision: Union[str, None] = "8d95f6550f6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_data_requests_user_id"), "data_requests", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_usage_logs_created_at"), "usage_logs", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_usage_logs_created_at"), table_name="usage_logs")
    op.drop_index(op.f("ix_data_requests_user_id"), table_name="data_requests")
