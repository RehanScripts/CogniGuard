"""Auth router (Implementation.md Phase 8) -- thin, delegates to `auth_flow`."""

from __future__ import annotations

import ipaddress

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy.orm import Session as DbSession

from .. import deps
from ..schemas.auth import (
    ConsentRequest,
    LoginRequest,
    NonceResponse,
    RegisterRequest,
    StepUpVerifyRequest,
)
from ..scoring.registry import Registry
from ..services import auth_flow

router = APIRouter()


def _client_ip(request: Request) -> str:
    """`Session.ip_address` is a Postgres INET column -- fall back to a sentinel for
    hosts that aren't a parseable IP (e.g. a reverse-proxy misconfiguration, or
    TestClient's default "testclient")."""
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


@router.get("/nonce", response_model=NonceResponse)
def get_nonce(redis: Redis = Depends(deps.get_redis)) -> NonceResponse:
    return auth_flow.issue_nonce_for(redis=redis)


@router.post("/register")
def register(req: RegisterRequest, db: DbSession = Depends(deps.get_db)) -> JSONResponse:
    try:
        user = auth_flow.register(db, req)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=409)
    return JSONResponse({"user_id": str(user.user_id), "status": "created"}, status_code=201)


@router.post("/consent")
def consent(req: ConsentRequest, db: DbSession = Depends(deps.get_db)) -> JSONResponse:
    try:
        user = auth_flow.consent_action(db, req)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=404)
    return JSONResponse({"user_id": str(user.user_id), "consent_status": user.consent_status})


@router.post("/login")
def login(
    req: LoginRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: DbSession = Depends(deps.get_db),
    redis: Redis = Depends(deps.get_redis),
    registry: Registry = Depends(deps.get_registry),
) -> JSONResponse:
    status_code, response = auth_flow.login(
        db,
        redis,
        registry,
        req,
        ip=_client_ip(request),
        asn=_client_asn(request),
        background_tasks=background_tasks,
    )
    return JSONResponse(response.model_dump(), status_code=status_code)


@router.post("/step-up/verify")
def step_up_verify(
    req: StepUpVerifyRequest,
    db: DbSession = Depends(deps.get_db),
    redis: Redis = Depends(deps.get_redis),
) -> JSONResponse:
    status_code, response = auth_flow.verify_step_up(db, redis, req)
    return JSONResponse(response.model_dump(), status_code=status_code)
