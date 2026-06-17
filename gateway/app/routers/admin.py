"""Admin router (Implementation.md Phase 8 subset): `/events`, `/users/{id}`, `/policy`
GET/PUT. `/cases` and `/models/.../promote`+`/retrain` need Phase 9's `case_mgmt.py` and
Phase 12's governance service, which don't exist yet -- not built here (see
PROGRESS.md gotcha). All behind `deps.require_admin`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .. import deps
from ..models.device import UserDevice
from ..models.scoring import Decision, RiskScore
from ..models.user import User
from ..schemas.admin import EventOut, PolicyUpdate, UserDetailOut
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
    )


@router.get("/events", response_model=list[EventOut])
def list_events(
    band: str | None = None,
    user_id: str | None = None,
    entity_type: str | None = None,
    limit: int = Query(default=50, le=500),
    db: DbSession = Depends(deps.get_db),
) -> list[EventOut]:
    stmt = select(RiskScore).order_by(RiskScore.scored_at.desc()).limit(limit)
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
        .where(RiskScore.user_id == uid)
        .order_by(RiskScore.scored_at.desc())
        .limit(20)
    ).all()

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
    )


@router.get("/policy")
def get_policy(redis: Redis = Depends(deps.get_redis)) -> dict:
    return {"active_policy": active_policy(redis=redis)}


@router.put("/policy")
def put_policy(update: PolicyUpdate, redis: Redis = Depends(deps.get_redis)) -> dict:
    redis.set(POLICY_REDIS_KEY, update.model_dump_json())
    return {"active_policy": active_policy(redis=redis)}
