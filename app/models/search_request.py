import uuid
from datetime import datetime, timezone

from sqlalchemy import ARRAY, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class SearchRequest(Base):
    __tablename__ = "search_requests"
    __table_args__ = (
        Index("idx_search_requests_user_created", "user_id", "created_at"),
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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Structured filters
    target_titles: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    target_companies: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    target_industries: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    target_company_size: Mapped[str | None] = mapped_column(String(100))
    target_locations: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    target_keywords: Mapped[list[str] | None] = mapped_column(ARRAY(Text))

    # Referral-specific fields
    target_role: Mapped[str | None] = mapped_column(String(255))
    target_seniority: Mapped[str | None] = mapped_column(String(100))

    status: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="active"
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    results_data: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
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
    user: Mapped["User"] = relationship(back_populates="search_requests")
    match_results: Mapped[list["MatchResult"]] = relationship(
        back_populates="search_request"
    )
