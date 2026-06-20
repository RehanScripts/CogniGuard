"""Immutable persistence: `risk_scores` + `decisions` + `audit_logs` (Implementation.md
Phase 8). Called via FastAPI `BackgroundTasks.add_task(...)` from the routers/flows so
the writes happen after the response is sent -- this repo's sync SQLAlchemy has no
native async session, so `BackgroundTasks` is the "off the hot path" mechanism (vs. the
architecture's notion of an async write).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session as DbSession

from ..models.governance import AuditLog
from ..models.scoring import Decision, RiskScore
from ..schemas.decision import DecisionResponse
from ..schemas.scoring import ScoreResult


def persist_risk_score(
    db: DbSession,
    result: ScoreResult,
    *,
    entity_type: str,
    entity_id: uuid.UUID | str,
    user_id: uuid.UUID | str | None,
    is_shadow: bool = False,
) -> RiskScore:
    row = RiskScore(
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        behavior_score=round(result.behavior_score * 100, 2),
        device_score=result.device_score,
        transaction_score=round(result.transaction_score * 100, 2),
        final_risk_score=result.final_risk_score,
        risk_band=result.risk_band,
        model_version=result.model_version,
        latency_ms=result.latency_ms,
        is_shadow=is_shadow,
    )
    db.add(row)
    db.commit()
    return row


def persist_decision(
    db: DbSession,
    decision_response: DecisionResponse,
    *,
    risk_score_id: uuid.UUID | str | None,
    entity_type: str,
    entity_id: uuid.UUID | str,
) -> Decision:
    row = Decision(
        risk_score_id=risk_score_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=decision_response.action,
        required_factors=decision_response.required_factors,
        reason_codes=[rc.model_dump() for rc in decision_response.reason_codes],
    )
    db.add(row)
    db.commit()
    return row


def persist_scoring_outcome(
    db: DbSession,
    result: ScoreResult,
    decision_response: DecisionResponse,
    *,
    entity_type: str,
    entity_id: uuid.UUID | str,
    user_id: uuid.UUID | str | None,
) -> tuple[RiskScore, Decision]:
    """Single background task so the persisted `Decision` row links to its `RiskScore`
    via `risk_score_id` -- two independent `BackgroundTasks.add_task` calls can't see
    each other's generated id once scheduled."""
    risk_score = persist_risk_score(
        db, result, entity_type=entity_type, entity_id=entity_id, user_id=user_id
    )
    decision_row = persist_decision(
        db,
        decision_response,
        risk_score_id=risk_score.score_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    return risk_score, decision_row


def write_audit_log(
    db: DbSession,
    *,
    actor_type: str,
    actor_id: str | None,
    action: str,
    entity_type: str | None = None,
    entity_id: uuid.UUID | str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    row = AuditLog(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_=metadata,
    )
    db.add(row)
    db.commit()
    return row
