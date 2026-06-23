"""Register / login / step-up orchestration (Architecture §6.1, Implementation.md
Phase 8's 6-step flow, verbatim):

1. Track A gate: `lock:ip`/`lock:device` -> 423, never the account.
2. Integrity verify BEFORE password -> 400 `INTEGRITY_REJECT` on failure.
3. `verify_password` (Argon2id) -> `block` body (200) on failure, no scoring run.
4. Success -> emit events, read features, score, decide, pick step-up factor if `verify`.
5. Persist risk_scores/decisions off the hot path (`BackgroundTasks`); update
   `session:risk:{id}` (Phase 9 inherits this key, Phase 8 originates it).
6. `allow` -> JWT + `Session` row now; `verify` -> `AuthChallenge` + a `stepup:{id}`
   Redis blob carrying what's needed to finish login on success; `block` -> nothing.

Every outcome is returned as `(http_status, DecisionResponse)` -- never raises for
expected control flow -- so the router can serialize the body directly and callers
(tests) get one uniform shape regardless of branch.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid

from fastapi import BackgroundTasks
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models.behavior import BehaviorSample
from ..models.scoring import AuthChallenge
from ..models.session import LoginEvent, Session as SessionModel
from ..models.user import Account, User
from ..schemas.auth import (
    ConsentRequest,
    LoginRequest,
    NonceResponse,
    RegisterRequest,
    StepUpVerifyRequest,
)
from ..schemas.decision import DecisionResponse, Hardening
from ..schemas.features import FeatureReadContext
from ..schemas.scoring import ReasonCode
from ..scoring import shadow, stack
from ..scoring.registry import Registry
from ..utils import fingerprint, security
from . import audit, case_mgmt, consent, event_producer, feature_reader, hardening, integrity
from .adaptive_auth import select_factor
from .decision_engine import decide
from .policy import active_policy

QUARANTINE_DAYS = 7


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _k_stepup(challenge_id: str) -> str:
    return f"stepup:{challenge_id}"


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


def _get_user_by_username(db: DbSession, username: str) -> User | None:
    return db.scalar(select(User).where(User.customer_ref == username))


def register(db: DbSession, req: RegisterRequest) -> User:
    if _get_user_by_username(db, req.username) is not None:
        raise ValueError(f"username {req.username!r} already registered")
    user = User(
        customer_ref=req.username,
        password_hash=security.hash_password(req.password),
        account_status="active",
    )
    db.add(user)
    db.flush()
    db.add(
        Account(
            user_id=user.user_id,
            account_number=f"ACC{uuid.uuid4().hex[:10].upper()}",
            account_type="savings",
            balance=100_000.00,  # demo seed balance -- no separate account-provisioning flow exists yet
            currency="INR",
            status="active",
        )
    )
    db.commit()
    return user


def consent_action(db: DbSession, req: ConsentRequest) -> User:
    user = _get_user_by_username(db, req.username)
    if user is None:
        raise ValueError(f"unknown username {req.username!r}")
    if req.action == "GRANT":
        consent.grant(db, user, req.consent_version)
    else:
        consent.withdraw(db, user)
    return user


def issue_nonce_for(user_id: str | None = None, *, redis: Redis) -> NonceResponse:
    nonce, expires_at = integrity.issue_nonce(user_id, redis=redis)
    return NonceResponse(nonce=nonce, expires_at=expires_at)


def _reject(
    action: str, *, reason_code: str, hardening_action: Hardening | None, integrity_flag: str = "OK"
) -> DecisionResponse:
    return DecisionResponse(
        action=action,
        entity_type="login",
        risk_score=100.0,
        risk_band="very_high",
        reason_codes=[ReasonCode(code=reason_code)],
        hardening=hardening_action,
        integrity=integrity_flag,
    )


def login(
    db: DbSession,
    redis: Redis,
    registry: Registry,
    req: LoginRequest,
    *,
    ip: str,
    asn: int | None,
    background_tasks: BackgroundTasks,
) -> tuple[int, DecisionResponse]:
    policy = active_policy(redis=redis)
    device_fp = req.behavior.device.fingerprint

    lock = hardening.is_locked(ip, device_fp, redis=redis)
    if lock is not None:
        return 423, _reject("block", reason_code="LOCKOUT", hardening_action=lock)

    ok, reason = integrity.verify(req.behavior, seq_binding=device_fp, redis=redis)
    if not ok:
        h = hardening.register_failure(db, ip, device_fp, asn, policy, redis=redis)
        audit.write_audit_log(
            db,
            actor_type="system",
            actor_id=device_fp,
            action="INTEGRITY_REJECT",
            metadata={"reason": reason},
        )
        return 400, _reject(
            "block",
            reason_code=reason or "INTEGRITY_REJECT",
            hardening_action=h,
            integrity_flag="INTEGRITY_REJECT",
        )

    user = _get_user_by_username(db, req.username)
    if user is None or not security.verify_password(req.password, user.password_hash or ""):
        h = hardening.register_failure(db, ip, device_fp, asn, policy, redis=redis)
        return 200, _reject("block", reason_code="BAD_CREDENTIALS", hardening_action=h)

    hardening.reset(ip, device_fp, redis=redis)

    device = fingerprint.get_or_create_device(db, req.behavior.device)
    fingerprint.get_or_create_user_device(db, user.user_id, device.device_id)
    db.commit()

    kafka_session_id = str(uuid.uuid4())
    event_producer.emit_login_event(
        user_id=str(user.user_id),
        session_id=kafka_session_id,
        device_id=str(device.device_id),
        ip=ip,
        asn=asn,
    )
    event_producer.emit_device_event(
        device_id=str(device.device_id),
        device_fingerprint=device_fp,
        os=req.behavior.device.platform,
        is_rooted=req.behavior.device.is_rooted,
        is_emulator=req.behavior.device.is_emulator,
    )

    ctx = FeatureReadContext(
        behavior=req.behavior, device_id=str(device.device_id), session_id=kafka_session_id
    )
    bundle = feature_reader.read_bundle(str(user.user_id), ctx, redis=redis)
    behavior_features = bundle.behavior
    event_producer.emit_behavior_event(
        user_id=str(user.user_id),
        session_id=kafka_session_id,
        typing_speed=behavior_features.typing_speed,
        key_latency_avg=behavior_features.key_latency_avg,
        typing_rhythm_std=behavior_features.typing_rhythm_std,
        hold_time_avg=behavior_features.hold_time_avg,
        swipe_velocity_norm=behavior_features.swipe_velocity_norm,
        swipe_angle_dev=behavior_features.swipe_angle_dev,
        touch_pressure_avg=behavior_features.touch_pressure_avg,
        acceleration_variance=behavior_features.acceleration_variance,
        mouse_velocity_mean=behavior_features.mouse_velocity_mean,
    )
    result = stack.score(bundle, policy=policy, registry=registry, redis=redis)

    decision = decide(
        result.risk_band,
        "login",
        policy=policy,
        cold_start=bundle.cold_start,
        degraded=result.degraded_mode,
    )
    step_up = None
    if decision.action == "verify":
        step_up = select_factor(decision.assurance or "light", None, policy["stepup"])

    response = DecisionResponse(
        action=decision.action,
        entity_type="login",
        risk_score=result.final_risk_score,
        risk_band=result.risk_band,
        required_factors=[step_up.challenge_type] if step_up else [],
        reason_codes=result.reason_codes,
        action_sensitivity=decision.action_sensitivity,
        step_up=step_up,
        degraded_mode=result.degraded_mode,
        model_version=result.model_version,
    )

    session_row: SessionModel | None = None
    if decision.action == "allow":
        session_row = SessionModel(
            session_id=uuid.UUID(kafka_session_id),
            user_id=user.user_id,
            device_id=device.device_id,
            ip_address=ip,
            asn=asn,
            login_risk_score=result.final_risk_score,
            auth_method_used="password",
            status="active",
        )
        db.add(session_row)
        db.flush()
        token, jwt_id = security.issue_jwt(str(user.user_id), str(session_row.session_id))
        session_row.jwt_id = jwt_id
        response.session_token = token
        _write_session_risk(
            redis,
            str(session_row.session_id),
            risk_band=result.risk_band,
            final_risk_score=result.final_risk_score,
            action="allow",
        )
    elif decision.action == "verify" and step_up is not None:
        challenge = AuthChallenge(challenge_type=step_up.challenge_type, status="issued")
        db.add(challenge)
        db.flush()
        step_up.challenge_id = str(challenge.challenge_id)
        response.step_up = step_up
        redis.set(
            _k_stepup(step_up.challenge_id),
            json.dumps(
                {
                    "user_id": str(user.user_id),
                    "device_id": str(device.device_id),
                    "ip": ip,
                    "asn": asn,
                    "risk_band": result.risk_band,
                    "final_risk_score": result.final_risk_score,
                    "challenge_type": step_up.challenge_type,
                    "assurance": step_up.assurance,
                    "kafka_session_id": kafka_session_id,
                }
            ),
            ex=300,
        )

    db.add(
        LoginEvent(
            session_id=session_row.session_id if session_row else None,
            user_id=user.user_id,
            device_id=device.device_id,
            event_type=(
                "success"
                if decision.action == "allow"
                else ("step_up" if decision.action == "verify" else "failure")
            ),
            behavior_anomaly_score=round(result.behavior_score * 100, 2),
            risk_score=result.final_risk_score,
            decision=decision.action,
        )
    )
    db.commit()

    if consent.is_capture_allowed(user):
        accepted = result.risk_band == "low" and decision.action == "allow"
        db.add(
            BehaviorSample(
                user_id=user.user_id,
                session_id=session_row.session_id if session_row else None,
                channel=req.behavior.channel,
                source=req.behavior.source,
                typing_speed=behavior_features.typing_speed,
                key_latency_avg=behavior_features.key_latency_avg,
                swipe_angle=behavior_features.swipe_angle_dev,
                touch_pressure=behavior_features.touch_pressure_avg,
                mouse_velocity=behavior_features.mouse_velocity_mean,
                accepted=accepted,
                quarantine_until=None if accepted else _now() + dt.timedelta(days=QUARANTINE_DAYS),
            )
        )
        db.commit()

    background_tasks.add_task(
        audit.persist_scoring_outcome,
        db,
        result,
        response,
        entity_type="login",
        entity_id=session_row.session_id if session_row else kafka_session_id,
        user_id=user.user_id,
    )
    background_tasks.add_task(
        shadow.run_and_persist,
        db,
        bundle,
        policy=policy,
        registry=registry,
        redis=redis,
        entity_type="login",
        entity_id=session_row.session_id if session_row else kafka_session_id,
        user_id=user.user_id,
    )
    background_tasks.add_task(
        event_producer.emit_risk_score,
        entity_type="login",
        entity_id=str(session_row.session_id if session_row else kafka_session_id),
        behavior_score=result.behavior_score,
        device_score=result.device_score,
        transaction_score=result.transaction_score,
        final_risk_score=result.final_risk_score,
        risk_band=result.risk_band,
        model_version=result.model_version,
    )
    background_tasks.add_task(
        event_producer.emit_decision,
        entity_type="login",
        entity_id=str(session_row.session_id if session_row else kafka_session_id),
        action=decision.action,
        required_factors=response.required_factors,
        reason_codes=[rc.model_dump() for rc in result.reason_codes],
    )
    if decision.action == "block" or result.risk_band == "very_high":
        background_tasks.add_task(
            case_mgmt.maybe_open_case,
            db,
            user_id=user.user_id,
            transaction_id=None,
            risk_band=result.risk_band,
            action=decision.action,
            reason_codes=[rc.model_dump() for rc in result.reason_codes],
        )

    return 200, response


def verify_step_up(
    db: DbSession,
    redis: Redis,
    req: StepUpVerifyRequest,
    *,
    background_tasks: BackgroundTasks,
) -> tuple[int, DecisionResponse]:
    raw = redis.get(_k_stepup(req.challenge_id))
    if raw is None:
        return 404, _reject("block", reason_code="CHALLENGE_NOT_FOUND", hardening_action=None)
    state = json.loads(raw)

    challenge = db.get(AuthChallenge, uuid.UUID(req.challenge_id))
    challenge_type = state["challenge_type"]
    is_demo_otp = challenge_type in ("OTP", "MPIN")
    passed = (req.otp_or_assertion == "123456") if is_demo_otp else bool(req.otp_or_assertion)

    if not passed:
        attempts = (challenge.attempts if challenge is not None else 0) + 1
        if challenge is not None:
            challenge.attempts = attempts
        max_attempts = active_policy(redis=redis)["stepup"].get("max_attempts", 3)

        # Exhausted retries -> escalate to block + alert (PRD §10.1 "if fail -> Blocked").
        # Consume the step-up blob so the challenge can't be reused, mark it failed, and
        # open a case the same way the login/payment block paths do.
        if attempts >= max_attempts:
            if challenge is not None:
                challenge.status = "failed"
                challenge.resolved_at = _now()
            db.commit()
            redis.delete(_k_stepup(req.challenge_id))
            background_tasks.add_task(
                case_mgmt.maybe_open_case,
                db,
                user_id=uuid.UUID(state["user_id"]),
                transaction_id=None,
                risk_band="very_high",
                action="block",
                reason_codes=[{"code": "STEP_UP_EXHAUSTED"}],
            )
            return 401, _reject("block", reason_code="STEP_UP_EXHAUSTED", hardening_action=None)

        db.commit()
        return 401, _reject("verify", reason_code="STEP_UP_FAILED", hardening_action=None)

    user_id = uuid.UUID(state["user_id"])
    device_id = uuid.UUID(state["device_id"])
    kafka_session_id = state.get("kafka_session_id")
    session_row = SessionModel(
        session_id=uuid.UUID(kafka_session_id) if kafka_session_id else None,
        user_id=user_id,
        device_id=device_id,
        ip_address=state["ip"],
        asn=state.get("asn"),
        login_risk_score=state["final_risk_score"],
        auth_method_used=challenge_type,
        status="active",
    )
    db.add(session_row)
    db.flush()
    token, jwt_id = security.issue_jwt(str(user_id), str(session_row.session_id))
    session_row.jwt_id = jwt_id

    if challenge is not None:
        challenge.status = "passed"
        challenge.resolved_at = _now()

    db.add(
        LoginEvent(
            session_id=session_row.session_id,
            user_id=user_id,
            device_id=device_id,
            event_type="step_up",
            risk_score=state["final_risk_score"],
            decision="allow",
        )
    )
    db.commit()

    _write_session_risk(
        redis,
        str(session_row.session_id),
        risk_band=state["risk_band"],
        final_risk_score=state["final_risk_score"],
        action="allow",
    )
    redis.delete(_k_stepup(req.challenge_id))

    response = DecisionResponse(
        action="allow",
        entity_type="login",
        risk_score=state["final_risk_score"],
        risk_band=state["risk_band"],
        session_token=token,
    )
    return 200, response
