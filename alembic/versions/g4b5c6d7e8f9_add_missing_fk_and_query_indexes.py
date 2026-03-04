"""add missing indexes for FK and frequently queried columns

Revision ID: g4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-03-04

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "g4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # FK columns missing indexes (PostgreSQL does not auto-index FKs)
    op.create_index("ix_user_blocks_blocker_id", "user_blocks", ["blocker_id"])
    op.create_index("ix_referral_codes_owner_id", "referral_codes", ["owner_id"])
    op.create_index(
        "ix_marketplace_listings_network_holder_id",
        "marketplace_listings",
        ["network_holder_id"],
    )

    # Frequently queried columns without indexes
    op.create_index("ix_company_boards_region", "company_boards", ["region"])
    op.create_index("ix_company_boards_is_active", "company_boards", ["is_active"])

    # Standalone created_at indexes for time-range queries in feed_ranker
    op.create_index("idx_feed_items_created_at", "feed_items", ["created_at"])
    op.create_index(
        "idx_feed_interactions_created_at",
        "feed_item_interactions",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_feed_interactions_created_at", "feed_item_interactions")
    op.drop_index("idx_feed_items_created_at", "feed_items")
    op.drop_index("ix_company_boards_is_active", "company_boards")
    op.drop_index("ix_company_boards_region", "company_boards")
    op.drop_index("ix_marketplace_listings_network_holder_id", "marketplace_listings")
    op.drop_index("ix_referral_codes_owner_id", "referral_codes")
    op.drop_index("ix_user_blocks_blocker_id", "user_blocks")
