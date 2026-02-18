"""add friends system tables and email external_id

Revision ID: a9e1f9c8bffa
Revises: 598766ca2ce4
Create Date: 2026-02-18 12:40:03.186186
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a9e1f9c8bffa"
down_revision: Union[str, None] = "598766ca2ce4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- user_blocks table --
    op.create_table(
        "user_blocks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("blocker_id", sa.UUID(), nullable=False),
        sa.Column("blocked_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("blocker_id != blocked_id", name="ck_no_self_block"),
        sa.ForeignKeyConstraint(["blocked_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["blocker_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_block_pair"),
    )
    op.create_index("idx_block_blocked", "user_blocks", ["blocked_id"])
    op.create_index("idx_block_blocker", "user_blocks", ["blocker_id"])

    # -- user_friendships table --
    op.create_table(
        "user_friendships",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("requester_id", sa.UUID(), nullable=False),
        sa.Column("addressee_id", sa.UUID(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="pending", nullable=False
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "requester_id != addressee_id", name="ck_no_self_friendship"
        ),
        sa.ForeignKeyConstraint(["addressee_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("requester_id", "addressee_id", name="uq_friendship_pair"),
    )
    op.create_index("idx_friendship_addressee", "user_friendships", ["addressee_id"])
    op.create_index("idx_friendship_requester", "user_friendships", ["requester_id"])
    op.create_index("idx_friendship_status", "user_friendships", ["status"])

    # -- new columns on users --
    op.add_column(
        "users",
        sa.Column(
            "discoverable_by_contacts",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "friend_list_visible", sa.Boolean(), server_default="false", nullable=False
        ),
    )

    # -- external_id on email_campaign_logs --
    op.add_column(
        "email_campaign_logs",
        sa.Column("external_id", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("email_campaign_logs", "external_id")
    op.drop_column("users", "friend_list_visible")
    op.drop_column("users", "discoverable_by_contacts")
    op.drop_index("idx_friendship_status", table_name="user_friendships")
    op.drop_index("idx_friendship_requester", table_name="user_friendships")
    op.drop_index("idx_friendship_addressee", table_name="user_friendships")
    op.drop_table("user_friendships")
    op.drop_index("idx_block_blocker", table_name="user_blocks")
    op.drop_index("idx_block_blocked", table_name="user_blocks")
    op.drop_table("user_blocks")
