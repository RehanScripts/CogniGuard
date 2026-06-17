import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Case(Base):
    """Fraud-ops alerts / investigations."""

    __tablename__ = "cases"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL")
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.transaction_id", ondelete="SET NULL")
    )
    alert_type: Mapped[str | None] = mapped_column(String(32))
    severity: Mapped[str | None] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(
        String(20), server_default=text("'open'")
    )  # open|investigating|confirmed_fraud|false_positive|closed
    assigned_to: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    """Immutable audit trail of every state change."""

    __tablename__ = "audit_logs"

    log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    actor_type: Mapped[str | None] = mapped_column(String(12))  # system|user|analyst
    actor_id: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str | None] = mapped_column(String(64))
    entity_type: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class ModelRegistry(Base):
    __tablename__ = "model_registry"

    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    model_name: Mapped[str | None] = mapped_column(
        String(32)
    )  # xgboost_txn|isolation_forest|lstm_seq
    model_type: Mapped[str | None] = mapped_column(String(32))
    version: Mapped[str | None] = mapped_column(String(64))
    stage: Mapped[str | None] = mapped_column(String(16))  # staging|production|archived
    artifact_uri: Mapped[str | None] = mapped_column(Text)  # S3 path
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    deployed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
