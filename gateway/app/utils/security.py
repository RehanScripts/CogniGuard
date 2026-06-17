"""Argon2id password hashing + JWT session tokens + denylist (Implementation.md Phase 8).

`jwt:denylist:{jwt_id}` is the documented Redis key (Architecture §4.1) for terminated/
hijacked session revocation -- `deps.get_current_user` only needs to check this, not
re-read the session row from Postgres on every authenticated request.
"""

from __future__ import annotations

import datetime as dt
import uuid

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from ..config import settings
from ..redis_client import redis_client

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def _denylist_key(jwt_id: str) -> str:
    return f"jwt:denylist:{jwt_id}"


def issue_jwt(user_id: str, session_id: str) -> tuple[str, str]:
    jwt_id = str(uuid.uuid4())
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(user_id),
        "session_id": str(session_id),
        "jti": jwt_id,
        "iat": now,
        "exp": now + dt.timedelta(minutes=settings.jwt_ttl_minutes),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)
    return token, jwt_id


def decode_jwt(token: str) -> dict:
    """Raises jwt.PyJWTError on bad signature/expiry -- callers decide how to respond."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])


def revoke(jwt_id: str) -> None:
    redis_client.set(_denylist_key(jwt_id), "1", ex=settings.jwt_ttl_minutes * 60)


def is_revoked(jwt_id: str) -> bool:
    return bool(redis_client.exists(_denylist_key(jwt_id)))
