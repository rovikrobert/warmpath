"""add feed tables (feed_items, feed_item_interactions, contact_freshness_signals)

Revision ID: a1f2b3c4d5e6
Revises: 69910c73664d
Create Date: 2026-02-20 13:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "a1f2b3c4d5e6"
down_revision: Union[str, None] = "69910c73664d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- feed_items table --
    op.create_table(
        "feed_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("item_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("action_url", sa.String(500), nullable=True),
        sa.Column("action_label", sa.String(100), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column("dedup_key", sa.String(500), nullable=True),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acted_on_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("emailed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "item_type IN ("
            "'job_alert', 'contact_update', 'enrichment_prompt', "
            "'marketplace_signal', 'outcome_check', 'platform_activity', "
            "'network_insight', 'follow_up_nudge')",
            name="ck_feed_items_type",
        ),
        sa.CheckConstraint(
            "priority BETWEEN 1 AND 100",
            name="ck_feed_items_priority",
        ),
    )
    op.create_index("ix_feed_items_user_id", "feed_items", ["user_id"])
    op.create_index("ix_feed_items_item_type", "feed_items", ["item_type"])
    op.create_index(
        "idx_feed_items_user_unseen",
        "feed_items",
        ["user_id", "seen_at", "created_at"],
    )
    op.create_index(
        "idx_feed_items_dedup",
        "feed_items",
        ["user_id", "item_type", "dedup_key"],
        unique=True,
        postgresql_where=sa.text("dismissed_at IS NULL AND dedup_key IS NOT NULL"),
    )
    op.create_index("idx_feed_items_expires", "feed_items", ["expires_at"])

    # -- feed_item_interactions table --
    op.create_table(
        "feed_item_interactions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("feed_item_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("interaction_type", sa.String(20), nullable=False),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["feed_item_id"], ["feed_items.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "interaction_type IN ('view', 'click', 'dismiss', 'share', 'snooze')",
            name="ck_feed_item_interactions_type",
        ),
    )
    op.create_index(
        "ix_feed_item_interactions_feed_item_id",
        "feed_item_interactions",
        ["feed_item_id"],
    )
    op.create_index(
        "ix_feed_item_interactions_user_id",
        "feed_item_interactions",
        ["user_id"],
    )
    op.create_index(
        "idx_feed_interactions_item",
        "feed_item_interactions",
        ["feed_item_id", "created_at"],
    )
    op.create_index(
        "idx_feed_interactions_user_type",
        "feed_item_interactions",
        ["user_id", "interaction_type", "created_at"],
    )

    # -- contact_freshness_signals table --
    op.create_table(
        "contact_freshness_signals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("signal_type", sa.String(50), nullable=False),
        sa.Column("signal_value", JSONB(), nullable=False),
        sa.Column("name_company_hash", sa.String(64), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "source",
            sa.String(50),
            nullable=False,
            server_default="feed_prompt",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "signal_type IN ("
            "'still_at_company', 'relationship_type', 'last_interaction', "
            "'would_refer', 'contact_moved', 'role_changed')",
            name="ck_freshness_signal_type",
        ),
    )
    op.create_index(
        "ix_contact_freshness_signals_user_id",
        "contact_freshness_signals",
        ["user_id"],
    )
    op.create_index(
        "ix_contact_freshness_signals_contact_id",
        "contact_freshness_signals",
        ["contact_id"],
    )
    op.create_index(
        "ix_contact_freshness_signals_name_company_hash",
        "contact_freshness_signals",
        ["name_company_hash"],
    )
    op.create_index(
        "idx_freshness_signals_latest",
        "contact_freshness_signals",
        ["contact_id", "signal_type", "created_at"],
    )
    op.create_index(
        "idx_freshness_signals_cross_user",
        "contact_freshness_signals",
        ["name_company_hash", "signal_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("contact_freshness_signals")
    op.drop_table("feed_item_interactions")
    op.drop_table("feed_items")
