"""Payment router (Implementation.md Phase 8) -- thin, delegates to `payment_flow`."""

from __future__ import annotations

import ipaddress

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy.orm import Session as DbSession

from .. import deps
from ..models.session import Session as SessionModel
from ..models.user import User
from ..schemas.payment import PaymentScoreRequest
from ..scoring.registry import Registry
from ..services import payment_flow

router = APIRouter()


def _client_ip(request: Request) -> str:
    """`Session.ip_address`/hardening counters key off this -- fall back to a sentinel
    for hosts that aren't a parseable IP (see routers/auth.py's identical helper)."""
    host = request.client.host if request.client else None
    if not host:
        return "0.0.0.0"
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return "0.0.0.0"
    return host


def _client_asn(request: Request) -> int | None:
    raw = request.headers.get("X-Demo-Asn")
    return int(raw) if raw else None


@router.post("/score")
def score(
    req: PaymentScoreRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: DbSession = Depends(deps.get_db),
    redis: Redis = Depends(deps.get_redis),
    registry: Registry = Depends(deps.get_registry),
    current: tuple[User, SessionModel] = Depends(deps.get_current_user),
) -> JSONResponse:
    user, session = current
    status_code, response = payment_flow.score_payment(
        db,
        redis,
        registry,
        user,
        session,
        req,
        ip=_client_ip(request),
        asn=_client_asn(request),
        background_tasks=background_tasks,
    )
    return JSONResponse(response.model_dump(), status_code=status_code)
