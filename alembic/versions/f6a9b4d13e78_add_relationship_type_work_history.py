"""add relationship_type, source, work_history columns

Revision ID: f6a9b4d13e78
Revises: e5f8a3c02d67
Create Date: 2026-02-16 23:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a9b4d13e78"
down_revision: Union[str, None] = "e5f8a3c02d67"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VALID_RELATIONSHIP_TYPES = (
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


def upgrade() -> None:
    # -- contacts table --
    op.add_column(
        "contacts",
        sa.Column("relationship_type", sa.String(50), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column(
            "source", sa.String(50), nullable=False, server_default="linkedin_csv"
        ),
    )
    op.add_column(
        "contacts",
        sa.Column("how_you_know", sa.Text(), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("last_interaction_date", sa.Date(), nullable=True),
    )

    # CHECK constraint for relationship_type
    op.create_check_constraint(
        "ck_contacts_relationship_type",
        "contacts",
        sa.column("relationship_type").in_(VALID_RELATIONSHIP_TYPES)
        | sa.column("relationship_type").is_(None),
    )

    # -- connector_profiles table --
    op.add_column(
        "connector_profiles",
        sa.Column(
            "work_history",
            sa.JSON(),
            nullable=True,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_constraint("ck_contacts_relationship_type", "contacts", type_="check")
    op.drop_column("contacts", "last_interaction_date")
    op.drop_column("contacts", "how_you_know")
    op.drop_column("contacts", "source")
    op.drop_column("contacts", "relationship_type")
    op.drop_column("connector_profiles", "work_history")
