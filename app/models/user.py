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

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
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
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    email_verification_token: Mapped[str | None] = mapped_column(String(255))
    email_verification_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
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

    # Relationships
    connector_profile: Mapped["ConnectorProfile | None"] = relationship(
        back_populates="user", uselist=False
    )
    contacts: Mapped[list["Contact"]] = relationship(back_populates="user")
    csv_uploads: Mapped[list["CsvUpload"]] = relationship(back_populates="user")
    search_requests: Mapped[list["SearchRequest"]] = relationship(back_populates="user")
    match_results: Mapped[list["MatchResult"]] = relationship(back_populates="user")
    warm_scores: Mapped[list["WarmScore"]] = relationship(back_populates="user")
    intro_requests: Mapped[list["IntroRequest"]] = relationship(back_populates="user")
    usage_logs: Mapped[list["UsageLog"]] = relationship(back_populates="user")
    applications: Mapped[list["Application"]] = relationship(back_populates="user")
    job_preferences: Mapped["UserJobPreferences | None"] = relationship(
        back_populates="user", uselist=False
    )
    # Marketplace & privacy relationships
    marketplace_listings: Mapped[list["MarketplaceListing"]] = relationship(
        back_populates="network_holder",
        foreign_keys="MarketplaceListing.network_holder_id",
    )
    network_sharing_preferences: Mapped["NetworkSharingPreferences | None"] = (
        relationship(back_populates="user", uselist=False)
    )
    intro_facilitations_as_seeker: Mapped[list["IntroFacilitation"]] = relationship(
        back_populates="job_seeker",
        foreign_keys="IntroFacilitation.job_seeker_id",
    )
    intro_facilitations_as_holder: Mapped[list["IntroFacilitation"]] = relationship(
        back_populates="network_holder",
        foreign_keys="IntroFacilitation.network_holder_id",
    )
    credit_transactions: Mapped[list["CreditTransaction"]] = relationship(
        back_populates="user"
    )
    connector_reputation: Mapped["ConnectorReputation | None"] = relationship(
        back_populates="user", uselist=False
    )
    network_holder_availability: Mapped[list["NetworkHolderAvailability"]] = (
        relationship(back_populates="user")
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
