import datetime as dt
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE")
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.account_id", ondelete="SET NULL")
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.session_id", ondelete="SET NULL")
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.device_id", ondelete="SET NULL")
    )
    beneficiary_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("beneficiaries.beneficiary_id", ondelete="SET NULL")
    )
    amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str | None] = mapped_column(String(8))
    transfer_type: Mapped[str | None] = mapped_column(String(8))  # IMPS|NEFT|RTGS|UPI
    channel: Mapped[str | None] = mapped_column(String(8))  # web|mobile
    is_new_payee: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    status: Mapped[str | None] = mapped_column(
        String(16)
    )  # initiated|pending|allowed|verified|blocked|reversed
    transaction_risk_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    decision: Mapped[str | None] = mapped_column(String(8))  # allow|verify|block
    decision_reason: Mapped[dict | None] = mapped_column(JSONB)  # reason_codes + amplifiers
    initiated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
