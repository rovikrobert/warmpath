import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class EmailCampaignLog(Base):
    """Tracks engagement emails sent to users — prevents duplicate sends."""

    __tablename__ = "email_campaign_logs"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "email_type", "sent_date", name="uq_campaign_user_type_date"
        ),
        Index("idx_campaign_user", "user_id"),
        Index("idx_campaign_type_date", "email_type", "sent_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    email_type: Mapped[str] = mapped_column(String(50), nullable=False)
    sent_date: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # YYYY-MM-DD for dedup
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    user: Mapped["User"] = relationship()
