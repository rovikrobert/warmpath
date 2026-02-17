"""add privacy compliance tables and user columns

Adds:
- consent_records table (Gap 6: consent tracking)
- data_requests table (Gap 9: DSAR tracking)
- archived_credit_transactions table (Gap 1: data retention)
- processing_restricted column on users (Gap 4: right to restrict)
- marketing_opt_out column on users (Gap 5: right to object)

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-02-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2e3f4a5b6c7"
down_revision: str = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # User model: privacy columns
    op.add_column(
        "users",
        sa.Column(
            "processing_restricted",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "marketing_opt_out",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )

    # Consent records table
    op.create_table(
        "consent_records",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("activity", sa.String(50), nullable=False),
        sa.Column("consented", sa.String(10), nullable=False, server_default="granted"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_consent_user_activity", "consent_records", ["user_id", "activity"]
    )

    # Data requests table (DSAR tracking)
    op.create_table(
        "data_requests",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("request_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("requester_email", sa.String(255), nullable=False),
        sa.Column("details", sa.dialects.postgresql.JSONB()),
        sa.Column("response_notes", sa.Text()),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_data_requests_status", "data_requests", ["status"])

    # Archived credit transactions table
    op.create_table(
        "archived_credit_transactions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "original_user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "original_transaction_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(100), nullable=False),
        sa.Column("original_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("archived_credit_transactions")
    op.drop_index("idx_data_requests_status", table_name="data_requests")
    op.drop_table("data_requests")
    op.drop_index("idx_consent_user_activity", table_name="consent_records")
    op.drop_table("consent_records")
    op.drop_column("users", "marketing_opt_out")
    op.drop_column("users", "processing_restricted")
