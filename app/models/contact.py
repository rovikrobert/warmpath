import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base
from app.utils.encryption import EncryptedString, EncryptedText


class CsvUpload(Base):
    __tablename__ = "csv_uploads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    row_count: Mapped[int | None] = mapped_column(Integer)
    processed_count: Mapped[int | None] = mapped_column(Integer, server_default="0")
    error_count: Mapped[int | None] = mapped_column(Integer, server_default="0")
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="pending", index=True
    )
    contacts_created: Mapped[int | None] = mapped_column(Integer, server_default="0")
    duplicates_skipped: Mapped[int | None] = mapped_column(Integer, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="csv_uploads")
    contacts: Mapped[list["Contact"]] = relationship(back_populates="csv_upload")


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        Index("idx_contacts_fingerprint", "user_id", "fingerprint"),
        Index(
            "idx_contacts_dedup",
            "user_id",
            "fingerprint",
            unique=True,
            postgresql_where="deleted_at IS NULL AND fingerprint IS NOT NULL",
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
    csv_upload_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("csv_uploads.id", ondelete="SET NULL"),
        index=True,
    )

    # Core identity fields (from LinkedIn CSV) — encrypted at rest
    first_name: Mapped[str | None] = mapped_column(EncryptedString())
    last_name: Mapped[str | None] = mapped_column(EncryptedString())
    full_name: Mapped[str] = mapped_column(EncryptedString(), nullable=False)
    email: Mapped[str | None] = mapped_column(EncryptedString())
    linkedin_url: Mapped[str | None] = mapped_column(EncryptedString())

    # Current position (from CSV or enrichment) — encrypted at rest
    current_title: Mapped[str | None] = mapped_column(EncryptedString())
    current_company: Mapped[str | None] = mapped_column(EncryptedString())
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        index=True,
    )

    # Additional context — encrypted at rest
    location: Mapped[str | None] = mapped_column(EncryptedString())
    connected_on: Mapped[date | None] = mapped_column(Date)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    notes: Mapped[str | None] = mapped_column(EncryptedText())

    # Relationship classification
    relationship_type: Mapped[str | None] = mapped_column(String(50), index=True)
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="linkedin_csv",
        index=True,
    )
    how_you_know: Mapped[str | None] = mapped_column(EncryptedText())
    last_interaction_date: Mapped[date | None] = mapped_column(Date)

    # Raw and enriched data
    raw_csv_row: Mapped[dict | None] = mapped_column(JSONB)
    enriched_data: Mapped[dict | None] = mapped_column(JSONB)

    # Deduplication
    fingerprint: Mapped[str | None] = mapped_column(String(255))

    # Blind indexes for exact-match lookups on encrypted columns
    email_blind_index: Mapped[str | None] = mapped_column(String(64), index=True)
    name_company_blind_index: Mapped[str | None] = mapped_column(String(64), index=True)

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
    user: Mapped["User"] = relationship(back_populates="contacts")
    csv_upload: Mapped["CsvUpload | None"] = relationship(back_populates="contacts")
    company: Mapped["Company | None"] = relationship(back_populates="contacts")
    contact_companies: Mapped[list["ContactCompany"]] = relationship(
        back_populates="contact"
    )
    match_results: Mapped[list["MatchResult"]] = relationship(back_populates="contact")
    warm_scores: Mapped[list["WarmScore"]] = relationship(back_populates="contact")
    intro_requests: Mapped[list["IntroRequest"]] = relationship(
        back_populates="contact"
    )
    applications: Mapped[list["Application"]] = relationship(back_populates="contact")
    marketplace_listings: Mapped[list["MarketplaceListing"]] = relationship(
        back_populates="contact"
    )


class ContactCompany(Base):
    __tablename__ = "contact_companies"
    __table_args__ = (
        Index(
            "idx_contact_companies_current",
            "company_id",
            "is_current",
            postgresql_where="is_current = true",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(500))
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    contact: Mapped["Contact"] = relationship(back_populates="contact_companies")
    company: Mapped["Company"] = relationship(back_populates="contact_companies")
