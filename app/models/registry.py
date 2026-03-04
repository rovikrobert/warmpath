"""Company board registry — persistent mapping of companies to ATS boards."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class CompanyBoard(Base):
    """Persistent mapping from a company name to its ATS board or career page.

    Replaces the static BOARD_REGISTRY dict with a DB-backed table that can
    be updated at runtime without redeployment.
    """

    __tablename__ = "company_boards"
    __table_args__ = (
        Index("idx_company_boards_key", "company_key", unique=True),
        Index("idx_company_boards_region", "region"),
        Index("idx_company_boards_is_active", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_key: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, comment="Normalized lowercase key"
    )
    display_name: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="Human-readable company name"
    )
    board_source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="greenhouse, lever, ashby, or career_page",
    )
    board_slug: Mapped[str | None] = mapped_column(
        String(255), comment="ATS board slug (null for career_page source)"
    )
    career_page_url: Mapped[str | None] = mapped_column(
        String(1000), comment="Fallback career page URL"
    )
    region: Mapped[str | None] = mapped_column(
        String(100), index=True, comment="Geographic region grouping"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="Last successful ATS probe timestamp"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
