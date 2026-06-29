"""Fraud-ops case lifecycle + analyst actions + label feedback to S3 (Implementation.md
Phase 9). Cases open automatically on `block`/`very_high` outcomes from any scoring
flow (login/payment/continuous re-scoring); analysts then assign/note/resolve them, and
a `confirmed_fraud`/`false_positive` resolution writes one labeled row to S3 for Phase
12's weekly XGBoost retrain -- the feedback loop CLAUDE.md §6 describes but no phase
has written to yet.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..models.governance import Case
from ..models.scoring import RiskScore
from ..models.transaction import Transaction
from ..redis_client import redis_client
from ..s3_client import get_s3
from ..schemas.admin import CaseUpdate
from . import audit

logger = logging.getLogger(__name__)

_SOC_FEED = "soc-feed"

_RESOLVED_LABELS = {"confirmed_fraud", "false_positive"}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _as_uuid(value: uuid.UUID | str) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


_SEVERITY_MAP = {
    "very_high": "critical",
    "high": "high",
    "medium": "medium",
}


def maybe_open_case(
    db: DbSession,
    *,
    user_id: uuid.UUID | str | None,
    transaction_id: uuid.UUID | str | None,
    risk_band: str,
    action: str,
    reason_codes: list[dict[str, Any]] | None = None,
) -> Case | None:
    """Open a case whenever the outcome warrants analyst attention: medium, high, or
    very_high risk, or any action that isn't a clean allow on a low-risk event."""
    if risk_band == "low" and action == "allow":
        return None
    severity = _SEVERITY_MAP.get(risk_band, "high")
    now = _now()
    case = Case(
        user_id=user_id,
        transaction_id=transaction_id,
        alert_type="FRAUD_RISK",
        severity=severity,
        status="open",
    )
    db.add(case)
    db.commit()

    # Publish after commit so the case is guaranteed in PostgreSQL before the
    # WebSocket message reaches the dashboard (eliminates the race condition where
    # the Cases page would refresh and find nothing yet).
    try:
        redis_client.publish(
            _SOC_FEED,
            json.dumps(
                {
                    "event_type": "case_opened",
                    "case_id": str(case.case_id),
                    "user_id": str(case.user_id) if case.user_id else None,
                    "transaction_id": str(case.transaction_id) if case.transaction_id else None,
                    "alert_type": case.alert_type,
                    "severity": severity,
                    "status": "open",
                    "risk_band": risk_band,
                    "action": action,
                    "reason_codes": reason_codes or [],
                    "created_at": now.isoformat(),
                },
                default=str,
            ),
        )
    except Exception:
        logger.warning("case_opened publish failed — dashboard will miss real-time update")

    return case


def update_case(db: DbSession, case_id: uuid.UUID | str, update: CaseUpdate) -> Case:
    case = db.get(Case, _as_uuid(case_id))
    if case is None:
        raise ValueError(f"case {case_id!r} not found")

    if update.assigned_to is not None:
        case.assigned_to = update.assigned_to

    if update.status is not None:
        case.status = update.status
        if update.status in _RESOLVED_LABELS:
            case.resolved_at = _now()
            _write_label(db, case, label=update.status)

    if update.note:
        audit.write_audit_log(
            db,
            actor_type="analyst",
            actor_id=update.assigned_to or case.assigned_to,
            action="CASE_NOTE",
            entity_type="case",
            entity_id=case.case_id,
            metadata={"note": update.note},
        )

    db.commit()
    return case


def _write_label(db: DbSession, case: Case, *, label: str) -> None:
    transaction = db.get(Transaction, case.transaction_id) if case.transaction_id else None
    risk_score = (
        db.scalar(
            select(RiskScore)
            .where(RiskScore.entity_id == case.transaction_id)
            .order_by(RiskScore.scored_at.desc())
        )
        if case.transaction_id is not None
        else None
    )

    body = {
        "case_id": str(case.case_id),
        "user_id": str(case.user_id) if case.user_id else None,
        "transaction_id": str(case.transaction_id) if case.transaction_id else None,
        "label": label,
        "labeled_at": _now().isoformat(),
        "amount": float(transaction.amount) if transaction and transaction.amount else None,
        "transfer_type": transaction.transfer_type if transaction else None,
        "is_new_payee": transaction.is_new_payee if transaction else None,
        "final_risk_score": (
            float(risk_score.final_risk_score)
            if risk_score and risk_score.final_risk_score is not None
            else None
        ),
        "behavior_score": (
            float(risk_score.behavior_score)
            if risk_score and risk_score.behavior_score is not None
            else None
        ),
        "transaction_score": (
            float(risk_score.transaction_score)
            if risk_score and risk_score.transaction_score is not None
            else None
        ),
        "risk_band": risk_score.risk_band if risk_score else None,
    }
    get_s3().put_object(
        Bucket=settings.s3_bucket,
        Key=f"labels/{label}/{case.case_id}.json",
        Body=json.dumps(body, default=str).encode("utf-8"),
        ContentType="application/json",
    )
