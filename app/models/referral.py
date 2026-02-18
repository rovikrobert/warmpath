"""Referral system models — referral codes and conversion tracking.

Two referral types:
- nh_invite: Job seeker invites someone to become a Network Holder
- js_invite: Job seeker invites another job seeker to join
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class ReferralCode(Base):
    __tablename__ = "referral_codes"
    __table_args__ = (
        Index("idx_referral_codes_owner", "owner_id"),
        Index("idx_referral_codes_code", "code", unique=True),
        Index("idx_referral_codes_target_email", "target_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    referral_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # nh_invite | js_invite
    target_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
    )
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)  # null = unlimited
    uses_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    credits_per_conversion: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="25"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    owner = relationship("User", foreign_keys=[owner_id])
    target_company = relationship("Company", foreign_keys=[target_company_id])
    conversions = relationship(
        "ReferralConversion", back_populates="referral_code", passive_deletes=True
    )


class ReferralConversion(Base):
    __tablename__ = "referral_conversions"
    __table_args__ = (
        Index("idx_referral_conversions_code", "referral_code_id"),
        Index("idx_referral_conversions_user", "referred_user_id"),
        UniqueConstraint(
            "referral_code_id",
            "referred_user_id",
            "conversion_event",
            name="uq_referral_conversion",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    referral_code_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("referral_codes.id", ondelete="CASCADE"),
        nullable=False,
    )
    referred_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversion_event: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # signup | csv_upload | first_search | subscription
    credits_awarded: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    referral_code = relationship("ReferralCode", back_populates="conversions")
    referred_user = relationship("User", foreign_keys=[referred_user_id])
