"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-02-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "is_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "plan_tier",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'free'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # 2. connector_profiles
    op.create_table(
        "connector_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("headline", sa.String(500)),
        sa.Column("current_company", sa.String(255)),
        sa.Column("current_title", sa.String(255)),
        sa.Column("industry", sa.String(255)),
        sa.Column("location", sa.String(255)),
        sa.Column("linkedin_url", sa.String(500)),
        sa.Column("bio_summary", sa.Text()),
        sa.Column("raw_profile", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", name="uq_connector_profile_user"),
    )

    # 3. csv_uploads
    op.create_table(
        "csv_uploads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("file_size_bytes", sa.Integer()),
        sa.Column("row_count", sa.Integer()),
        sa.Column("processed_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("error_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_csv_uploads_user_id", "csv_uploads", ["user_id"])
    op.create_index("ix_csv_uploads_status", "csv_uploads", ["status"])

    # 4. companies
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("domain", sa.String(255)),
        sa.Column("linkedin_url", sa.String(500)),
        sa.Column("industry", sa.String(255)),
        sa.Column("company_size", sa.String(100)),
        sa.Column("headquarters", sa.String(255)),
        sa.Column("description", sa.Text()),
        sa.Column("logo_url", sa.String(500)),
        sa.Column("raw_data", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_companies_domain",
        "companies",
        ["domain"],
        unique=True,
        postgresql_where=sa.text("domain IS NOT NULL"),
    )

    # 5. contacts
    op.create_table(
        "contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "csv_upload_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("csv_uploads.id", ondelete="SET NULL"),
        ),
        sa.Column("first_name", sa.String(255)),
        sa.Column("last_name", sa.String(255)),
        sa.Column("full_name", sa.String(500), nullable=False),
        sa.Column("email", sa.String(255)),
        sa.Column("linkedin_url", sa.String(500)),
        sa.Column("current_title", sa.String(500)),
        sa.Column("current_company", sa.String(500)),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
        ),
        sa.Column("location", sa.String(255)),
        sa.Column("connected_on", sa.Date()),
        sa.Column("tags", postgresql.ARRAY(sa.Text())),
        sa.Column("notes", sa.Text()),
        sa.Column("raw_csv_row", postgresql.JSONB()),
        sa.Column("enriched_data", postgresql.JSONB()),
        sa.Column("fingerprint", sa.String(255)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_contacts_user_id", "contacts", ["user_id"])
    op.create_index("ix_contacts_company_id", "contacts", ["company_id"])
    op.create_index("idx_contacts_fingerprint", "contacts", ["user_id", "fingerprint"])
    op.create_index(
        "idx_contacts_dedup",
        "contacts",
        ["user_id", "fingerprint"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND fingerprint IS NOT NULL"),
    )

    # 6. contact_companies
    op.create_table(
        "contact_companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(500)),
        sa.Column(
            "is_current",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_contact_companies_contact_id", "contact_companies", ["contact_id"]
    )
    op.create_index(
        "ix_contact_companies_company_id", "contact_companies", ["company_id"]
    )
    op.create_index(
        "idx_contact_companies_current",
        "contact_companies",
        ["company_id", "is_current"],
        postgresql_where=sa.text("is_current = true"),
    )

    # 7. search_requests
    op.create_table(
        "search_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("target_titles", postgresql.ARRAY(sa.Text())),
        sa.Column("target_companies", postgresql.ARRAY(sa.Text())),
        sa.Column("target_industries", postgresql.ARRAY(sa.Text())),
        sa.Column("target_company_size", sa.String(100)),
        sa.Column("target_locations", postgresql.ARRAY(sa.Text())),
        sa.Column("target_keywords", postgresql.ARRAY(sa.Text())),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_search_requests_user_id", "search_requests", ["user_id"])

    # 8. match_results
    op.create_table(
        "match_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "search_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("search_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relevance_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("match_reasoning", sa.Text(), nullable=False),
        sa.Column("match_type", sa.String(50), nullable=False),
        sa.Column("user_feedback", sa.String(50)),
        sa.Column("feedback_note", sa.Text()),
        sa.Column("ai_model_version", sa.String(100)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "search_request_id", "contact_id", name="idx_match_results_dedup"
        ),
    )
    op.create_index(
        "ix_match_results_search_request_id",
        "match_results",
        ["search_request_id"],
    )
    op.create_index("ix_match_results_user_id", "match_results", ["user_id"])
    op.create_index(
        "idx_match_results_relevance",
        "match_results",
        ["search_request_id", sa.text("relevance_score DESC")],
    )

    # 9. warm_scores
    op.create_table(
        "warm_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("total_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("recency_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("tenu[RESEND_KEY_REDACTED]", sa.Numeric(5, 2), nullable=False),
        sa.Column("context_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("role_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("engagement_score", sa.Numeric(5, 2), server_default=sa.text("0")),
        sa.Column("sco[RESEND_KEY_REDACTED]", postgresql.JSONB()),
        sa.Column(
            "algorithm_version",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'v1'"),
        ),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", "contact_id", name="idx_warm_scores_dedup"),
    )
    op.create_index("ix_warm_scores_user_id", "warm_scores", ["user_id"])
    op.create_index(
        "idx_warm_scores_total",
        "warm_scores",
        ["user_id", sa.text("total_score DESC")],
    )

    # 10. intro_requests
    op.create_table(
        "intro_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "match_result_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("match_results.id", ondelete="SET NULL"),
        ),
        sa.Column("context", sa.Text()),
        sa.Column(
            "tone",
            sa.String(50),
            server_default=sa.text("'professional'"),
        ),
        sa.Column(
            "channel",
            sa.String(50),
            server_default=sa.text("'linkedin'"),
        ),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_intro_requests_user_id", "intro_requests", ["user_id"])

    # 11. intro_messages
    op.create_table(
        "intro_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "intro_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("intro_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("subject_line", sa.String(500)),
        sa.Column("message_body", sa.Text(), nullable=False),
        sa.Column("variant_label", sa.String(100)),
        sa.Column("is_selected", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("user_edited_body", sa.Text()),
        sa.Column("ai_model_version", sa.String(100)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_intro_messages_intro_request_id",
        "intro_messages",
        ["intro_request_id"],
    )

    # 12. enrichment_cache
    op.create_table(
        "enrichment_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cache_key", sa.String(500), nullable=False, unique=True),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_enrichment_cache_cache_key", "enrichment_cache", ["cache_key"])
    op.create_index(
        "ix_enrichment_cache_expires_at", "enrichment_cache", ["expires_at"]
    )

    # 13. usage_logs
    op.create_table(
        "usage_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100)),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True)),
        sa.Column("metadata", postgresql.JSONB()),
        sa.Column("ip_address", postgresql.INET()),
        sa.Column("user_agent", sa.String(500)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_usage_logs_user_id", "usage_logs", ["user_id"])
    op.create_index("ix_usage_logs_action", "usage_logs", ["action"])
    op.create_index(
        "idx_usage_logs_created",
        "usage_logs",
        ["user_id", sa.text("created_at DESC")],
    )

    # updated_at trigger function
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    # Apply trigger to all tables with updated_at
    for table in [
        "users",
        "connector_profiles",
        "csv_uploads",
        "companies",
        "contacts",
        "search_requests",
        "match_results",
        "warm_scores",
        "intro_requests",
        "enrichment_cache",
    ]:
        op.execute(f"""
            CREATE TRIGGER trg_{table}_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
        """)


def downgrade() -> None:
    op.drop_table("usage_logs")
    op.drop_table("enrichment_cache")
    op.drop_table("intro_messages")
    op.drop_table("intro_requests")
    op.drop_table("warm_scores")
    op.drop_table("match_results")
    op.drop_table("search_requests")
    op.drop_table("contact_companies")
    op.drop_table("contacts")
    op.drop_table("companies")
    op.drop_table("csv_uploads")
    op.drop_table("connector_profiles")
    op.drop_table("users")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")
