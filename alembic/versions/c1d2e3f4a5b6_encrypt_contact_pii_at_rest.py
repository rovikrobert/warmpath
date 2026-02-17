"""encrypt contact PII at rest

Add blind index columns and widen VARCHAR PII columns to TEXT
so Fernet ciphertext (which is longer than plaintext) fits.

Revision ID: c1d2e3f4a5b6
Revises: a7b8c9d0e1f2
Create Date: 2026-02-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add blind index columns (deterministic HMAC-SHA256 hashes for exact-match lookups)
    op.add_column(
        "contacts",
        sa.Column("email_blind_index", sa.String(64), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("name_company_blind_index", sa.String(64), nullable=True),
    )
    op.create_index("ix_contacts_email_blind_index", "contacts", ["email_blind_index"])
    op.create_index(
        "ix_contacts_name_company_blind_index", "contacts", ["name_company_blind_index"]
    )

    # Widen PII columns from VARCHAR to TEXT so Fernet ciphertext fits
    # (notes and how_you_know are already Text)
    for col in [
        "first_name",
        "last_name",
        "full_name",
        "email",
        "linkedin_url",
        "current_title",
        "current_company",
        "location",
    ]:
        op.alter_column(
            "contacts",
            col,
            type_=sa.Text(),
            existing_type=sa.String(),
            existing_nullable=True if col != "full_name" else False,
        )


def downgrade() -> None:
    # Revert TEXT columns back to VARCHAR (will truncate any ciphertext!)
    varchar_sizes = {
        "first_name": 255,
        "last_name": 255,
        "full_name": 500,
        "email": 255,
        "linkedin_url": 500,
        "current_title": 500,
        "current_company": 500,
        "location": 255,
    }
    for col, size in varchar_sizes.items():
        op.alter_column(
            "contacts",
            col,
            type_=sa.String(size),
            existing_type=sa.Text(),
            existing_nullable=True if col != "full_name" else False,
        )

    op.drop_index("ix_contacts_name_company_blind_index", "contacts")
    op.drop_index("ix_contacts_email_blind_index", "contacts")
    op.drop_column("contacts", "name_company_blind_index")
    op.drop_column("contacts", "email_blind_index")
