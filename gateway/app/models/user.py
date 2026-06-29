import datetime as dt
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    customer_ref: Mapped[str | None] = mapped_column(Text, unique=True)  # bank customer number
    full_name: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)  # tokenized at rest in prod
    phone: Mapped[str | None] = mapped_column(Text)  # tokenized at rest in prod
    password_hash: Mapped[str | None] = mapped_column(Text)  # Argon2id
    account_status: Mapped[str] = mapped_column(String(32), default="active")  # active|frozen|closed|pending_email_verify
    kyc_level: Mapped[str | None] = mapped_column(String(16))
    baseline_risk_tier: Mapped[str | None] = mapped_column(String(8))  # low|medium|high

    # DPDP consent (NFR-9)
    is_minor: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    consent_status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=text("'NONE'")
    )  # NONE|GRANTED|WITHDRAWN
    consent_timestamp: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    consent_version: Mapped[str | None] = mapped_column(String(16))

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Account(Base):
    __tablename__ = "accounts"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE")
    )
    account_number: Mapped[str | None] = mapped_column(Text, unique=True)
    account_type: Mapped[str | None] = mapped_column(String(16))  # savings|current
    balance: Mapped[float | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str | None] = mapped_column(String(8))
    status: Mapped[str | None] = mapped_column(String(16))
    opened_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
