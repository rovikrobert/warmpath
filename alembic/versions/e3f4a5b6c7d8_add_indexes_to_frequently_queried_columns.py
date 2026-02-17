"""add indexes to frequently queried columns

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-02-17

Adds indexes to columns frequently used in WHERE clauses to improve query
performance. Identified by perf_monitor agent scan.
"""

from alembic import op

# revision identifiers
revision = "e3f4a5b6c7d8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_connector_profiles_user_id", "connector_profiles", ["user_id"])
    op.create_index(
        "ix_user_job_preferences_user_id", "user_job_preferences", ["user_id"]
    )
    op.create_index("ix_contacts_relationship_type", "contacts", ["relationship_type"])
    op.create_index("ix_contacts_source", "contacts", ["source"])
    op.create_index("ix_applications_status", "applications", ["status"])
    op.create_index("ix_match_results_match_type", "match_results", ["match_type"])
    op.create_index("ix_credit_transactions_type", "credit_transactions", ["type"])
    op.create_index("ix_contacts_csv_upload_id", "contacts", ["csv_upload_id"])


def downgrade() -> None:
    op.drop_index("ix_contacts_csv_upload_id", "contacts")
    op.drop_index("ix_credit_transactions_type", "credit_transactions")
    op.drop_index("ix_match_results_match_type", "match_results")
    op.drop_index("ix_applications_status", "applications")
    op.drop_index("ix_contacts_source", "contacts")
    op.drop_index("ix_contacts_relationship_type", "contacts")
    op.drop_index("ix_user_job_preferences_user_id", "user_job_preferences")
    op.drop_index("ix_connector_profiles_user_id", "connector_profiles")
