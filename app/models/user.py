import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint(
            "oauth_provider", "oauth_provider_id", name="uq_user_oauth_identity"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    oauth_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    oauth_provider_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    plan_tier: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="free"
    )
    user_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="job_seeker"
    )
    # Security / session management
    token_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    email_verification_token: Mapped[str | None] = mapped_column(String(255))
    email_verification_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    password_reset_token: Mapped[str | None] = mapped_column(String(255))
    password_reset_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # Privacy / GDPR
    processing_restricted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    marketing_opt_out: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
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

    # Relationships (passive_deletes=True defers to DB-level ON DELETE CASCADE)
    connector_profile: Mapped["ConnectorProfile | None"] = relationship(
        back_populates="user", uselist=False, passive_deletes=True
    )
    contacts: Mapped[list["Contact"]] = relationship(
        back_populates="user", passive_deletes=True
    )
    csv_uploads: Mapped[list["CsvUpload"]] = relationship(
        back_populates="user", passive_deletes=True
    )
    search_requests: Mapped[list["SearchRequest"]] = relationship(
        back_populates="user", passive_deletes=True
    )
    match_results: Mapped[list["MatchResult"]] = relationship(
        back_populates="user", passive_deletes=True
    )
    warm_scores: Mapped[list["WarmScore"]] = relationship(
        back_populates="user", passive_deletes=True
    )
    intro_requests: Mapped[list["IntroRequest"]] = relationship(
        back_populates="user", passive_deletes=True
    )
    usage_logs: Mapped[list["UsageLog"]] = relationship(
        back_populates="user", passive_deletes=True
    )
    applications: Mapped[list["Application"]] = relationship(
        back_populates="user", passive_deletes=True
    )
    job_preferences: Mapped["UserJobPreferences | None"] = relationship(
        back_populates="user", uselist=False, passive_deletes=True
    )
    # Marketplace & privacy relationships
    marketplace_listings: Mapped[list["MarketplaceListing"]] = relationship(
        back_populates="network_holder",
        foreign_keys="MarketplaceListing.network_holder_id",
        passive_deletes=True,
    )
    network_sharing_preferences: Mapped["NetworkSharingPreferences | None"] = (
        relationship(back_populates="user", uselist=False, passive_deletes=True)
    )
    intro_facilitations_as_seeker: Mapped[list["IntroFacilitation"]] = relationship(
        back_populates="job_seeker",
        foreign_keys="IntroFacilitation.job_seeker_id",
        passive_deletes=True,
    )
    intro_facilitations_as_holder: Mapped[list["IntroFacilitation"]] = relationship(
        back_populates="network_holder",
        foreign_keys="IntroFacilitation.network_holder_id",
        passive_deletes=True,
    )
    credit_transactions: Mapped[list["CreditTransaction"]] = relationship(
        back_populates="user", passive_deletes=True
    )
    connector_reputation: Mapped["ConnectorReputation | None"] = relationship(
        back_populates="user", uselist=False, passive_deletes=True
    )
    network_holder_availability: Mapped[list["NetworkHolderAvailability"]] = (
        relationship(back_populates="user", passive_deletes=True)
    )


class ConnectorProfile(Base):
    __tablename__ = "connector_profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_connector_profile_user"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    headline: Mapped[str | None] = mapped_column(String(500))
    current_company: Mapped[str | None] = mapped_column(String(255))
    current_title: Mapped[str | None] = mapped_column(String(255))
    industry: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    bio_summary: Mapped[str | None] = mapped_column(Text)
    work_history: Mapped[list | None] = mapped_column(JSONB, server_default="[]")
    raw_profile: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="connector_profile")
