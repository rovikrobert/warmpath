"""add updated_at to 6 models, indexes on connector_reputation and intro_facilitations

Revision ID: f3a4b5c6d7e8
Revises: e7ced6848306
Create Date: 2026-03-02

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f3a4b5c6d7e8"
down_revision = "e7ced6848306"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add updated_at to 6 tables missing it (convention requires all tables
    # except audit_logs to have created_at + updated_at)
    for table in [
        "csv_upload_chunks",
        "feed_item_interactions",
        "contact_freshness_signals",
        "freshness_propagation_log",
        "recommendation_demand_signals",
        "user_milestones",
    ]:
        op.add_column(
            table,
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=True,
            ),
        )

    # Add index on connector_reputation.user_id (queried in WHERE clauses)
    op.create_index(
        "ix_connector_reputation_user_id",
        "connector_reputation",
        ["user_id"],
    )

    # Add index on intro_facilitations.relay_message_id (queried in webhook handler)
    op.create_index(
        "ix_intro_facilitations_relay_message_id",
        "intro_facilitations",
        ["relay_message_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_intro_facilitations_relay_message_id", table_name="intro_facilitations"
    )
    op.drop_index("ix_connector_reputation_user_id", table_name="connector_reputation")

    for table in [
        "csv_upload_chunks",
        "feed_item_interactions",
        "contact_freshness_signals",
        "freshness_propagation_log",
        "recommendation_demand_signals",
        "user_milestones",
    ]:
        op.drop_column(table, "updated_at")
