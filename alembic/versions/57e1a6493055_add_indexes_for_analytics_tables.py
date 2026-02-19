"""add indexes for analytics tables

Revision ID: 57e1a6493055
Revises: d5c351c415ce
Create Date: 2026-02-19 12:27:22.737190
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "57e1a6493055"
down_revision: Union[str, None] = "d5c351c415ce"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # applications: composite indexes for user listing + status filtering
    op.create_index(
        "idx_applications_user_created",
        "applications",
        ["user_id", "created_at"],
    )
    op.create_index(
        "idx_applications_user_status",
        "applications",
        ["user_id", "status"],
    )

    # audit_logs: composite indexes for user audit trail + rate-limit checks
    op.create_index(
        "idx_audit_logs_user",
        "audit_logs",
        ["user_id", "created_at"],
    )
    op.create_index(
        "idx_audit_logs_action_ip",
        "audit_logs",
        ["action", "ip_address", "created_at"],
    )

    # intro_facilitations: composite indexes for holder pending queue + seeker history
    op.create_index(
        "idx_intro_holder_status",
        "intro_facilitations",
        ["network_holder_id", "status"],
    )
    op.create_index(
        "idx_intro_seeker_created",
        "intro_facilitations",
        ["job_seeker_id", "created_at"],
    )

    # search_requests: composite index for user search history
    op.create_index(
        "idx_search_requests_user_created",
        "search_requests",
        ["user_id", "created_at"],
    )

    # usage_logs: composite index for rate-limit queries (user + action + time window)
    op.create_index(
        "idx_usage_logs_rate_limit",
        "usage_logs",
        ["user_id", "action", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_usage_logs_rate_limit", table_name="usage_logs")
    op.drop_index("idx_search_requests_user_created", table_name="search_requests")
    op.drop_index("idx_intro_seeker_created", table_name="intro_facilitations")
    op.drop_index("idx_intro_holder_status", table_name="intro_facilitations")
    op.drop_index("idx_audit_logs_action_ip", table_name="audit_logs")
    op.drop_index("idx_audit_logs_user", table_name="audit_logs")
    op.drop_index("idx_applications_user_status", table_name="applications")
    op.drop_index("idx_applications_user_created", table_name="applications")
