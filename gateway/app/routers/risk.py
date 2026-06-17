"""Risk router -- `GET /session/{id}` reads `session:risk:{id}` from Redis
(originated by Phase 8's auth_flow/payment_flow, Phase 9 continues writing the same
key). 404 if no scoring event has happened yet for that session.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from redis import Redis

from .. import deps

router = APIRouter()


@router.get("/session/{session_id}")
def get_session_risk(session_id: str, redis: Redis = Depends(deps.get_redis)) -> dict:
    raw = redis.get(f"session:risk:{session_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail="no risk score recorded for this session")
    return json.loads(raw)
