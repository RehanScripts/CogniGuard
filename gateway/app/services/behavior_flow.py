"""Continuous mid-session re-scoring (Architecture §6.4, Implementation.md Phase 9):
integrity verify -> read features -> stacked score -> if `very_high`, terminate the
session + denylist its JWT + open a case; else update `session:risk:{id}` and let the
client carry on. Unlike `auth_flow.login`/`payment_flow.score_payment`, this does not
go through `decision_engine.decide()` / the risk×action matrix -- §6.4's sequence is a
flat two-branch safety net on `risk_band`, not a stakes-gated action attempt.

`entity_type="transaction"` is used for persistence/Kafka (CLAUDE.md's canonical entity
types are only `login`/`transaction`; Implementation.md literally says "entity
`transaction`/continuous" for this path).
"""

from __future__ import annotations

import datetime as dt
import json

from fastapi import BackgroundTasks
from redis import Redis
from sqlalchemy.orm import Session as DbSession

from ..models.session import Session as SessionModel
from ..models.user import User
from ..schemas.behavior import BehaviorPayload
from ..schemas.decision import BehaviorIngestResponse, DecisionResponse
from ..schemas.features import FeatureReadContext
from ..schemas.scoring import ReasonCode
from ..scoring import shadow, stack
from ..scoring.registry import Registry
from ..utils import security
from . import audit, case_mgmt, event_producer, feature_reader, integrity
from .policy import active_policy

_REPLAY_REASONS = {"NONCE_INVALID", "SEQ_REPLAY"}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _k_session_risk(session_id: str) -> str:
    return f"session:risk:{session_id}"


def _write_session_risk(
    redis: Redis, session_id: str, *, risk_band: str, final_risk_score: float, action: str
) -> None:
    redis.set(
        _k_session_risk(session_id),
        json.dumps(
            {
                "risk_band": risk_band,
                "final_risk_score": final_risk_score,
                "action": action,
                "scored_at": _now().isoformat(),
            }
        ),
        ex=24 * 3600,
    )


def _reject(status_reason: str) -> BehaviorIngestResponse:
    return BehaviorIngestResponse(
        action="verify",
        reauth=False,
        risk_score=100.0,
        risk_band="very_high",
        reason_codes=[ReasonCode(code=status_reason)],
        degraded_mode=False,
    )


def ingest(
    db: DbSession,
    redis: Redis,
    registry: Registry,
    user: User,
    session: SessionModel,
    payload: BehaviorPayload,
    *,
    background_tasks: BackgroundTasks,
) -> tuple[int, BehaviorIngestResponse]:
    ok, reason = integrity.verify(payload, seq_binding=str(session.session_id), redis=redis)
    if not ok:
        status_code = 409 if reason in _REPLAY_REASONS else 400
        return status_code, _reject(reason or "INTEGRITY_REJECT")

    policy = active_policy(redis=redis)

    ctx = FeatureReadContext(
        behavior=payload,
        device_id=str(session.device_id) if session.device_id else None,
        session_id=str(session.session_id),
    )
    bundle = feature_reader.read_bundle(str(user.user_id), ctx, redis=redis)
    behavior_features = bundle.behavior
    event_producer.emit_behavior_event(
        user_id=str(user.user_id),
        session_id=str(session.session_id),
        typing_speed=behavior_features.typing_speed,
        key_latency=behavior_features.key_latency_avg,
        swipe_angle=behavior_features.swipe_angle_dev,
        touch_pressure=behavior_features.touch_pressure_avg,
        mouse_velocity=behavior_features.mouse_velocity_mean,
    )

    result = stack.score(bundle, policy=policy, registry=registry, redis=redis)

    very_high = result.risk_band == "very_high"
    action = "verify" if very_high else "allow"

    if very_high:
        session.status = "terminated"
        session.ended_at = _now()
        if session.jwt_id:
            security.revoke(session.jwt_id)
        db.commit()
    else:
        _write_session_risk(
            redis,
            str(session.session_id),
            risk_band=result.risk_band,
            final_risk_score=result.final_risk_score,
            action=action,
        )

    decision_response = DecisionResponse(
        action=action,
        entity_type="transaction",
        risk_score=result.final_risk_score,
        risk_band=result.risk_band,
        reason_codes=result.reason_codes,
        degraded_mode=result.degraded_mode,
        model_version=result.model_version,
        trust_score=result.trust_score,
        behavior_match_score=result.behavior_match_score,
        behavior_score_source=result.behavior_score_source,
        device_trust=result.device_score,
    )
    client_response = BehaviorIngestResponse(
        action=action,
        reauth=very_high,
        risk_score=result.final_risk_score,
        risk_band=result.risk_band,
        reason_codes=result.reason_codes,
        degraded_mode=result.degraded_mode,
        model_version=result.model_version,
        trust_score=result.trust_score,
        behavior_match_score=result.behavior_match_score,
        behavior_score_source=result.behavior_score_source,
        device_trust=result.device_score,
    )

    background_tasks.add_task(
        audit.persist_scoring_outcome,
        db,
        result,
        decision_response,
        entity_type="transaction",
        entity_id=session.session_id,
        user_id=user.user_id,
    )
    background_tasks.add_task(
        shadow.run_and_persist,
        db,
        bundle,
        policy=policy,
        registry=registry,
        redis=redis,
        entity_type="transaction",
        entity_id=session.session_id,
        user_id=user.user_id,
    )
    background_tasks.add_task(
        event_producer.emit_risk_score,
        entity_type="transaction",
        entity_id=str(session.session_id),
        behavior_score=result.behavior_score,
        device_score=result.device_score,
        transaction_score=result.transaction_score,
        final_risk_score=result.final_risk_score,
        risk_band=result.risk_band,
        model_version=result.model_version,
        trust_score=result.trust_score,
        behavior_match_score=result.behavior_match_score,
        behavior_score_source=result.behavior_score_source,
    )
    background_tasks.add_task(
        event_producer.emit_decision,
        entity_type="transaction",
        entity_id=str(session.session_id),
        action=action,
        required_factors=[],
        reason_codes=[rc.model_dump() for rc in result.reason_codes],
    )
    if very_high:
        background_tasks.add_task(
            case_mgmt.maybe_open_case,
            db,
            user_id=user.user_id,
            transaction_id=None,
            risk_band=result.risk_band,
            action=action,
            reason_codes=[rc.model_dump() for rc in result.reason_codes],
        )

    return 200, client_response
