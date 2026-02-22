"""add intro relay delivery columns and contact phone

Revision ID: 9f9095905da7
Revises: 8ce8d4f34c45
Create Date: 2026-02-22 10:19:26.466520
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "9f9095905da7"
down_revision: Union[str, None] = "8ce8d4f34c45"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Intro relay delivery tracking columns
    op.add_column(
        "intro_facilitations",
        sa.Column(
            "delivery_method",
            sa.String(length=20),
            nullable=True,
            comment="email_relay | linkedin_manual | other_manual",
        ),
    )
    op.add_column(
        "intro_facilitations",
        sa.Column(
            "delivery_status",
            sa.String(length=20),
            nullable=True,
            comment="pending | sent | delivered | bounced | opened | failed",
        ),
    )
    op.add_column(
        "intro_facilitations",
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "intro_facilitations",
        sa.Column(
            "relay_message_id",
            sa.String(length=255),
            nullable=True,
            comment="Resend email ID for tracking",
        ),
    )
    op.add_column(
        "intro_facilitations",
        sa.Column(
            "credits_awarded_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Prevents double credit award",
        ),
    )

    # Contact phone column (EncryptedString stores as TEXT in DB)
    op.add_column(
        "contacts",
        sa.Column(
            "phone",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("intro_facilitations", "credits_awarded_at")
    op.drop_column("intro_facilitations", "relay_message_id")
    op.drop_column("intro_facilitations", "delivered_at")
    op.drop_column("intro_facilitations", "delivery_status")
    op.drop_column("intro_facilitations", "delivery_method")
    op.drop_column("contacts", "phone")
