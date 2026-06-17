"""Telemetry integrity verification (NFR-5, CLAUDE.md invariant 11): single-use nonce +
HMAC-SHA256 + monotonic seq + timestamp skew. Defeats capture-and-replay (RAT/MITM).

Implementation.md line 499 (verbatim): `key = sha256(jwt_secret+nonce)`,
`msg = nonce ‖ canonical(metrics) ‖ fingerprint ‖ ts`. `canonical(metrics)` isn't pinned
down anywhere else in the docs (the behavior-sdk that would need to mirror this is
Phase 10, not built yet) -- defined here, once, precisely: a sorted-key, no-whitespace
JSON dump of every `BehaviorPayload` field that isn't itself part of the signature
envelope (`nonce`/`seq`/`ts`/`integrity_sig`) or concatenated separately (`device`,
whose `fingerprint` is the one part of it bound into the message).

Seq monotonicity needs a persistent "last seq" the documented Redis key catalog
(Architecture §4.1) doesn't enumerate -- `seq:{binding}` is this module's addition
(same pattern as Phase 7's `policy:active`), keyed by whatever stable identity the
caller has at the time (device fingerprint pre-login, session_id once one exists).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import secrets

from redis import Redis

from ..config import settings
from ..redis_client import redis_client as _default_redis
from ..schemas.behavior import BehaviorPayload

IntegrityReason = str  # "NONCE_INVALID" | "SEQ_REPLAY" | "HMAC_MISMATCH" | "TIMESTAMP_SKEW"


def _k_nonce(nonce: str) -> str:
    return f"nonce:{nonce}"


def _k_seq(binding: str) -> str:
    return f"seq:{binding}"


def canonical_metrics(payload: BehaviorPayload) -> str:
    metrics = {
        "channel": payload.channel,
        "source": payload.source,
        "action": payload.action.model_dump(mode="json"),
        "keystroke": payload.keystroke.model_dump(mode="json") if payload.keystroke else None,
        "mouse": payload.mouse.model_dump(mode="json") if payload.mouse else None,
        "touch": payload.touch.model_dump(mode="json") if payload.touch else None,
        "derived_features": payload.derived_features,
        "context": payload.context.model_dump(mode="json"),
    }
    return json.dumps(metrics, sort_keys=True, separators=(",", ":"))


def compute_signature(payload: BehaviorPayload) -> str:
    key = hashlib.sha256((settings.jwt_secret + payload.nonce).encode()).digest()
    msg = (
        payload.nonce + canonical_metrics(payload) + payload.device.fingerprint + payload.ts
    ).encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def issue_nonce(user_id: str | None = None, *, redis: Redis = _default_redis) -> tuple[str, str]:
    nonce = secrets.token_urlsafe(16)
    expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=settings.nonce_ttl_s)
    redis.set(_k_nonce(nonce), json.dumps({"user_id": user_id}), ex=settings.nonce_ttl_s)
    return nonce, expires_at.isoformat()


def verify(
    payload: BehaviorPayload, *, seq_binding: str, redis: Redis = _default_redis
) -> tuple[bool, IntegrityReason | None]:
    """On success, consumes the nonce (DEL) and advances the seq floor for `seq_binding`.
    Order follows Implementation.md line 499 verbatim: nonce -> seq -> HMAC -> skew."""
    nonce_key = _k_nonce(payload.nonce)
    if not redis.exists(nonce_key):
        return False, "NONCE_INVALID"

    seq_key = _k_seq(seq_binding)
    last_seq = int(redis.get(seq_key) or 0)
    if payload.seq <= last_seq:
        return False, "SEQ_REPLAY"

    expected_sig = compute_signature(payload)
    if not hmac.compare_digest(expected_sig, payload.integrity_sig):
        return False, "HMAC_MISMATCH"

    try:
        ts = dt.datetime.fromisoformat(payload.ts)
    except ValueError:
        return False, "TIMESTAMP_SKEW"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    now = dt.datetime.now(dt.timezone.utc)
    if abs((now - ts).total_seconds()) > settings.integrity_skew_s:
        return False, "TIMESTAMP_SKEW"

    redis.delete(nonce_key)
    redis.set(seq_key, payload.seq, ex=settings.nonce_ttl_s * 10)
    return True, None
