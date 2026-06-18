"""§10.3 payment scoring orchestration (Architecture §6.2/§6.6, Implementation.md
Phase 8): integrity verify -> resolve beneficiary -> emit transaction_event -> build
`TxnContext` -> stacked score with amplifiers -> risk×action decide -> step-up factor if
`verify` -> transaction-fraud-layer controls -> persist + emit + return.

`is_new_payee` for scoring comes from `feature_reader.read_bundle`'s Redis
`known_beneficiaries` check (the same signal `FeatureBundle.txn.is_new_payee` already
uses), not from whether the Postgres `UserBeneficiary` row was just created here --
Flink (not this request) is what eventually adds a beneficiary to that Redis set once it
processes the `transaction_events` topic, so the two systems are deliberately read
separately: Postgres `UserBeneficiary.added_at` is the only place `payee_age_minutes`
(an amplifier input Redis doesn't track at all) can come from.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid

from fastapi import BackgroundTasks
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models.beneficiary import Beneficiary, UserBeneficiary
from ..models.session import Session as SessionModel
from ..models.transaction import Transaction
from ..models.user import Account, User
from ..schemas.features import FeatureReadContext
from ..schemas.payment import PaymentScoreRequest, PaymentScoreResponse
from ..schemas.scoring import ReasonCode
from ..scoring import stack
from ..scoring.amplifiers import NEW_PAYEE_AMOUNT_RATIO, TxnContext
from ..scoring.registry import Registry
from ..utils import fingerprint
from . import audit, case_mgmt, event_producer, feature_reader, integrity
from .adaptive_auth import select_factor
from .decision_engine import decide
from .policy import active_policy
from .txn_fraud_layer import resolve_controls

LARGE_AMOUNT_FALLBACK = 50_000.0  # cold-start accounts with no daily_avg_amount history yet


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _k_session_risk(session_id: str) -> str:
    return f"session:risk:{session_id}"


def _k_new_payees_recent(user_id: str) -> str:
    return f"user:{user_id}:new_payees_recent"


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


def _resolve_beneficiary(
    db: DbSession, user_id: uuid.UUID, beneficiary_id: str | None, beneficiary_vpa: str | None
) -> tuple[Beneficiary | None, UserBeneficiary | None, bool]:
    """Find-or-create the `Beneficiary`/`UserBeneficiary` rows. The returned bool is
    whether the `UserBeneficiary` relationship was just created by this call -- i.e.
    this transaction *is* the "new payee" moment in the system of record. (The
    Redis-derived `bundle.txn.is_new_payee` used for scoring is a separate, eventually-
    consistent signal -- see module docstring.)"""
    if beneficiary_id is None and beneficiary_vpa is None:
        return None, None, False

    beneficiary = None
    if beneficiary_id:
        try:
            beneficiary = db.get(Beneficiary, uuid.UUID(beneficiary_id))
        except ValueError:
            beneficiary = None
    if beneficiary is None and beneficiary_vpa:
        beneficiary = db.scalar(
            select(Beneficiary).where(Beneficiary.account_number == beneficiary_vpa)
        )
    if beneficiary is None:
        beneficiary = Beneficiary(
            account_number=beneficiary_vpa or beneficiary_id,
            beneficiary_type="UPI" if beneficiary_vpa else "BANK",
        )
        db.add(beneficiary)
        db.flush()

    user_beneficiary = db.scalar(
        select(UserBeneficiary).where(
            UserBeneficiary.user_id == user_id,
            UserBeneficiary.beneficiary_id == beneficiary.beneficiary_id,
        )
    )
    just_created = user_beneficiary is None
    if user_beneficiary is None:
        user_beneficiary = UserBeneficiary(
            user_id=user_id, beneficiary_id=beneficiary.beneficiary_id
        )
        db.add(user_beneficiary)
        db.flush()
    db.commit()
    return beneficiary, user_beneficiary, just_created


def _action_type(is_new_payee: bool, amount: float, daily_avg_amount: float) -> str:
    if not is_new_payee:
        return "transfer_known_payee_small"
    is_large = (
        daily_avg_amount <= 0
        or amount > NEW_PAYEE_AMOUNT_RATIO * daily_avg_amount
        or amount >= LARGE_AMOUNT_FALLBACK
    )
    return "transfer_new_payee_large" if is_large else "transfer_known_payee_small"


def score_payment(
    db: DbSession,
    redis: Redis,
    registry: Registry,
    user: User,
    session: SessionModel,
    req: PaymentScoreRequest,
    *,
    ip: str,
    asn: int | None,
    background_tasks: BackgroundTasks,
) -> tuple[int, PaymentScoreResponse]:
    policy = active_policy(redis=redis)

    ok, reason = integrity.verify(req.behavior, seq_binding=str(session.session_id), redis=redis)
    if not ok:
        return 400, PaymentScoreResponse(
            action="block",
            entity_type="transaction",
            risk_score=100.0,
            risk_band="very_high",
            reason_codes=[ReasonCode(code=reason or "INTEGRITY_REJECT")],
            integrity="INTEGRITY_REJECT",
        )

    device = fingerprint.get_or_create_device(db, req.behavior.device)
    fingerprint.get_or_create_user_device(db, user.user_id, device.device_id)
    db.commit()

    beneficiary, user_beneficiary, just_added_payee = _resolve_beneficiary(
        db, user.user_id, req.beneficiary_id, req.beneficiary_vpa
    )

    transaction_id = uuid.uuid4()
    event_producer.emit_transaction_event(
        user_id=str(user.user_id),
        transaction_id=str(transaction_id),
        amount=req.amount,
        beneficiary_id=str(beneficiary.beneficiary_id) if beneficiary else None,
        transfer_type=req.transfer_type,
        is_new_payee=just_added_payee,
    )

    ctx = FeatureReadContext(
        behavior=req.behavior,
        device_id=str(device.device_id),
        amount=req.amount,
        beneficiary_id=str(beneficiary.beneficiary_id) if beneficiary else None,
    )
    bundle = feature_reader.read_bundle(str(user.user_id), ctx, redis=redis)
    is_new_payee = bundle.txn.is_new_payee

    account = db.scalar(select(Account).where(Account.user_id == user.user_id))
    account_balance = float(account.balance) if account and account.balance is not None else None

    payee_age_minutes = None
    if user_beneficiary is not None and user_beneficiary.added_at is not None:
        payee_age_minutes = (_now() - user_beneficiary.added_at).total_seconds() / 60.0

    new_payee_key = _k_new_payees_recent(str(user.user_id))
    new_payee_count_recent = redis.scard(new_payee_key)
    if is_new_payee and beneficiary is not None:
        redis.sadd(new_payee_key, str(beneficiary.beneficiary_id))
        redis.expire(new_payee_key, 3600)
        new_payee_count_recent += 1

    profile = redis.hgetall(f"user:{user.user_id}:profile")
    daily_avg_amount = float(profile.get("avg_amount_30d") or 0.0)

    txn_ctx = TxnContext(
        payee_age_minutes=payee_age_minutes,
        daily_avg_amount=daily_avg_amount,
        amount=req.amount,
        new_payee_count_recent=new_payee_count_recent,
        account_balance=account_balance,
        odd_time=bundle.txn.odd_time,
        pre_txn_dwell_ms=req.behavior.context.pre_txn_dwell_ms,
    )

    result = stack.score(bundle, policy=policy, registry=registry, txn_context=txn_ctx, redis=redis)

    action_type = _action_type(is_new_payee, req.amount, daily_avg_amount)
    decision = decide(
        result.risk_band,
        action_type,
        policy=policy,
        cold_start=bundle.cold_start,
        degraded=result.degraded_mode,
    )
    step_up = None
    if decision.action == "verify":
        step_up = select_factor(decision.assurance or "light", None, policy["stepup"])

    txn_controls = resolve_controls(result.risk_band, result.amplifiers, txn_ctx, policy)
    # decision_engine's RISK_ACTION_MATRIX cooling_off/reconfirm cells (e.g. low risk +
    # high stakes -> "verify + cooling-off", PRD §10.2) are a separate signal from
    # txn_fraud_layer's band/amplifier-driven trigger -- merge both in so a matrix cell
    # that calls for cooling/reconfirm isn't silently dropped just because no amplifier
    # fired and the band itself isn't high/very_high.
    if decision.cooling_off and not txn_controls.cooling_until:
        cooling_minutes = policy.get("cooling_off", {}).get("minutes", 30)
        txn_controls.cooling_until = (_now() + dt.timedelta(minutes=cooling_minutes)).isoformat()
    if decision.reconfirm and not txn_controls.reconfirm:
        txn_controls.reconfirm = policy.get("cooling_off", {}).get("reconfirm_channel", "APP_PUSH")

    if txn_controls.cooling_until and user_beneficiary is not None:
        user_beneficiary.cooling_until = dt.datetime.fromisoformat(txn_controls.cooling_until)

    status_map = {"allow": "allowed", "verify": "verified", "block": "blocked"}
    db.add(
        Transaction(
            transaction_id=transaction_id,
            user_id=user.user_id,
            account_id=account.account_id if account else None,
            session_id=session.session_id,
            device_id=device.device_id,
            beneficiary_id=beneficiary.beneficiary_id if beneficiary else None,
            amount=req.amount,
            currency="INR",
            transfer_type=req.transfer_type,
            channel=req.channel,
            is_new_payee=is_new_payee,
            status=status_map[decision.action],
            transaction_risk_score=result.final_risk_score,
            decision=decision.action,
            decision_reason={
                "reason_codes": [rc.model_dump() for rc in result.reason_codes],
                "amplifiers": [a.model_dump() for a in result.amplifiers],
            },
        )
    )
    db.commit()

    response = PaymentScoreResponse(
        action=decision.action,
        entity_type="transaction",
        risk_score=result.final_risk_score,
        risk_band=result.risk_band,
        required_factors=[step_up.challenge_type] if step_up else [],
        reason_codes=result.reason_codes,
        amplifiers=result.amplifiers,
        action_sensitivity=decision.action_sensitivity,
        step_up=step_up,
        txn_controls=txn_controls,
        degraded_mode=result.degraded_mode,
        model_version=result.model_version,
        base_score=result.base_score,
    )

    _write_session_risk(
        redis,
        str(session.session_id),
        risk_band=result.risk_band,
        final_risk_score=result.final_risk_score,
        action=decision.action,
    )

    background_tasks.add_task(
        audit.persist_scoring_outcome,
        db,
        result,
        response,
        entity_type="transaction",
        entity_id=transaction_id,
        user_id=user.user_id,
    )
    background_tasks.add_task(
        event_producer.emit_risk_score,
        entity_type="transaction",
        entity_id=str(transaction_id),
        behavior_score=result.behavior_score,
        device_score=result.device_score,
        transaction_score=result.transaction_score,
        final_risk_score=result.final_risk_score,
        risk_band=result.risk_band,
        model_version=result.model_version,
    )
    background_tasks.add_task(
        event_producer.emit_decision,
        entity_type="transaction",
        entity_id=str(transaction_id),
        action=decision.action,
        required_factors=response.required_factors,
        reason_codes=[rc.model_dump() for rc in result.reason_codes],
    )
    if decision.action == "block" or result.risk_band == "very_high":
        background_tasks.add_task(
            case_mgmt.maybe_open_case,
            db,
            user_id=user.user_id,
            transaction_id=transaction_id,
            risk_band=result.risk_band,
            action=decision.action,
            reason_codes=[rc.model_dump() for rc in result.reason_codes],
        )

    return 200, response
