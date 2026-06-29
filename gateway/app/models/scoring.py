import datetime as dt
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Index, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class RiskScore(Base):
    """One row per scoring event (login or transaction)."""

    __tablename__ = "risk_scores"
    __table_args__ = (
        Index("idx_risk_scores_user_time", "user_id", "scored_at"),
        Index("idx_risk_scores_band", "risk_band"),
    )

    score_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    entity_type: Mapped[str | None] = mapped_column(String(16))  # login|transaction
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # session_id or txn_id
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL")
    )
    behavior_score: Mapped[float | None] = mapped_column(Numeric(5, 2))  # Isolation Forest
    device_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    transaction_score: Mapped[float | None] = mapped_column(Numeric(5, 2))  # XGBoost
    final_risk_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    risk_band: Mapped[str | None] = mapped_column(String(12))  # low|medium|high|very_high
    model_version: Mapped[str | None] = mapped_column(String(64))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    # Continuous identity verification (Phase 20-22), persisted starting Phase 27 so the
    # SOC dashboard's historical/case views carry the same trust fields the live feed
    # already showed -- no new calculation, just persisting `ScoreResult` fields that were
    # previously computed every request and then discarded.
    trust_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    behavior_match_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    behavior_score_source: Mapped[str | None] = mapped_column(String(16))  # ae|if|fallback
    # Phase 12 challenger/shadow scoring (Implementation.md §12): True for a row produced
    # by scoring/shadow.py's challenger run alongside the champion -- never acted on, never
    # broadcast to the live SOC feed, excluded from /admin/events by default.
    is_shadow: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    scored_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class Decision(Base):
    __tablename__ = "decisions"

    decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    risk_score_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("risk_scores.score_id", ondelete="CASCADE")
    )
    entity_type: Mapped[str | None] = mapped_column(String(16))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str | None] = mapped_column(String(8))  # allow|verify|block
    required_factors: Mapped[dict | None] = mapped_column(JSONB)  # ["OTP","FINGERPRINT"]
    reason_codes: Mapped[dict | None] = mapped_column(JSONB)  # explainability
    decided_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class AuthChallenge(Base):
    __tablename__ = "auth_challenges"

    challenge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.session_id", ondelete="CASCADE")
    )
    decision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("decisions.decision_id", ondelete="SET NULL")
    )
    challenge_type: Mapped[str | None] = mapped_column(
        String(16)
    )  # OTP|MPIN|FINGERPRINT|PASSKEY|VOICE_READBACK
    status: Mapped[str | None] = mapped_column(String(12))  # issued|passed|failed|expired
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    issued_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
