"""Auth router (Implementation.md Phase 8) -- thin, delegates to `auth_flow`."""

from __future__ import annotations

import ipaddress
import uuid

import jwt as pyjwt
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis import Redis
from sqlalchemy.orm import Session as DbSession

from .. import deps
from ..models.session import Session as SessionModel
from ..schemas.auth import (
    ConsentRequest,
    EmailVerifyRequest,
    LoginRequest,
    NonceResponse,
    RegisterRequest,
    StepUpVerifyRequest,
)
from ..scoring.registry import Registry
from ..services import auth_flow
from ..utils import security

_opt_bearer = HTTPBearer(auto_error=False)

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
def register(
    req: RegisterRequest,
    background_tasks: BackgroundTasks,
    db: DbSession = Depends(deps.get_db),
    redis: Redis = Depends(deps.get_redis),
) -> JSONResponse:
    try:
        user, challenge_id = auth_flow.initiate_registration(db, req, redis, background_tasks)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=409)
    return JSONResponse(
        {
            "user_id": str(user.user_id),
            "challenge_id": challenge_id,
            "status": "pending_email_verify",
        },
        status_code=201,
    )


@router.post("/register/verify-email")
def verify_registration_email(
    req: EmailVerifyRequest,
    db: DbSession = Depends(deps.get_db),
    redis: Redis = Depends(deps.get_redis),
) -> JSONResponse:
    status_code, body = auth_flow.verify_registration_email(
        db, redis, req.challenge_id, req.otp_code
    )
    return JSONResponse(body, status_code=status_code)


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


@router.post("/logout", status_code=204)
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(_opt_bearer),
    db: DbSession = Depends(deps.get_db),
) -> None:
    """Revoke the current session JWT (adds jti to Redis denylist) and mark the
    Postgres session row as ended.  Idempotent — safe to call on an already-expired
    token (nothing to revoke, just returns 204)."""
    if credentials is None:
        return
    try:
        claims = security.decode_jwt(credentials.credentials)
    except pyjwt.PyJWTError:
        return  # already expired — denylist entry would outlive the token anyway
    jwt_id = claims.get("jti")
    if jwt_id:
        security.revoke(jwt_id)
    session_id_str = claims.get("session_id")
    if session_id_str:
        try:
            session = db.get(SessionModel, uuid.UUID(session_id_str))
            if session and session.status == "active":
                session.status = "ended"
                db.commit()
        except Exception:
            pass


@router.post("/step-up/verify")
def step_up_verify(
    req: StepUpVerifyRequest,
    background_tasks: BackgroundTasks,
    db: DbSession = Depends(deps.get_db),
    redis: Redis = Depends(deps.get_redis),
) -> JSONResponse:
    status_code, response = auth_flow.verify_step_up(
        db, redis, req, background_tasks=background_tasks
    )
    return JSONResponse(response.model_dump(), status_code=status_code)
