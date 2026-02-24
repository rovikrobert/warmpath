"""expand relationship_type check constraint

Revision ID: 316f5a16aa57
Revises: e6ae7c7339ca
Create Date: 2026-02-24 21:31:47.510103
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "316f5a16aa57"
down_revision: Union[str, None] = "e6ae7c7339ca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Original set from f6a9b4d13e78
OLD_TYPES = (
    "former_colleague",
    "current_colleague",
    "manager",
    "alumni",
    "industry_peer",
    "friend",
    "mentor",
    "recruiter",
    "other",
)

# Expanded set — adds client, vendor, investor (matches app/schemas/contact.py)
NEW_TYPES = (
    "former_colleague",
    "current_colleague",
    "manager",
    "alumni",
    "industry_peer",
    "friend",
    "mentor",
    "recruiter",
    "client",
    "vendor",
    "investor",
    "other",
)


def upgrade() -> None:
    op.drop_constraint("ck_contacts_relationship_type", "contacts", type_="check")
    op.create_check_constraint(
        "ck_contacts_relationship_type",
        "contacts",
        sa.column("relationship_type").in_(NEW_TYPES)
        | sa.column("relationship_type").is_(None),
    )


def downgrade() -> None:
    op.drop_constraint("ck_contacts_relationship_type", "contacts", type_="check")
    op.create_check_constraint(
        "ck_contacts_relationship_type",
        "contacts",
        sa.column("relationship_type").in_(OLD_TYPES)
        | sa.column("relationship_type").is_(None),
    )
