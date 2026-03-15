"""add agent_auto_repair feed type

Revision ID: 945acd78778c
Revises: h5c6d7e8f9a0
Create Date: 2026-03-15 22:40:55.472134
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "945acd78778c"
down_revision: Union[str, None] = "h5c6d7e8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_TYPES = (
    "'job_alert', 'contact_update', 'enrichment_prompt', "
    "'marketplace_signal', 'outcome_check', 'platform_activity', "
    "'network_insight', 'follow_up_nudge', "
    "'intro_approval_nudge', 'manual_send_reminder', "
    "'csv_completion'"
)

NEW_TYPES = OLD_TYPES + ", 'agent_auto_repair'"


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
