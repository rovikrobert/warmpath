"""add csv_completion to feed_items type constraint

Revision ID: e7ced6848306
Revises: e6fb92c8fca7
Create Date: 2026-02-28 16:36:36.079950
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e7ced6848306"
down_revision: Union[str, None] = "e6fb92c8fca7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_TYPES = (
    "'job_alert', 'contact_update', 'enrichment_prompt', "
    "'marketplace_signal', 'outcome_check', 'platform_activity', "
    "'network_insight', 'follow_up_nudge', "
    "'intro_approval_nudge', 'manual_send_reminder'"
)
NEW_TYPES = OLD_TYPES + ", 'csv_completion'"


def upgrade() -> None:
    op.drop_constraint("ck_feed_items_type", "feed_items", type_="check")
    op.create_check_constraint(
        "ck_feed_items_type",
        "feed_items",
        f"item_type IN ({NEW_TYPES})",
    )


def downgrade() -> None:
    op.drop_constraint("ck_feed_items_type", "feed_items", type_="check")
    op.create_check_constraint(
        "ck_feed_items_type",
        "feed_items",
        f"item_type IN ({OLD_TYPES})",
    )
