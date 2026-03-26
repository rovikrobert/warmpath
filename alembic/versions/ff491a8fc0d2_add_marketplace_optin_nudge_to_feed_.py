"""add marketplace_optin_nudge to feed_items item_type check

Revision ID: ff491a8fc0d2
Revises: 945acd78778c
Create Date: 2026-03-26 00:34:03.228792
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ff491a8fc0d2"
down_revision: Union[str, None] = "945acd78778c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_TYPES = (
    "'job_alert', 'contact_update', 'enrichment_prompt', "
    "'marketplace_signal', 'outcome_check', 'platform_activity', "
    "'network_insight', 'follow_up_nudge', "
    "'intro_approval_nudge', 'manual_send_reminder', "
    "'csv_completion', 'agent_auto_repair'"
)

NEW_TYPES = (
    "'job_alert', 'contact_update', 'enrichment_prompt', "
    "'marketplace_signal', 'outcome_check', 'platform_activity', "
    "'network_insight', 'follow_up_nudge', "
    "'intro_approval_nudge', 'manual_send_reminder', "
    "'csv_completion', 'agent_auto_repair', "
    "'marketplace_optin_nudge'"
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
