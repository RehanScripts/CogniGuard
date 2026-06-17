import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Beneficiary(Base):
    __tablename__ = "beneficiaries"

    beneficiary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    account_number: Mapped[str | None] = mapped_column(Text)
    bank_code: Mapped[str | None] = mapped_column(String(16))  # IFSC / routing
    name: Mapped[str | None] = mapped_column(Text)
    beneficiary_type: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class UserBeneficiary(Base):
    __tablename__ = "user_beneficiaries"
    __table_args__ = (UniqueConstraint("user_id", "beneficiary_id", name="uq_user_beneficiary"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE")
    )
    beneficiary_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("beneficiaries.beneficiary_id", ondelete="CASCADE")
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    cooling_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    transfer_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    total_amount_sent: Mapped[float] = mapped_column(Numeric(18, 2), server_default=text("0"))
    added_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
