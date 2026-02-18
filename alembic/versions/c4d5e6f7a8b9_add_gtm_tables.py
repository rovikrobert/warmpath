"""add GTM tables: competitor_profiles, pricing_benchmarks, partnership_opportunities, gtm_experiments

Revision ID: c4d5e6f7a8b9
Revises: a9e1f9c8bffa
Create Date: 2026-02-18 18:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "a9e1f9c8bffa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- competitor_profiles --
    op.create_table(
        "competitor_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column(
            "category",
            sa.String(length=30),
            nullable=False,
            comment="direct, indirect, or adjacent",
        ),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pricing", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "positioning", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("target_market", sa.String(length=200), nullable=True),
        sa.Column("funding_stage", sa.String(length=50), nullable=True),
        sa.Column("employee_count", sa.Integer(), nullable=True),
        sa.Column("strengths", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("weaknesses", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "threat_level",
            sa.String(length=20),
            nullable=False,
            comment="low, medium, high, or critical",
        ),
        sa.Column("last_scraped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "source_urls", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_competitor_profiles_category", "competitor_profiles", ["category"]
    )
    op.create_index(
        "idx_competitor_profiles_threat_level", "competitor_profiles", ["threat_level"]
    )
    op.create_index("idx_competitor_profiles_domain", "competitor_profiles", ["domain"])

    # -- pricing_benchmarks --
    op.create_table(
        "pricing_benchmarks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_name", sa.String(length=200), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column(
            "product_category",
            sa.String(length=50),
            nullable=False,
            comment="referral_platform, job_board, networking, hr_tech, or career_coaching",
        ),
        sa.Column(
            "pricing_model",
            sa.String(length=30),
            nullable=False,
            comment="freemium, subscription, usage, hybrid, or enterprise_only",
        ),
        sa.Column("tiers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("free_tier_exists", sa.Boolean(), nullable=True),
        sa.Column(
            "lowest_paid_price", sa.Numeric(precision=10, scale=2), nullable=True
        ),
        sa.Column("enterprise_available", sa.Boolean(), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_pricing_benchmarks_product_category",
        "pricing_benchmarks",
        ["product_category"],
    )
    op.create_index(
        "idx_pricing_benchmarks_scraped_at", "pricing_benchmarks", ["scraped_at"]
    )
    op.create_index("idx_pricing_benchmarks_domain", "pricing_benchmarks", ["domain"])

    # -- partnership_opportunities --
    op.create_table(
        "partnership_opportunities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("partner_name", sa.String(length=200), nullable=False),
        sa.Column("partner_domain", sa.String(length=255), nullable=True),
        sa.Column(
            "partner_type",
            sa.String(length=30),
            nullable=False,
            comment="bootcamp, university, coach, association, corporate, or strategic",
        ),
        sa.Column(
            "stage",
            sa.String(length=30),
            nullable=False,
            comment="identified, outreach, conversation, proposal, negotiation, signed, or lost",
        ),
        sa.Column("stage_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("contact_name", sa.String(length=200), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("estimated_users", sa.Integer(), nullable=True),
        sa.Column(
            "estimated_monthly_revenue",
            sa.Numeric(precision=10, scale=2),
            nullable=True,
        ),
        sa.Column("notes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "legal_review_status",
            sa.String(length=20),
            nullable=False,
            comment="not_required, pending, approved, or blocked",
        ),
        sa.Column("next_action", sa.String(length=500), nullable=True),
        sa.Column("next_action_date", sa.Date(), nullable=True),
        sa.Column("lost_reason", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_partnership_opportunities_stage", "partnership_opportunities", ["stage"]
    )
    op.create_index(
        "idx_partnership_opportunities_partner_type",
        "partnership_opportunities",
        ["partner_type"],
    )
    op.create_index(
        "idx_partnership_opportunities_next_action_date",
        "partnership_opportunities",
        ["next_action_date"],
    )
    op.create_index(
        "idx_partnership_opportunities_created_by",
        "partnership_opportunities",
        ["created_by"],
    )

    # -- gtm_experiments --
    op.create_table(
        "gtm_experiments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=True),
        sa.Column(
            "experiment_type",
            sa.String(length=30),
            nullable=False,
            comment="pricing, messaging, channel, landing_page, or onboarding",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            comment="draft, running, paused, completed, or analyzed",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("variants", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("target_sample_size", sa.Integer(), nullable=True),
        sa.Column("results", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_gtm_experiments_status", "gtm_experiments", ["status"])
    op.create_index(
        "idx_gtm_experiments_experiment_type", "gtm_experiments", ["experiment_type"]
    )


def downgrade() -> None:
    op.drop_index("idx_gtm_experiments_experiment_type", table_name="gtm_experiments")
    op.drop_index("idx_gtm_experiments_status", table_name="gtm_experiments")
    op.drop_table("gtm_experiments")

    op.drop_index(
        "idx_partnership_opportunities_created_by",
        table_name="partnership_opportunities",
    )
    op.drop_index(
        "idx_partnership_opportunities_next_action_date",
        table_name="partnership_opportunities",
    )
    op.drop_index(
        "idx_partnership_opportunities_partner_type",
        table_name="partnership_opportunities",
    )
    op.drop_index(
        "idx_partnership_opportunities_stage", table_name="partnership_opportunities"
    )
    op.drop_table("partnership_opportunities")

    op.drop_index("idx_pricing_benchmarks_domain", table_name="pricing_benchmarks")
    op.drop_index("idx_pricing_benchmarks_scraped_at", table_name="pricing_benchmarks")
    op.drop_index(
        "idx_pricing_benchmarks_product_category", table_name="pricing_benchmarks"
    )
    op.drop_table("pricing_benchmarks")

    op.drop_index("idx_competitor_profiles_domain", table_name="competitor_profiles")
    op.drop_index(
        "idx_competitor_profiles_threat_level", table_name="competitor_profiles"
    )
    op.drop_index("idx_competitor_profiles_category", table_name="competitor_profiles")
    op.drop_table("competitor_profiles")
