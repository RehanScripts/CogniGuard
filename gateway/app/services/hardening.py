"""Track A: IP/device brute-force counters + escalation (CLAUDE.md "two-track lockout"
invariant -- lock the offending IP/device, NEVER the account). Counters/locks live in
Redis per Architecture §4.1: `fail:ip:{ip}` / `fail:device:{fp}` (TTL window),
`lock:ip:{ip}` / `lock:device:{fp}`, `bruteforce:asn:{asn}` (distributed detection).
Escalation thresholds come from the active policy's `hardening` block -- never
hardcoded (CLAUDE.md invariant 6).
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from redis import Redis
from sqlalchemy.orm import Session as DbSession

from ..redis_client import redis_client as _default_redis
from ..schemas.decision import Hardening
from . import audit

FAIL_WINDOW_S = 15 * 60  # rolling window failures are counted over
MAX_DELAY_S = 5  # cap the server-side backoff sleep for demo safety


def _k_fail_ip(ip: str) -> str:
    return f"fail:ip:{ip}"


def _k_fail_device(fp: str) -> str:
    return f"fail:device:{fp}"


def _k_lock_ip(ip: str) -> str:
    return f"lock:ip:{ip}"


def _k_lock_device(fp: str) -> str:
    return f"lock:device:{fp}"


def _k_bruteforce_asn(asn: int) -> str:
    return f"bruteforce:asn:{asn}"


def is_locked(ip: str, device_fp: str, *, redis: Redis = _default_redis) -> Hardening | None:
    ip_ttl = redis.ttl(_k_lock_ip(ip))
    if ip_ttl and ip_ttl > 0:
        return Hardening(action="LOCKOUT", scope="ip", retry_after_s=ip_ttl)
    device_ttl = redis.ttl(_k_lock_device(device_fp))
    if device_ttl and device_ttl > 0:
        return Hardening(action="LOCKOUT", scope="device", retry_after_s=device_ttl)
    return None


def register_failure(
    db: DbSession,
    ip: str,
    device_fp: str,
    asn: int | None,
    policy: Mapping[str, Any],
    *,
    redis: Redis = _default_redis,
) -> Hardening | None:
    hardening_policy = policy.get("hardening", {})
    delay_after = hardening_policy.get("delay_after", 3)
    captcha_after = hardening_policy.get("captcha_after", 4)
    lock_after = hardening_policy.get("lock_after", 5)
    lock_minutes = hardening_policy.get("lock_minutes", 15)

    ip_count = redis.incr(_k_fail_ip(ip))
    redis.expire(_k_fail_ip(ip), FAIL_WINDOW_S)
    device_count = redis.incr(_k_fail_device(device_fp))
    redis.expire(_k_fail_device(device_fp), FAIL_WINDOW_S)
    fail_count = max(ip_count, device_count)

    if asn is not None:
        asn_count = redis.incr(_k_bruteforce_asn(asn))
        redis.expire(_k_bruteforce_asn(asn), FAIL_WINDOW_S)
        if asn_count >= lock_after:
            audit.write_audit_log(
                db,
                actor_type="system",
                actor_id=str(asn),
                action="DISTRIBUTED_BRUTEFORCE_ALERT",
                metadata={"asn": asn, "count": asn_count},
            )

    if fail_count >= lock_after:
        lock_ttl = lock_minutes * 60
        if ip_count >= lock_after:
            redis.set(_k_lock_ip(ip), "1", ex=lock_ttl)
        if device_count >= lock_after:
            redis.set(_k_lock_device(device_fp), "1", ex=lock_ttl)
        scope = "ip" if ip_count >= lock_after else "device"
        return Hardening(action="LOCKOUT", scope=scope, retry_after_s=lock_ttl)

    if fail_count >= captcha_after:
        return Hardening(action="CAPTCHA", scope="ip", retry_after_s=0)

    if fail_count >= delay_after:
        backoff = min(2 ** (fail_count - delay_after), MAX_DELAY_S)
        time.sleep(backoff)
        return Hardening(action="DELAY", scope="ip", retry_after_s=backoff)

    return None


def reset(ip: str, device_fp: str, *, redis: Redis = _default_redis) -> None:
    redis.delete(_k_fail_ip(ip), _k_fail_device(device_fp))
