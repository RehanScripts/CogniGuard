"""Feature reader (Architecture §5.2, Implementation.md Phase 5).

Assembles the `FeatureBundle` for inference from Redis online features (written by the
Flink feature engine, `flink-jobs/sinks.py`) + the inline request payload. **Never**
touches PostgreSQL — CLAUDE.md §6 invariant: inference reads Redis only.

Redis key names here must match `flink-jobs/sinks.py` exactly (separate deployment
units, can't share imports).
"""

from __future__ import annotations

import datetime as dt
import math
import statistics

from redis import Redis

from ..schemas.behavior import BehaviorPayload
from ..schemas.features import (
    BehaviorFeatures,
    ContextFeatures,
    DeviceFeatures,
    FeatureBundle,
    FeatureReadContext,
    NetworkFeatures,
    TxnFeatures,
)
from ..utils.geo import geohash, haversine

EPS = 1e-9

# Feature-engineering heuristics (not decision thresholds/amplifiers — those live in
# policy per CLAUDE.md §6 invariant 6). No per-user hour-of-day profile is kept in
# Redis (Phase 4 schema), so "odd time" is a fixed late-night window.
ODD_TIME_HOURS = frozenset(range(0, 6))  # 00:00–05:59
HIGH_VELOCITY_1H = 5
HIGH_VELOCITY_24H = 20
NEW_PAYEE_RISK = 0.6


def _k_profile(uid: str) -> str:
    return f"user:{uid}:profile"


def _k_known_devices(uid: str) -> str:
    return f"user:{uid}:known_devices"


def _k_known_beneficiaries(uid: str) -> str:
    return f"user:{uid}:known_beneficiaries"


def _k_known_geos(uid: str) -> str:
    return f"user:{uid}:known_geos"


def _k_velocity(uid: str, window: str) -> str:
    return f"user:{uid}:velocity:{window}"


def _k_amount_sum(uid: str) -> str:
    return f"user:{uid}:amount_sum:24h"


def _k_device_trust(device_id: str) -> str:
    return f"device:{device_id}:trust"


def _parse_hour(ts: str) -> tuple[int, int]:
    """(hour, day-of-week) from an ISO8601 timestamp; falls back to "now" on parse failure."""
    try:
        parsed = dt.datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        parsed = dt.datetime.now(dt.timezone.utc)
    return parsed.hour, parsed.weekday()


def _behavior_from_payload(behavior: BehaviorPayload) -> BehaviorFeatures:
    """Fold the inline behavioral metrics — mobile sends pre-computed `derived_features`
    (edge extraction); web sends raw keystroke/mouse/touch blocks that we reduce here."""
    if behavior.derived_features:
        d = behavior.derived_features
        return BehaviorFeatures(
            typing_speed=d.get("typing_speed", 0.0),
            key_latency_avg=d.get("key_latency_avg", 0.0),
            typing_rhythm_std=d.get("typing_rhythm_std", 0.0),
            hold_time_avg=d.get("hold_time_avg", 0.0),
            swipe_velocity_norm=d.get("swipe_velocity_norm", 0.0),
            swipe_angle_dev=d.get("swipe_angle_dev", 0.0),
            touch_pressure_avg=d.get("touch_pressure_avg", 0.0),
            acceleration_variance=d.get("acceleration_variance", 0.0),
            mouse_velocity_mean=d.get("mouse_velocity_mean", 0.0),
        )

    typing_speed = key_latency_avg = typing_rhythm_std = hold_time_avg = 0.0
    if behavior.keystroke and behavior.keystroke.events:
        events = behavior.keystroke.events
        hold_time_avg = sum(e.up - e.down for e in events) / len(events)
        if len(events) > 1:
            duration_s = (events[-1].up - events[0].down) / 1000.0
            if duration_s > 0:
                typing_speed = len(events) / duration_s
            flights = [events[i].down - events[i - 1].up for i in range(1, len(events))]
            key_latency_avg = sum(flights) / len(flights)
            if len(flights) > 1:
                typing_rhythm_std = statistics.pstdev(flights)

    mouse_velocity_mean = 0.0
    if behavior.mouse and len(behavior.mouse.moves) > 1:
        moves = behavior.mouse.moves
        speeds = []
        for prev, cur in zip(moves, moves[1:]):
            dt_ms = cur.get("t", 0) - prev.get("t", 0)
            if dt_ms > 0:
                dist = math.hypot(cur.get("x", 0) - prev.get("x", 0), cur.get("y", 0) - prev.get("y", 0))
                speeds.append(dist / dt_ms)
        if speeds:
            mouse_velocity_mean = sum(speeds) / len(speeds)

    swipe_velocity_norm = swipe_angle_dev = 0.0
    if behavior.touch and behavior.touch.swipes:
        swipes = behavior.touch.swipes
        speeds = [math.hypot(s.get("vx", 0.0), s.get("vy", 0.0)) for s in swipes]
        swipe_velocity_norm = sum(speeds) / len(speeds)
        if len(swipes) > 1:
            angles = [math.atan2(s.get("vy", 0.0), s.get("vx", 0.0)) for s in swipes]
            swipe_angle_dev = statistics.pstdev(angles)

    return BehaviorFeatures(
        typing_speed=typing_speed,
        key_latency_avg=key_latency_avg,
        typing_rhythm_std=typing_rhythm_std,
        hold_time_avg=hold_time_avg,
        swipe_velocity_norm=swipe_velocity_norm,
        swipe_angle_dev=swipe_angle_dev,
        touch_pressure_avg=0.0,  # not captured by the raw web contract (mobile-only)
        acceleration_variance=0.0,  # not captured by the raw web contract (mobile-only)
        mouse_velocity_mean=mouse_velocity_mean,
    )


