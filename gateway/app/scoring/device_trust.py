"""Device Trust Engine (UPGRADE_PLAN.md Phase B1).

Computes device_trust ∈ [0, 100] and device_class from device and session-context
signals that are already available in the hot-path feature reader (no extra Redis
reads beyond what feature_reader.read_bundle already fetches).

Pure functions — no I/O.  The feature reader calls compute() inline so the current
request sees a real trust value instead of the 0.0 default; a background task then
calls persist() to write the result to device:{device_id}:trust (TTL 7 days) so
subsequent requests find it cached per the "inference reads Redis only" rule.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Literal

from redis import Redis

DeviceClass = Literal["trusted", "known", "new", "suspicious"]

# Default trust budgets — mirrors policy.py's "device_trust" dict so tests and
# callers that don't pass policy still get sensible values (NFR-4 fallback).
_BUDGET_DEFAULTS: dict[str, float] = {
    "rooted_ceiling": 10.0,
    "base_new": 35.0,
    "base_known": 75.0,
    "penalty_impossible_travel": 40.0,
    "bonus_biometric": 15.0,
    "impossible_travel_kmh": 800.0,
}
TRUST_TTL_S = 7 * 24 * 3600     # cache the computed trust for 7 days

_DEVICE_TRUST_KEY_PREFIX = "device:"


def _k_device_trust(device_id: str) -> str:
    return f"{_DEVICE_TRUST_KEY_PREFIX}{device_id}:trust"


def _k_device_class(device_id: str) -> str:
    return f"{_DEVICE_TRUST_KEY_PREFIX}{device_id}:class"


@dataclass(frozen=True)
class DeviceTrustResult:
    trust: float          # 0..100
    device_class: DeviceClass
    signals: dict[str, bool | float] = field(default_factory=dict)


def compute(
    *,
    is_rooted: bool,
    is_emulator: bool,
    is_new_device: bool,
    geo_distance_km: float,
    hours_since_last_login: float | None,
    biometric_bound: bool = False,
    budgets: dict | None = None,
) -> DeviceTrustResult:
    """Compute device trust from signals already available in the feature reader.

    Args:
        is_rooted / is_emulator: from DevicePayload fields.
        is_new_device: True when device fingerprint is absent from
            user:{uid}:known_devices (already checked by feature_reader).
        geo_distance_km: haversine distance from last known location (0 when
            no prior location recorded — treated as no penalty).
        hours_since_last_login: elapsed hours since last_login_ts in the user
            profile; None when no prior login exists (new user) — impossible
            travel check is skipped.
        biometric_bound: True when the device has a registered biometric key
            (Phase C wires this; defaults to False until then).
        budgets: policy["device_trust"] dict — overrides default constants;
            falls back to _BUDGET_DEFAULTS for any missing key (NFR-4).
    """
    b: dict[str, float] = {**_BUDGET_DEFAULTS, **(budgets or {})}

    signals: dict[str, bool | float] = {
        "is_rooted": is_rooted,
        "is_emulator": is_emulator,
        "is_new_device": is_new_device,
        "geo_distance_km": geo_distance_km,
        "biometric_bound": biometric_bound,
        "impossible_travel": False,
    }

    if is_rooted or is_emulator:
        return DeviceTrustResult(
            trust=b["rooted_ceiling"],
            device_class="suspicious",
            signals=signals,
        )

    trust = b["base_new"] if is_new_device else b["base_known"]

    if (
        hours_since_last_login is not None
        and hours_since_last_login > 0
        and geo_distance_km > 0
        and (geo_distance_km / hours_since_last_login) > b["impossible_travel_kmh"]
    ):
        trust -= b["penalty_impossible_travel"]
        signals["impossible_travel"] = True

    if biometric_bound:
        trust = min(100.0, trust + b["bonus_biometric"])

    trust = round(max(0.0, min(100.0, trust)), 1)

    if trust >= 80.0:
        device_class: DeviceClass = "trusted"
    elif trust >= 50.0:
        device_class = "known"
    elif trust >= 20.0:
        device_class = "new"
    else:
        device_class = "suspicious"

    return DeviceTrustResult(trust=trust, device_class=device_class, signals=signals)


def hours_since(ts_str: str | bytes | None) -> float | None:
    """Parse an ISO-8601 timestamp string from the user profile hash and return
    how many hours have elapsed since then.  Returns None on any parse failure
    so callers skip the impossible-travel check rather than crashing."""
    if not ts_str:
        return None
    try:
        s = ts_str.decode() if isinstance(ts_str, bytes) else str(ts_str)
        parsed = dt.datetime.fromisoformat(s)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        delta = dt.datetime.now(dt.timezone.utc) - parsed
        return delta.total_seconds() / 3600.0
    except (ValueError, TypeError, AttributeError):
        return None


def persist(device_id: str, result: DeviceTrustResult, *, redis: Redis) -> None:
    """Write the computed trust + class to Redis (background task, off hot path)."""
    redis.set(_k_device_trust(device_id), str(result.trust), ex=TRUST_TTL_S)
    redis.set(
        _k_device_class(device_id),
        json.dumps({"class": result.device_class, "signals": result.signals}),
        ex=TRUST_TTL_S,
    )
