import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Boolean, text
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Session(Base):
    __tablename__ = "sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE")
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.device_id", ondelete="SET NULL")
    )
    jwt_id: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(INET)
    asn: Mapped[int | None] = mapped_column(Integer)
    is_vpn: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    geo_lat: Mapped[float | None] = mapped_column(Numeric(9, 6))
    geo_lon: Mapped[float | None] = mapped_column(Numeric(9, 6))
    geo_city: Mapped[str | None] = mapped_column(String(64))
    geo_country: Mapped[str | None] = mapped_column(String(64))
    login_risk_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    auth_method_used: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(
        String(16), server_default=text("'active'")
    )  # active|ended|terminated
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class LoginEvent(Base):
    __tablename__ = "login_events"

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.session_id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL")
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.device_id", ondelete="SET NULL")
    )
    event_type: Mapped[str | None] = mapped_column(String(16))  # attempt|success|failure|step_up
    behavior_anomaly_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    risk_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    decision: Mapped[str | None] = mapped_column(String(8))  # allow|verify|block
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
