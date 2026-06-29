"""Admin router (Implementation.md Phase 8 subset + Phase 9 `/cases` + Phase 12
`/models`+`/drift`; Phase 30 RBAC): `/login` is open; every other route requires the
admin-track JWT (`deps.require_role`) -- `admin` for policy/model writes, either
`admin` or `analyst` for read/case-triage routes.
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from redis import Redis
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session as DbSession

from training import drift_monitor, promote

from .. import deps
from ..redis_client import redis_client
from ..models.behavior import BehaviorSample
from ..models.device import Device, UserDevice
from ..models.governance import Case, ModelRegistry
from ..models.scoring import AuthChallenge, Decision, RiskScore
from ..models.session import LoginEvent, Session as SessionModel
from ..models.transaction import Transaction
from ..models.user import User
from ..scoring import shap_explainer
from ..scoring.registry import Registry
from ..schemas.admin import (
    AdminLoginRequest,
    AdminLoginResponse,
    AuthTimelineEventOut,
    CaseOut,
    CaseUpdate,
    DeviceIntelOut,
    DriftReportOut,
    EventOut,
    FactoryResetOut,
    GeoEntryOut,
    InvestigationResultOut,
    ModelOut,
    ModelVersionOut,
    PolicyUpdate,
    PromoteRequest,
    RollbackRequest,
    ShapExplanationOut,
    UserDetailOut,
)
from ..services import analyst_auth, case_mgmt, investigation_llm
from ..services.policy import DEFAULT_POLICY, POLICY_REDIS_KEY, active_policy

router = APIRouter()

_any_role = Depends(deps.require_role("admin", "analyst"))
_admin_only = Depends(deps.require_role("admin"))


@router.post("/login", response_model=AdminLoginResponse)
def login(req: AdminLoginRequest, db: DbSession = Depends(deps.get_db)) -> AdminLoginResponse:
    result = analyst_auth.login(db, req)
    if result is None:
        raise HTTPException(status_code=401, detail="invalid credentials")
    return result


def _event_out(row: RiskScore, action: str | None) -> EventOut:
    return EventOut(
        score_id=str(row.score_id),
        entity_type=row.entity_type or "",
        entity_id=str(row.entity_id) if row.entity_id else None,
        user_id=str(row.user_id) if row.user_id else None,
        final_risk_score=row.final_risk_score,
        risk_band=row.risk_band,
        action=action,
        model_version=row.model_version,
        latency_ms=row.latency_ms,
        scored_at=row.scored_at.isoformat() if row.scored_at else None,
        trust_score=row.trust_score,
        behavior_match_score=row.behavior_match_score,
        behavior_score_source=row.behavior_score_source,
    )


@router.get("/events", response_model=list[EventOut], dependencies=[_any_role])
def list_events(
    band: str | None = None,
    user_id: str | None = None,
    entity_type: str | None = None,
    limit: int = Query(default=50, le=500),
    db: DbSession = Depends(deps.get_db),
) -> list[EventOut]:
    # Shadow (challenger) rows are for offline comparison only -- the live SOC feed must
    # never show them (Implementation.md Phase 12).
    stmt = (
        select(RiskScore)
        .where(RiskScore.is_shadow.is_(False))
        .order_by(RiskScore.scored_at.desc())
        .limit(limit)
    )
    if band:
        stmt = stmt.where(RiskScore.risk_band == band)
    if user_id:
        stmt = stmt.where(RiskScore.user_id == uuid.UUID(user_id))
    if entity_type:
        stmt = stmt.where(RiskScore.entity_type == entity_type)
    rows = db.scalars(stmt).all()

    entity_ids = [r.entity_id for r in rows if r.entity_id is not None]
    decisions = (
        {
            d.entity_id: d.action
            for d in db.scalars(select(Decision).where(Decision.entity_id.in_(entity_ids)))
        }
        if entity_ids
        else {}
    )
    return [_event_out(r, decisions.get(r.entity_id)) for r in rows]


@router.get("/users/{user_id}", response_model=UserDetailOut, dependencies=[_any_role])
def get_user_detail(user_id: str, db: DbSession = Depends(deps.get_db)) -> UserDetailOut:
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid user_id")

    user = db.get(User, uid)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    devices = db.scalars(select(UserDevice).where(UserDevice.user_id == uid)).all()
    recent = db.scalars(
        select(RiskScore)
        .where(RiskScore.user_id == uid, RiskScore.is_shadow.is_(False))
        .order_by(RiskScore.scored_at.desc())
        .limit(20)
    ).all()
    quarantined = db.scalar(
        select(func.count())
        .select_from(BehaviorSample)
        .where(BehaviorSample.user_id == uid, BehaviorSample.accepted.is_(False))
    )

    return UserDetailOut(
        user={
            "user_id": str(user.user_id),
            "customer_ref": user.customer_ref,
            "consent_status": user.consent_status,
            "account_status": user.account_status,
        },
        devices=[
            {
                "device_id": str(d.device_id),
                "trust_score": float(d.trust_score),
                "is_trusted": d.is_trusted,
            }
            for d in devices
        ],
        recent_events=[_event_out(r, None) for r in recent],
        quarantined_samples=quarantined or 0,
    )


@router.get(
    "/users/{user_id}/auth-timeline",
    response_model=list[AuthTimelineEventOut],
    dependencies=[_any_role],
)
def get_auth_timeline(
    user_id: str, db: DbSession = Depends(deps.get_db)
) -> list[AuthTimelineEventOut]:
    """D2: recent login events + step-up challenges for a user (analyst-only)."""
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid user_id")

    events = db.scalars(
        select(LoginEvent)
        .where(LoginEvent.user_id == uid)
        .order_by(LoginEvent.created_at.desc())
        .limit(50)
    ).all()

    out: list[AuthTimelineEventOut] = []
    for ev in events:
        device_label: str | None = None
        if ev.device_id:
            d = db.get(Device, ev.device_id)
            if d:
                device_label = " ".join(p for p in (d.os, d.browser) if p) or None

        challenge_type: str | None = None
        if ev.event_type == "step_up" and ev.session_id:
            challenge_row = db.scalar(
                select(AuthChallenge)
                .where(AuthChallenge.challenge_id == ev.session_id)
            )
            if challenge_row:
                challenge_type = challenge_row.challenge_type

        out.append(
            AuthTimelineEventOut(
                event_id=str(ev.event_id),
                event_type=ev.event_type,
                challenge_type=challenge_type,
                decision=ev.decision,
                risk_band=None,
                device_label=device_label,
                created_at=ev.created_at,
            )
        )
    return out


@router.get(
    "/devices/{device_id}",
    response_model=DeviceIntelOut,
    dependencies=[_any_role],
)
def get_device_intel(
    device_id: str, db: DbSession = Depends(deps.get_db)
) -> DeviceIntelOut:
    """D3: device intelligence — trust class, geo trend, linked users."""
    try:
        did = uuid.UUID(device_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid device_id")

    device = db.get(Device, did)
    if device is None:
        raise HTTPException(status_code=404, detail="device not found")

    user_links = db.scalars(
        select(UserDevice).where(UserDevice.device_id == did)
    ).all()
    trust_score = float(user_links[0].trust_score) if user_links else None
    is_trusted = any(l.is_trusted for l in user_links)

    trust_class = "unknown"
    if trust_score is not None:
        if trust_score >= 60 and is_trusted:
            trust_class = "trusted"
        elif trust_score >= 40:
            trust_class = "known"
        elif device.is_rooted or device.is_emulator:
            trust_class = "suspicious"
        else:
            trust_class = "new"

    geo_rows = db.scalars(
        select(SessionModel)
        .where(SessionModel.device_id == did)
        .order_by(SessionModel.started_at.desc())
        .limit(5)
    ).all()

    geo_trend = [
        GeoEntryOut(
            ip_address=str(s.ip_address) if s.ip_address else None,
            city=s.geo_city,
            country=s.geo_country,
            seen_at=s.started_at,
        )
        for s in geo_rows
    ]

    event_count = db.scalar(
        select(func.count()).select_from(RiskScore).where(
            RiskScore.entity_id.in_(
                select(SessionModel.session_id).where(SessionModel.device_id == did)
            )
        )
    ) or 0

    return DeviceIntelOut(
        device_id=str(did),
        os=device.os,
        os_version=device.os_version,
        browser=device.browser,
        is_rooted=device.is_rooted,
        is_emulator=device.is_emulator,
        first_seen_at=device.first_seen_at,
        last_seen_at=device.last_seen_at,
        trust_class=trust_class,
        trust_score=trust_score,
        linked_user_count=len(user_links),
        event_count=int(event_count),
        geo_trend=geo_trend,
    )


@router.post(
    "/explain/{score_id}",
    response_model=ShapExplanationOut,
    dependencies=[_any_role],
)
def explain_score(
    score_id: str,
    db: DbSession = Depends(deps.get_db),
    registry: Registry = Depends(deps.get_registry),
) -> ShapExplanationOut:
    """D4: on-demand SHAP explanation for a risk score (off hot path, analyst-only)."""
    try:
        return shap_explainer.explain_score(score_id, db, registry)
    except (ValueError, ImportError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post(
    "/cases/{case_id}/investigate",
    response_model=InvestigationResultOut,
    dependencies=[_any_role],
)
async def investigate_case(
    case_id: str, db: DbSession = Depends(deps.get_db)
) -> InvestigationResultOut:
    """D5: LLM investigation assistant — deterministic stub by default, Claude if configured."""
    try:
        cid = uuid.UUID(case_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid case_id")

    case = db.get(Case, cid)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")

    provider = investigation_llm.get_provider()
    return await provider.investigate(case_id, case, db)


@router.get("/policy", dependencies=[_any_role])
def get_policy(redis: Redis = Depends(deps.get_redis)) -> dict:
    return {"active_policy": active_policy(redis=redis)}


@router.put("/policy", dependencies=[_admin_only])
def put_policy(update: PolicyUpdate, redis: Redis = Depends(deps.get_redis)) -> dict:
    redis.set(POLICY_REDIS_KEY, update.model_dump_json())
    return {"active_policy": active_policy(redis=redis)}


def _case_out(case: Case, db: DbSession) -> CaseOut:
    score_id: str | None = None
    risk_band: str | None = None
    final_risk_score: float | None = None
    reason_codes: list[dict] | None = None
    amplifiers: list[dict] | None = None

    if case.transaction_id:
        risk_score_row = db.scalar(
            select(RiskScore)
            .where(RiskScore.entity_id == case.transaction_id, RiskScore.is_shadow.is_(False))
            .order_by(RiskScore.scored_at.desc())
        )
        if risk_score_row:
            score_id = str(risk_score_row.score_id)
            risk_band = risk_score_row.risk_band
            final_risk_score = (
                float(risk_score_row.final_risk_score)
                if risk_score_row.final_risk_score is not None
                else None
            )
        txn = db.get(Transaction, case.transaction_id)
        if txn and txn.decision_reason:
            reason_codes = txn.decision_reason.get("reason_codes")
            amplifiers = txn.decision_reason.get("amplifiers")

    updated_at = (case.resolved_at or case.created_at)
    return CaseOut(
        case_id=str(case.case_id),
        user_id=str(case.user_id) if case.user_id else None,
        transaction_id=str(case.transaction_id) if case.transaction_id else None,
        alert_type=case.alert_type,
        severity=case.severity,
        status=case.status,
        assigned_to=case.assigned_to,
        created_at=case.created_at.isoformat() if case.created_at else None,
        resolved_at=case.resolved_at.isoformat() if case.resolved_at else None,
        updated_at=updated_at.isoformat() if updated_at else None,
        score_id=score_id,
        risk_band=risk_band,
        final_risk_score=final_risk_score,
        reason_codes=reason_codes,
        amplifiers=amplifiers,
    )


@router.get("/cases", response_model=list[CaseOut], dependencies=[_any_role])
def list_cases(
    status: str | None = None,
    user_id: str | None = None,
    limit: int = Query(default=50, le=500),
    db: DbSession = Depends(deps.get_db),
) -> list[CaseOut]:
    stmt = select(Case).order_by(Case.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(Case.status == status)
    if user_id:
        stmt = stmt.where(Case.user_id == uuid.UUID(user_id))
    return [_case_out(c, db) for c in db.scalars(stmt).all()]


@router.patch("/cases/{case_id}", response_model=CaseOut, dependencies=[_any_role])
def patch_case(case_id: str, update: CaseUpdate, db: DbSession = Depends(deps.get_db)) -> CaseOut:
    try:
        case = case_mgmt.update_case(db, case_id, update)
    except ValueError:
        raise HTTPException(status_code=404, detail="case not found")
    return _case_out(case, db)


def _model_version_out(row: ModelRegistry) -> ModelVersionOut:
    return ModelVersionOut(
        model_id=str(row.model_id),
        version=row.version,
        stage=row.stage,
        model_type=row.model_type,
        metrics=row.metrics or {},
        artifact_uri=row.artifact_uri,
        deployed_at=row.deployed_at.isoformat() if row.deployed_at else None,
    )


def _models_by_name(db: DbSession, *, model_name: str | None = None) -> list[ModelOut]:
    stmt = select(ModelRegistry).order_by(ModelRegistry.deployed_at.desc())
    if model_name:
        stmt = stmt.where(ModelRegistry.model_name == model_name)
    grouped: dict[str, list[ModelVersionOut]] = {}
    for row in db.scalars(stmt).all():
        grouped.setdefault(row.model_name or "", []).append(_model_version_out(row))
    return [ModelOut(model_name=name, versions=versions) for name, versions in grouped.items()]


@router.get("/models", response_model=list[ModelOut], dependencies=[_any_role])
def list_models(db: DbSession = Depends(deps.get_db)) -> list[ModelOut]:
    return _models_by_name(db)


@router.get("/models/{model_name}", response_model=ModelOut, dependencies=[_any_role])
def get_model(model_name: str, db: DbSession = Depends(deps.get_db)) -> ModelOut:
    found = _models_by_name(db, model_name=model_name)
    if not found:
        raise HTTPException(status_code=404, detail="model not found")
    return found[0]


@router.post("/models/{model_name}/promote", response_model=ModelOut, dependencies=[_admin_only])
def promote_model(
    model_name: str,
    body: PromoteRequest,
    db: DbSession = Depends(deps.get_db),
    registry: Registry = Depends(deps.get_registry),
) -> ModelOut:
    try:
        promote.promote_to_production(model_name, body.version)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    registry.reload(model_name)
    return _models_by_name(db, model_name=model_name)[0]


@router.post("/models/{model_name}/rollback", response_model=ModelOut, dependencies=[_admin_only])
def rollback_model(
    model_name: str,
    body: RollbackRequest,
    db: DbSession = Depends(deps.get_db),
    registry: Registry = Depends(deps.get_registry),
) -> ModelOut:
    try:
        promote.rollback(model_name, body.version)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    registry.reload(model_name)
    return _models_by_name(db, model_name=model_name)[0]


@router.get("/drift", response_model=DriftReportOut, dependencies=[_any_role])
def get_drift(
    db: DbSession = Depends(deps.get_db), redis: Redis = Depends(deps.get_redis)
) -> DriftReportOut:
    # Read-only observability -- only the CLI/scheduled path (training.drift_monitor's
    # __main__) triggers retrains; a GET must never have that side effect.
    report = drift_monitor.run(db, policy=active_policy(redis=redis), trigger_retrain=False)
    return DriftReportOut(**report)


_RESET_TABLES = [
    "users", "accounts", "sessions", "login_events", "behavior_samples",
    "beneficiaries", "user_beneficiaries", "transactions",
    "risk_scores", "decisions", "auth_challenges",
    "cases", "audit_logs", "devices", "user_devices",
]


@router.post("/factory-reset", response_model=FactoryResetOut, dependencies=[_admin_only])
def factory_reset(db: DbSession = Depends(deps.get_db)) -> FactoryResetOut:
    """Wipe all banking user/session/behavioral data for a clean-slate demo.

    Keeps: model_registry (scoring stays live) and analysts (SOC logins preserved).
    After the wipe, sets system:seed_disabled in Redis so seed_demo.py skips
    user re-seeding on container restart — the next interaction must be Sign Up.
    """
    table_list = ", ".join(_RESET_TABLES)
    db.execute(text(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"))
    db.commit()
    redis_client.flushdb()
    redis_client.set(POLICY_REDIS_KEY, json.dumps(DEFAULT_POLICY))
    redis_client.set("system:seed_disabled", "1")
    return FactoryResetOut(status="ok", tables_truncated=_RESET_TABLES, redis="flushed")
