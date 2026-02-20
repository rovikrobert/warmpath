"""add session_id and event_source to usage_logs

Revision ID: 7e0659554ab2
Revises: 650d855b89ea
Create Date: 2026-02-20 21:37:07.506610
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "7e0659554ab2"
down_revision: Union[str, None] = "650d855b89ea"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Fix: usage_logs missing columns causing coach briefing crash
    op.add_column("usage_logs", sa.Column("session_id", sa.UUID(), nullable=True))
    op.add_column(
        "usage_logs", sa.Column("event_source", sa.String(length=50), nullable=True)
    )

    # Application outcome attribution columns
    op.add_column(
        "applications", sa.Column("source_type", sa.String(length=50), nullable=True)
    )
    op.add_column(
        "applications", sa.Column("source_listing_id", sa.UUID(), nullable=True)
    )
    op.add_column(
        "applications", sa.Column("source_intro_id", sa.UUID(), nullable=True)
    )
    op.add_column(
        "applications", sa.Column("outcome", sa.String(length=50), nullable=True)
    )
    op.add_column(
        "applications",
        sa.Column("outcome_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_applications_source_type"),
        "applications",
        ["source_type"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_applications_source_listing",
        "applications",
        "marketplace_listings",
        ["source_listing_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_applications_source_intro",
        "applications",
        "intro_facilitations",
        ["source_intro_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_applications_source_intro", "applications", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_applications_source_listing", "applications", type_="foreignkey"
    )
    op.drop_index(op.f("ix_applications_source_type"), table_name="applications")
    op.drop_column("applications", "outcome_at")
    op.drop_column("applications", "outcome")
    op.drop_column("applications", "source_intro_id")
    op.drop_column("applications", "source_listing_id")
    op.drop_column("applications", "source_type")
    op.drop_column("usage_logs", "event_source")
    op.drop_column("usage_logs", "session_id")
