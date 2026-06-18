"""Behavior router (Implementation.md Phase 9) -- thin, delegates to `behavior_flow`."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy.orm import Session as DbSession

from .. import deps
from ..models.session import Session as SessionModel
from ..models.user import User
from ..schemas.behavior import BehaviorPayload
from ..scoring.registry import Registry
from ..services import behavior_flow

router = APIRouter()


@router.post("/ingest")
def ingest(
    payload: BehaviorPayload,
    background_tasks: BackgroundTasks,
    db: DbSession = Depends(deps.get_db),
    redis: Redis = Depends(deps.get_redis),
    registry: Registry = Depends(deps.get_registry),
    current: tuple[User, SessionModel] = Depends(deps.get_current_user),
) -> JSONResponse:
    user, session = current
    status_code, response = behavior_flow.ingest(
        db, redis, registry, user, session, payload, background_tasks=background_tasks
    )
    return JSONResponse(response.model_dump(), status_code=status_code)
