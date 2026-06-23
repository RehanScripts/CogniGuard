"""Enrollment router (Implementation.md Phase 21) -- thin, delegates to `enrollment`.

The demo path drives enrollment automatically over the first ~N login/app-open cycles
(`auth_flow.login`); this endpoint exposes the same per-cycle capture so enrollment can
be driven explicitly or tested in isolation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy.orm import Session as DbSession

from .. import deps
from ..schemas.enrollment import EnrollRequest
from ..services import enrollment

router = APIRouter()


@router.post("/")
def enroll(
    req: EnrollRequest,
    db: DbSession = Depends(deps.get_db),
    redis: Redis = Depends(deps.get_redis),
) -> JSONResponse:
    status_code, response = enrollment.enroll_user(db, redis, req)
    body = response.model_dump() if hasattr(response, "model_dump") else response
    return JSONResponse(body, status_code=status_code)
