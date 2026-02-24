"""add matching signal fields to user_job_preferences

Revision ID: 5cb0628b05f9
Revises: e3f4a5b6c7d8
Create Date: 2026-02-24

Adds career_level, years_experience, key_skills, and target_companies
to user_job_preferences — strengthens referral matching and signal building.
"""

from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "5cb0628b05f9"
down_revision: Union[str, None] = "e3f4a5b6c7d8"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "user_job_preferences",
        sa.Column("career_level", sa.String(50), nullable=True),
    )
    op.add_column(
        "user_job_preferences",
        sa.Column("years_experience", sa.Integer(), nullable=True),
    )
    op.add_column(
        "user_job_preferences",
        sa.Column(
            "key_skills",
            postgresql.JSONB(),
            server_default=sa.text("'[]'"),
            nullable=True,
        ),
    )
    op.add_column(
        "user_job_preferences",
        sa.Column(
            "target_companies",
            postgresql.JSONB(),
            server_default=sa.text("'[]'"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("user_job_preferences", "target_companies")
    op.drop_column("user_job_preferences", "key_skills")
    op.drop_column("user_job_preferences", "years_experience")
    op.drop_column("user_job_preferences", "career_level")
