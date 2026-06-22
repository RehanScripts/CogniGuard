"""Admin router (Implementation.md Phase 8 subset + Phase 9 `/cases` + Phase 12
`/models`+`/drift`): `/events`, `/users/{id}`, `/policy` GET/PUT, `/cases` GET/PATCH,
`/models` GET/promote/rollback, `/drift` GET. All behind `deps.require_admin`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from training import drift_monitor, promote

from .. import deps
from ..models.behavior import BehaviorSample
from ..models.device import UserDevice
from ..models.governance import Case, ModelRegistry
from ..models.scoring import Decision, RiskScore
from ..models.user import User
from ..scoring.registry import Registry
from ..schemas.admin import (
    CaseOut,
    CaseUpdate,
    DriftReportOut,
    EventOut,
    ModelOut,
    ModelVersionOut,
    PolicyUpdate,
    PromoteRequest,
    RollbackRequest,
    UserDetailOut,
)
from ..services import case_mgmt
from ..services.policy import POLICY_REDIS_KEY, active_policy

router = APIRouter(dependencies=[Depends(deps.require_admin)])


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


@router.get("/events", response_model=list[EventOut])
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


@router.get("/users/{user_id}", response_model=UserDetailOut)
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


@router.get("/policy")
def get_policy(redis: Redis = Depends(deps.get_redis)) -> dict:
    return {"active_policy": active_policy(redis=redis)}


@router.put("/policy")
def put_policy(update: PolicyUpdate, redis: Redis = Depends(deps.get_redis)) -> dict:
    redis.set(POLICY_REDIS_KEY, update.model_dump_json())
    return {"active_policy": active_policy(redis=redis)}


def _case_out(case: Case) -> CaseOut:
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
    )


@router.get("/cases", response_model=list[CaseOut])
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
    return [_case_out(c) for c in db.scalars(stmt).all()]


@router.patch("/cases/{case_id}", response_model=CaseOut)
def patch_case(case_id: str, update: CaseUpdate, db: DbSession = Depends(deps.get_db)) -> CaseOut:
    try:
        case = case_mgmt.update_case(db, case_id, update)
    except ValueError:
        raise HTTPException(status_code=404, detail="case not found")
    return _case_out(case)


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


@router.get("/models", response_model=list[ModelOut])
def list_models(db: DbSession = Depends(deps.get_db)) -> list[ModelOut]:
    return _models_by_name(db)


@router.get("/models/{model_name}", response_model=ModelOut)
def get_model(model_name: str, db: DbSession = Depends(deps.get_db)) -> ModelOut:
    found = _models_by_name(db, model_name=model_name)
    if not found:
        raise HTTPException(status_code=404, detail="model not found")
    return found[0]


@router.post("/models/{model_name}/promote", response_model=ModelOut)
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


@router.post("/models/{model_name}/rollback", response_model=ModelOut)
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


@router.get("/drift", response_model=DriftReportOut)
def get_drift(
    db: DbSession = Depends(deps.get_db), redis: Redis = Depends(deps.get_redis)
) -> DriftReportOut:
    # Read-only observability -- only the CLI/scheduled path (training.drift_monitor's
    # __main__) triggers retrains; a GET must never have that side effect.
    report = drift_monitor.run(db, policy=active_policy(redis=redis), trigger_retrain=False)
    return DriftReportOut(**report)
