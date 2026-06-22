import datetime as dt
import uuid

from sqlalchemy import DateTime, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Analyst(Base):
    """Fraud-ops staff (admin/analyst), distinct from the customer `User` table --
    Phase 30, fulfilling CLAUDE.md §8's "role-scoped JWT" requirement for admin
    endpoints that no earlier phase implemented. A 17th table beyond the canonical
    16 (PRD §17.1), the same documented-exception pattern as Phase 28's banking
    tables."""

    __tablename__ = "analysts"

    analyst_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(Text, unique=True)
    full_name: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)  # Argon2id
    role: Mapped[str] = mapped_column(String(16), server_default=text("'analyst'"))  # admin|analyst
    status: Mapped[str] = mapped_column(
        String(16), server_default=text("'active'")
    )  # active|inactive
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
