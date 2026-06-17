import datetime as dt
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class BehaviorSample(Base):
    """Raw biometric captures (also archived to S3). Quarantine + retention lifecycle."""

    __tablename__ = "behavior_samples"
    __table_args__ = (
        Index("idx_behavior_samples_quarantine", "quarantine_until"),
        Index("idx_behavior_samples_retention", "retention_expires_at"),
    )

    sample_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE")
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.session_id", ondelete="SET NULL")
    )
    channel: Mapped[str | None] = mapped_column(String(8))  # web|mobile
    source: Mapped[str] = mapped_column(String(16), server_default=text("'web_sdk'"))

    typing_speed: Mapped[float | None] = mapped_column(Numeric)  # keystrokes/sec
    typing_rhythm: Mapped[dict | None] = mapped_column(JSONB)  # inter-key latency vector
    key_latency_avg: Mapped[float | None] = mapped_column(Numeric)
    swipe_angle: Mapped[float | None] = mapped_column(Numeric)
    touch_pressure: Mapped[float | None] = mapped_column(Numeric)
    mouse_velocity: Mapped[float | None] = mapped_column(Numeric)

    # Anti-poisoning quarantine (FR-A4) + DPDP retention (NFR-9)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    quarantine_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    retention_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    captured_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
