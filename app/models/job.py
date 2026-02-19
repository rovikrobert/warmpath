import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class JobOpening(Base):
    __tablename__ = "job_openings"
    __table_args__ = (
        UniqueConstraint("source", "source_job_id", name="uq_job_openings_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    department: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_job_id: Mapped[str | None] = mapped_column(String(255))
    is_remote: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    raw_data: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    company: Mapped["Company | None"] = relationship(back_populates="job_openings")
    applications: Mapped[list["Application"]] = relationship(
        back_populates="job_opening"
    )


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'message_sent', 'responded', "
            "'interview_scheduled', 'interviewed', 'offer_received', "
            "'offer_accepted', 'rejected', 'withdrawn', 'no_response')",
            name="ck_applications_status",
        ),
        Index("idx_applications_user_created", "user_id", "created_at"),
        Index("idx_applications_user_status", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL")
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL")
    )
    job_opening_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_openings.id", ondelete="SET NULL")
    )
    match_result_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("match_results.id", ondelete="SET NULL")
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_title: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="draft",
        index=True,
    )
    channel: Mapped[str | None] = mapped_column(String(50))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    user: Mapped["User"] = relationship(back_populates="applications")
    company: Mapped["Company | None"] = relationship(back_populates="applications")
    contact: Mapped["Contact | None"] = relationship(back_populates="applications")
    job_opening: Mapped["JobOpening | None"] = relationship(
        back_populates="applications"
    )
    match_result: Mapped["MatchResult | None"] = relationship(
        back_populates="applications"
    )


class UserJobPreferences(Base):
    __tablename__ = "user_job_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_job_preferences_user"),
        CheckConstraint(
            "job_search_status IN ('active', 'passive', 'paused')",
            name="ck_user_job_preferences_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_role: Mapped[str | None] = mapped_column(String(255))
    target_seniority: Mapped[str | None] = mapped_column(String(100))
    target_industries: Mapped[dict | None] = mapped_column(JSONB, server_default="'[]'")
    target_locations: Mapped[dict | None] = mapped_column(JSONB, server_default="'[]'")
    open_to_remote: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    job_search_status: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="job_preferences")
