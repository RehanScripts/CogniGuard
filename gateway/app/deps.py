"""FastAPI dependency injection: DB/Redis/Registry handles + JWT auth
(Implementation.md Phase 8). `get_current_user` is denylist-only, no Postgres
read for the revocation check itself -- `jwt:denylist:{jwt_id}` is the documented
revocation mechanism (Architecture §4.1: "terminated/hijacked session revocation"),
so a valid signature + absent denylist entry is sufficient; the one Postgres read here
is to hand callers an actual `Session`/`User` row, not just bare ids.
"""

from __future__ import annotations

import uuid

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis import Redis
from sqlalchemy.orm import Session as DbSession

from .db import get_db
from .models.analyst import Analyst
from .models.session import Session as SessionModel
from .models.user import User
from .redis_client import redis_client
from .scoring.registry import Registry
from .utils import security

_bearer = HTTPBearer(auto_error=True)


def get_redis() -> Redis:
    return redis_client


def get_registry(request: Request) -> Registry:
    return request.app.state.registry


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: DbSession = Depends(get_db),
) -> tuple[User, SessionModel]:
    try:
        claims = security.decode_jwt(credentials.credentials)
    except pyjwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token"
        )

    jwt_id = claims.get("jti")
    if not jwt_id or security.is_revoked(jwt_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session revoked")

    try:
        session_id = uuid.UUID(claims["session_id"])
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="malformed token claims"
        )

    session = db.get(SessionModel, session_id)
    if session is None or session.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session not active")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")

    return user, session


def get_current_analyst(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: DbSession = Depends(get_db),
) -> Analyst:
    """Decodes the admin-track JWT (`kind: admin`, issued by `issue_admin_jwt`) --
    a separate token track from `get_current_user` so a customer session can never
    satisfy an admin/analyst endpoint (Phase 30, CLAUDE.md §8)."""
    try:
        claims = security.decode_jwt(credentials.credentials)
    except pyjwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token"
        )

    if claims.get("kind") != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not an admin token")

    jwt_id = claims.get("jti")
    if not jwt_id or security.is_revoked(jwt_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session revoked")

    try:
        analyst_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="malformed token claims"
        )

    analyst = db.get(Analyst, analyst_id)
    if analyst is None or analyst.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="analyst not active")

    return analyst


def require_role(*roles: str):
    """Dependency factory -- `Depends(require_role("admin"))` for admin-only routes,
    `Depends(require_role("admin", "analyst"))` for routes either role may use."""

    def _check(analyst: Analyst = Depends(get_current_analyst)) -> Analyst:
        if analyst.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role")
        return analyst

    return _check
