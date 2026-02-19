"""add missing indexes and timestamps to 10 tables

Revision ID: 5da346403a79
Revises: 621e94b7b6bd
Create Date: 2026-02-19 16:36:32.291859
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "5da346403a79"
down_revision: Union[str, None] = "621e94b7b6bd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_timestamp(table: str, column: str) -> None:
    """Add a timestamp column with server_default for existing rows, then drop the default."""
    op.add_column(
        table,
        sa.Column(
            column,
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )


def upgrade() -> None:
    # --- New indexes ---
    op.create_index(
        "idx_campaign_external_id", "email_campaign_logs", ["external_id"], unique=False
    )
    op.create_index(
        "idx_pricing_benchmarks_pricing_model",
        "pricing_benchmarks",
        ["pricing_model"],
        unique=False,
    )
    op.create_index(
        "idx_company_boards_is_active", "company_boards", ["is_active"], unique=False
    )

    # --- Add updated_at to 10 tables ---
    for table in [
        "contact_companies",
        "credit_transactions",
        "email_campaign_logs",
        "usage_logs",
        "user_blocks",
        "suppression_list",
        "consent_records",
        "data_requests",
        "archived_credit_transactions",
        "referral_conversions",
    ]:
        _add_timestamp(table, "updated_at")

    # --- Add created_at to 2 tables that were missing it ---
    _add_timestamp("email_campaign_logs", "created_at")
    _add_timestamp("archived_credit_transactions", "created_at")


def downgrade() -> None:
    # --- Drop created_at from 2 tables ---
    op.drop_column("archived_credit_transactions", "created_at")
    op.drop_column("email_campaign_logs", "created_at")

    # --- Drop updated_at from 10 tables ---
    for table in [
        "referral_conversions",
        "archived_credit_transactions",
        "data_requests",
        "consent_records",
        "suppression_list",
        "user_blocks",
        "usage_logs",
        "email_campaign_logs",
        "credit_transactions",
        "contact_companies",
    ]:
        op.drop_column(table, "updated_at")

    # --- Drop indexes ---
    op.drop_index("idx_company_boards_is_active", table_name="company_boards")
    op.drop_index(
        "idx_pricing_benchmarks_pricing_model", table_name="pricing_benchmarks"
    )
    op.drop_index("idx_campaign_external_id", table_name="email_campaign_logs")
