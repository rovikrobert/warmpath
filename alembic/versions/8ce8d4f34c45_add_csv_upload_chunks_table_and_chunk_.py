"""add csv_upload_chunks table and chunk tracking columns

Revision ID: 8ce8d4f34c45
Revises: 1761685b88f5
Create Date: 2026-02-21 19:09:40.701118
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8ce8d4f34c45"
down_revision: Union[str, None] = "1761685b88f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "csv_upload_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("upload_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="pending", nullable=False
        ),
        sa.Column("provider_used", sa.String(length=20), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("contacts_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["upload_id"], ["csv_uploads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_csv_upload_chunks_upload_id"),
        "csv_upload_chunks",
        ["upload_id"],
        unique=False,
    )
    op.add_column("csv_uploads", sa.Column("total_chunks", sa.Integer(), nullable=True))
    op.add_column(
        "csv_uploads",
        sa.Column("chunks_cleaned", sa.Integer(), server_default="0", nullable=True),
    )
    op.add_column(
        "csv_uploads",
        sa.Column("chunks_imported", sa.Integer(), server_default="0", nullable=True),
    )


def downgrade() -> None:
    op.drop_column("csv_uploads", "chunks_imported")
    op.drop_column("csv_uploads", "chunks_cleaned")
    op.drop_column("csv_uploads", "total_chunks")
    op.drop_index(
        op.f("ix_csv_upload_chunks_upload_id"), table_name="csv_upload_chunks"
    )
    op.drop_table("csv_upload_chunks")
