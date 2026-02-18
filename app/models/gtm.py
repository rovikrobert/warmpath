"""GTM (Go-To-Market) models — competitors, pricing benchmarks, partnerships, experiments."""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class CompetitorProfile(Base):
    """Tracked competitor with feature/pricing/positioning intelligence."""

    __tablename__ = "competitor_profiles"
    __table_args__ = (
        Index("idx_competitor_profiles_category", "category"),
        Index("idx_competitor_profiles_threat_level", "threat_level"),
        Index("idx_competitor_profiles_domain", "domain"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="direct, indirect, or adjacent"
    )
    features: Mapped[dict | None] = mapped_column(JSONB)
    pricing: Mapped[dict | None] = mapped_column(JSONB)
    positioning: Mapped[dict | None] = mapped_column(JSONB)
    target_market: Mapped[str | None] = mapped_column(String(200))
    funding_stage: Mapped[str | None] = mapped_column(String(50))
    employee_count: Mapped[int | None] = mapped_column(Integer)
    strengths: Mapped[dict | None] = mapped_column(JSONB)
    weaknesses: Mapped[dict | None] = mapped_column(JSONB)
    threat_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="medium",
        comment="low, medium, high, or critical",
    )
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_urls: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PricingBenchmark(Base):
    """Pricing data point from a competitor or adjacent product."""

    __tablename__ = "pricing_benchmarks"
    __table_args__ = (
        Index("idx_pricing_benchmarks_product_category", "product_category"),
        Index("idx_pricing_benchmarks_scraped_at", "scraped_at"),
        Index("idx_pricing_benchmarks_domain", "domain"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255))
    product_category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="referral_platform, job_board, networking, hr_tech, or career_coaching",
    )
    pricing_model: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="freemium, subscription, usage, hybrid, or enterprise_only",
    )
    tiers: Mapped[dict | None] = mapped_column(JSONB)
    free_tier_exists: Mapped[bool | None] = mapped_column(Boolean)
    lowest_paid_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    enterprise_available: Mapped[bool | None] = mapped_column(Boolean)
    source_url: Mapped[str | None] = mapped_column(String(500))
    scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PartnershipOpportunity(Base):
    """Partnership pipeline entry — bootcamps, universities, coaches, etc."""

    __tablename__ = "partnership_opportunities"
    __table_args__ = (
        Index("idx_partnership_opportunities_stage", "stage"),
        Index("idx_partnership_opportunities_partner_type", "partner_type"),
        Index("idx_partnership_opportunities_next_action_date", "next_action_date"),
        Index("idx_partnership_opportunities_created_by", "created_by"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    partner_name: Mapped[str] = mapped_column(String(200), nullable=False)
    partner_domain: Mapped[str | None] = mapped_column(String(255))
    partner_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="bootcamp, university, coach, association, corporate, or strategic",
    )
    stage: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="identified",
        comment="identified, outreach, conversation, proposal, negotiation, signed, or lost",
    )
    stage_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    contact_name: Mapped[str | None] = mapped_column(String(200))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    estimated_users: Mapped[int | None] = mapped_column(Integer)
    estimated_monthly_revenue: Mapped[float | None] = mapped_column(Numeric(10, 2))
    notes: Mapped[dict | None] = mapped_column(JSONB)
    legal_review_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="not_required",
        comment="not_required, pending, approved, or blocked",
    )
    next_action: Mapped[str | None] = mapped_column(String(500))
    next_action_date: Mapped[date | None] = mapped_column(Date)
    lost_reason: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GTMExperiment(Base):
    """A/B test or growth experiment with hypothesis, variants, and results."""

    __tablename__ = "gtm_experiments"
    __table_args__ = (
        Index("idx_gtm_experiments_status", "status"),
        Index("idx_gtm_experiments_experiment_type", "experiment_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    hypothesis: Mapped[str | None] = mapped_column(Text)
    experiment_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="pricing, messaging, channel, landing_page, or onboarding",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        comment="draft, running, paused, completed, or analyzed",
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    variants: Mapped[dict | None] = mapped_column(JSONB)
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    target_sample_size: Mapped[int | None] = mapped_column(Integer)
    results: Mapped[dict | None] = mapped_column(JSONB)
    conclusion: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
