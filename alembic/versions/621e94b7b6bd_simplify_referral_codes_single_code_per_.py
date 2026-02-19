"""simplify referral codes single code per user

Revision ID: 621e94b7b6bd
Revises: 57e1a6493055
Create Date: 2026-02-19 14:53:58.849615
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

# revision identifiers, used by Alembic.
revision: str = "621e94b7b6bd"
down_revision: Union[str, None] = "57e1a6493055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make referral_type nullable (no longer used, kept for existing data)
    op.alter_column(
        "referral_codes",
        "referral_type",
        existing_type=sa.VARCHAR(length=20),
        nullable=True,
    )

    # Drop target_company_id FK — find the actual constraint name dynamically
    conn = op.get_bind()
    inspector = sa_inspect(conn)
    fks = inspector.get_foreign_keys("referral_codes")
    for fk in fks:
        if "target_company_id" in fk["constrained_columns"]:
            op.drop_constraint(fk["name"], "referral_codes", type_="foreignkey")
            break

    # Drop the column
    op.drop_column("referral_codes", "target_company_id")


def downgrade() -> None:
    op.add_column(
        "referral_codes",
        sa.Column("target_company_id", sa.UUID(), autoincrement=False, nullable=True),
    )
    op.create_foreign_key(
        "referral_codes_target_company_id_fkey",
        "referral_codes",
        "companies",
        ["target_company_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column(
        "referral_codes",
        "referral_type",
        existing_type=sa.VARCHAR(length=20),
        nullable=False,
    )
