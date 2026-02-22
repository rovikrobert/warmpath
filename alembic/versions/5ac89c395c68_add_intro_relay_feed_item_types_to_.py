"""add intro relay feed item types to check constraint

Revision ID: 5ac89c395c68
Revises: 9f9095905da7
Create Date: 2026-02-22 12:11:06.774822
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5ac89c395c68"
down_revision: Union[str, None] = "9f9095905da7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_TYPES = (
    "'job_alert', 'contact_update', 'enrichment_prompt', "
    "'marketplace_signal', 'outcome_check', 'platform_activity', "
    "'network_insight', 'follow_up_nudge'"
)

NEW_TYPES = (
    "'job_alert', 'contact_update', 'enrichment_prompt', "
    "'marketplace_signal', 'outcome_check', 'platform_activity', "
    "'network_insight', 'follow_up_nudge', "
    "'intro_approval_nudge', 'manual_send_reminder'"
)


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