def read_bundle(user_id: str, payload: FeatureReadContext, *, redis: Redis) -> FeatureBundle:
    """Assemble a `FeatureBundle` from Redis online features + the inline payload.
    Reads Redis ONLY (no Postgres). Missing keys (cold-start) fall back to defaults
    that bias the decision layer toward `verify`, never `block` (CLAUDE.md §6.9)."""
    profile = redis.hgetall(_k_profile(user_id))
    cold_start = not profile

    device_id = payload.device_id
    is_new_device = True
    device_trust = 0.0
    if device_id:
        is_new_device = not redis.sismember(_k_known_devices(user_id), device_id)
        trust_raw = redis.get(_k_device_trust(device_id))
        device_trust = float(trust_raw) if trust_raw is not None else 0.0

    geo_distance_km = 0.0
    geo_change = False
    if payload.geo_lat is not None and payload.geo_lon is not None:
        current_geohash = geohash(payload.geo_lat, payload.geo_lon)
        geo_change = not redis.sismember(_k_known_geos(user_id), current_geohash)
        last_lat, last_lon = profile.get("last_geo_lat"), profile.get("last_geo_lon")
        if last_lat is not None and last_lon is not None:
            geo_distance_km = haversine(float(last_lat), float(last_lon), payload.geo_lat, payload.geo_lon)

    avg_amount_30d = float(profile.get("avg_amount_30d") or 0.0)
    std_amount_30d = float(profile.get("std_amount_30d") or 0.0)
    amount_zscore = 0.0
    if payload.amount > 0:
        amount_zscore = (payload.amount - avg_amount_30d) / max(std_amount_30d, EPS)

    velocity_1h = int(redis.get(_k_velocity(user_id, "1h")) or 0)
    velocity_24h = int(redis.get(_k_velocity(user_id, "24h")) or 0)
    amount_sum_24h = float(redis.get(_k_amount_sum(user_id)) or 0.0)
    high_velocity = velocity_1h >= HIGH_VELOCITY_1H or velocity_24h >= HIGH_VELOCITY_24H

    is_new_payee = False
    beneficiary_risk = 0.0
    if payload.beneficiary_id:
        is_new_payee = not redis.sismember(_k_known_beneficiaries(user_id), payload.beneficiary_id)
        beneficiary_risk = NEW_PAYEE_RISK if is_new_payee else 0.0

    hour, dow = _parse_hour(payload.behavior.ts)
    odd_time = hour in ODD_TIME_HOURS

    return FeatureBundle(
        user_id=user_id,
        behavior=_behavior_from_payload(payload.behavior),
        device=DeviceFeatures(
            device_trust=device_trust,
            is_new_device=is_new_device,
            is_rooted=payload.behavior.device.is_rooted or payload.behavior.device.is_emulator,
        ),
        network=NetworkFeatures(
            geo_distance_km=geo_distance_km,
            geo_change=geo_change,
            vpn=payload.vpn,
            asn=payload.asn,
        ),
        txn=TxnFeatures(
            amount=payload.amount,
            amount_zscore=amount_zscore,
            velocity_1h=velocity_1h,
            velocity_24h=velocity_24h,
            amount_sum_24h=amount_sum_24h,
            is_new_payee=is_new_payee,
            beneficiary_risk=beneficiary_risk,
            odd_time=odd_time,
            high_velocity=high_velocity,
        ),
        context=ContextFeatures(
            hour=hour,
            dow=dow,
            session_age_s=payload.behavior.context.session_age_s,
            pre_txn_dwell_ms=payload.behavior.context.pre_txn_dwell_ms,
            correction_rate=payload.behavior.context.correction_rate,
            behavior_score=0.0,  # Isolation Forest output, filled in by scoring (Phase 6)
        ),
        cold_start=cold_start,
    )
