import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class MatchResult(Base):
    __tablename__ = "match_results"
    __table_args__ = (
        UniqueConstraint(
            "search_request_id", "contact_id", name="idx_match_results_dedup"
        ),
        Index(
            "idx_match_results_relevance",
            "search_request_id",
            "relevance_score",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    search_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("search_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    relevance_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    match_reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    match_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # User feedback on match quality
    user_feedback: Mapped[str | None] = mapped_column(String(50))
    feedback_note: Mapped[str | None] = mapped_column(Text)

    ai_model_version: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    search_request: Mapped["SearchRequest"] = relationship(
        back_populates="match_results"
    )
    contact: Mapped["Contact"] = relationship(back_populates="match_results")
    user: Mapped["User"] = relationship(back_populates="match_results")
    intro_requests: Mapped[list["IntroRequest"]] = relationship(
        back_populates="match_result"
    )


class WarmScore(Base):
    __tablename__ = "warm_scores"
    __table_args__ = (
        UniqueConstraint("user_id", "contact_id", name="idx_warm_scores_dedup"),
        Index("idx_warm_scores_total", "user_id", "total_score"),
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
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Overall score
    total_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

    # Component scores (each 0-100, weighted to produce total)
    recency_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    tenure_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    context_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    role_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    engagement_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), server_default="0"
    )

    # Breakdown metadata
    score_factors: Mapped[dict | None] = mapped_column(JSONB)
    algorithm_version: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="v1"
    )

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
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
    user: Mapped["User"] = relationship(back_populates="warm_scores")
    contact: Mapped["Contact"] = relationship(back_populates="warm_scores")


class IntroRequest(Base):
    __tablename__ = "intro_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    match_result_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("match_results.id", ondelete="SET NULL"),
    )

    context: Mapped[str | None] = mapped_column(Text)
    tone: Mapped[str | None] = mapped_column(String(50), server_default="professional")
    channel: Mapped[str | None] = mapped_column(String(50), server_default="linkedin")
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="pending"
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
    user: Mapped["User"] = relationship(back_populates="intro_requests")
    contact: Mapped["Contact"] = relationship(back_populates="intro_requests")
    match_result: Mapped["MatchResult | None"] = relationship(
        back_populates="intro_requests"
    )
    intro_messages: Mapped[list["IntroMessage"]] = relationship(
        back_populates="intro_request"
    )


class IntroMessage(Base):
    __tablename__ = "intro_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    intro_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intro_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    subject_line: Mapped[str | None] = mapped_column(String(500))
    message_body: Mapped[str] = mapped_column(Text, nullable=False)
    variant_label: Mapped[str | None] = mapped_column(String(100))

    # User interaction
    is_selected: Mapped[bool | None] = mapped_column(Boolean, server_default="false")
    user_edited_body: Mapped[str | None] = mapped_column(Text)

    ai_model_version: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    intro_request: Mapped["IntroRequest"] = relationship(
        back_populates="intro_messages"
    )
