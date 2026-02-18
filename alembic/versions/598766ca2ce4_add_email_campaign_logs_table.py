"""add email_campaign_logs table

Revision ID: 598766ca2ce4
Revises: bf86d10d81a7
Create Date: 2026-02-18 12:09:39.269336
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "598766ca2ce4"
down_revision: Union[str, None] = "bf86d10d81a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_campaign_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("email_type", sa.String(length=50), nullable=False),
        sa.Column("sent_date", sa.String(length=10), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "email_type", "sent_date", name="uq_campaign_user_type_date"
        ),
    )
    op.create_index(
        "idx_campaign_type_date",
        "email_campaign_logs",
        ["email_type", "sent_date"],
        unique=False,
    )
    op.create_index(
        "idx_campaign_user", "email_campaign_logs", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("idx_campaign_user", table_name="email_campaign_logs")
    op.drop_index("idx_campaign_type_date", table_name="email_campaign_logs")
    op.drop_table("email_campaign_logs")
