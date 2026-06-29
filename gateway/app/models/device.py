import datetime as dt
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import TEXT as PG_TEXT
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Device(Base):
    __tablename__ = "devices"

    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    device_fingerprint: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    os: Mapped[str | None] = mapped_column(String(32))
    os_version: Mapped[str | None] = mapped_column(String(32))
    browser: Mapped[str | None] = mapped_column(Text)
    app_version: Mapped[str | None] = mapped_column(String(32))
    is_rooted: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_emulator: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    first_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    last_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class UserDevice(Base):
    __tablename__ = "user_devices"
    __table_args__ = (UniqueConstraint("user_id", "device_id", name="uq_user_device"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE")
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.device_id", ondelete="CASCADE")
    )
    trust_score: Mapped[float] = mapped_column(Numeric(5, 2), server_default=text("0"))  # 0..100
    is_trusted: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    binding_status: Mapped[str | None] = mapped_column(String(16))  # bound|pending|revoked
    first_linked_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    public_key: Mapped[str | None] = mapped_column(Text)  # PEM RSA public key for KeyStore binding
