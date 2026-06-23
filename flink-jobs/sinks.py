"""Event → Redis online-feature updates + S3 raw mirror (Architecture §4.1).

This module is the transformation core of the feature engine. It is plain Python (no
Flink) so it can be unit-tested against a real Redis, and so the PyFlink job
(`feature_engine.py`) is a thin wrapper that just routes deserialized records here.

Windowing: velocity/amount-sum windows are enforced by Redis key TTLs (counter +
`EXPIRE ... NX`); 30-day profile stats are maintained incrementally (Welford) in the
profile hash. Per-user keying in Flink keeps these read-modify-write updates serialized.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import uuid

from windows import geohash, welford_std, welford_update

logger = logging.getLogger("cogniguard.feature_engine")

TTL_1H = 3600
TTL_24H = 86400


# --- key helpers ----------------------------------------------------------------
def k_profile(uid: str) -> str:
    return f"user:{uid}:profile"


def k_known_devices(uid: str) -> str:
    return f"user:{uid}:known_devices"


def k_known_benef(uid: str) -> str:
    return f"user:{uid}:known_beneficiaries"


def k_known_geos(uid: str) -> str:
    return f"user:{uid}:known_geos"


def k_velocity(uid: str, window: str) -> str:
    return f"user:{uid}:velocity:{window}"


def k_amount_sum(uid: str) -> str:
    return f"user:{uid}:amount_sum:24h"


def k_device_trust(device_id: str) -> str:
    return f"device:{device_id}:trust"


def k_behavior_baseline(uid: str) -> str:
    return f"behavior:{uid}:baseline"


BEHAVIOR_FEATURES = (
    "typing_speed",
    "key_latency_avg",
    "typing_rhythm_std",
    "hold_time_avg",
    "swipe_velocity_norm",
    "swipe_angle_dev",
    "touch_pressure_avg",
    "acceleration_variance",
    "mouse_velocity_mean",
)


# --- per-topic feature updates --------------------------------------------------
def update_from_login_event(redis, user_id: str, p: dict) -> None:
    profile: dict[str, str] = {"last_login_ts": str(p.get("ts", ""))}
    if p.get("device_id"):
        redis.sadd(k_known_devices(user_id), p["device_id"])
        profile["last_device_id"] = p["device_id"]
    lat, lon = p.get("geo_lat"), p.get("geo_lon")
    if lat is not None and lon is not None:
        gh = geohash(float(lat), float(lon))
        redis.sadd(k_known_geos(user_id), gh)
        profile["last_geo_lat"] = str(lat)
        profile["last_geo_lon"] = str(lon)
        profile["last_geohash"] = gh
        # baseline_geohash = first seen location (durable home base)
        if not redis.hexists(k_profile(user_id), "baseline_geohash"):
            profile["baseline_geohash"] = gh
    redis.hset(k_profile(user_id), mapping=profile)


def update_from_transaction_event(redis, user_id: str, p: dict) -> None:
    amount = float(p.get("amount", 0.0))

    # velocity counters (TTL-windowed; EXPIRE NX makes them fixed windows)
    for window, ttl in (("1h", TTL_1H), ("24h", TTL_24H)):
        key = k_velocity(user_id, window)
        redis.incr(key)
        redis.expire(key, ttl, nx=True)

    # 24h amount sum
    asum = k_amount_sum(user_id)
    redis.incrbyfloat(asum, amount)
    redis.expire(asum, TTL_24H, nx=True)

    # 30-day profile stats via Welford (count/mean/m2 stored in the profile hash)
    pkey = k_profile(user_id)
    cur = redis.hmget(pkey, "_amt_count", "_amt_mean", "_amt_m2")
    count = int(cur[0]) if cur[0] else 0
    mean = float(cur[1]) if cur[1] else 0.0
    m2 = float(cur[2]) if cur[2] else 0.0
    count, mean, m2 = welford_update(count, mean, m2, amount)
    redis.hset(
        pkey,
        mapping={
            "_amt_count": count,
            "_amt_mean": mean,
            "_amt_m2": m2,
            "avg_amount_30d": round(mean, 4),
            "std_amount_30d": round(welford_std(count, m2), 4),
            "txn_count_30d": count,
        },
    )

    if p.get("beneficiary_id"):
        redis.sadd(k_known_benef(user_id), p["beneficiary_id"])


def update_from_behavior_event(redis, user_id: str, p: dict) -> None:
    key = k_behavior_baseline(user_id)
    raw = redis.get(key)
    acc = json.loads(raw) if raw else {}
    baseline: dict[str, float] = {}
    for feat in BEHAVIOR_FEATURES:
        c, m, m2 = acc.get(feat, [0, 0.0, 0.0])
        c, m, m2 = welford_update(int(c), float(m), float(m2), float(p.get(feat, 0.0) or 0.0))
        acc[feat] = [c, m, m2]
        baseline[feat] = round(m, 6)
        baseline[f"{feat}_std"] = round(welford_std(c, m2), 6)
    acc["_baseline"] = baseline
    redis.set(key, json.dumps(acc))


def update_from_device_event(redis, device_id: str, p: dict) -> None:
    # Simple count-based trust that drops hard for rooted/emulated devices.
    key = k_device_trust(device_id)
    sightings = redis.incr(f"{key}:sightings")
    rooted = p.get("is_rooted") or p.get("is_emulator")
    trust = 0.0 if rooted else min(100.0, 50.0 + 5.0 * sightings)
    redis.set(key, round(trust, 2))


# --- S3 raw mirror --------------------------------------------------------------
def mirror_to_s3(s3, bucket: str, topic: str, p: dict) -> str:
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    key = f"raw/{topic}/dt={day}/{uuid.uuid4().hex}.json"
    s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(p).encode("utf-8"))
    return key


# --- dispatch -------------------------------------------------------------------
_KEY_FIELD = {
    "login_events": "user_id",
    "behavior_events": "user_id",
    "transaction_events": "user_id",
    "device_events": "device_id",
}


def process_record(redis, s3, bucket: str, topic: str, key: str, payload: dict) -> None:
    """Apply one event's feature updates to Redis and mirror it to S3. Never raises —
    a single bad record must not kill the stream."""
    try:
        if topic == "login_events":
            update_from_login_event(redis, key, payload)
        elif topic == "transaction_events":
            update_from_transaction_event(redis, key, payload)
        elif topic == "behavior_events":
            update_from_behavior_event(redis, key, payload)
        elif topic == "device_events":
            update_from_device_event(redis, key, payload)
    except Exception:  # noqa: BLE001
        logger.exception("redis feature update failed for topic=%s key=%s", topic, key)
    if s3 is not None:
        try:
            mirror_to_s3(s3, bucket, topic, payload)
        except Exception:  # noqa: BLE001
            logger.exception("s3 mirror failed for topic=%s", topic)
