"""Feature reader (Architecture §5.2, Implementation.md Phase 5).

Assembles the `FeatureBundle` for inference from Redis online features (written by the
Flink feature engine, `flink-jobs/sinks.py`) + the inline request payload. **Never**
touches PostgreSQL — CLAUDE.md §6 invariant: inference reads Redis only.

Redis key names here must match `flink-jobs/sinks.py` exactly (separate deployment
units, can't share imports).
"""

from __future__ import annotations

import datetime as dt
import json
import math
import statistics

from redis import Redis

from training.train_isolation_forest import BEHAVIOR_COLUMNS

from ..scoring import calibration, device_trust as _device_trust_engine, embedding_store, identity
from ..scoring.autoencoder import MIN_SEQ, N_FEATURES, SEQ_LEN
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

# AE rolling-window ring buffer (Implementation.md Phase 14) -- a capped Redis LIST per
# session, refreshed on every push so a session that's still active never expires mid-way.
SEQ_BUFFER_TTL_S = 24 * 3600

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


def _k_seq(session_id: str) -> str:
    return f"behavior:{session_id}:seq"


def _k_risk_baseline(uid: str) -> str:
    return f"user:{uid}:risk_baseline"


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
                dist = math.hypot(
                    cur.get("x", 0) - prev.get("x", 0), cur.get("y", 0) - prev.get("y", 0)
                )
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


def _has_calibration(user_id: str, *, redis: Redis) -> bool:
    """Whether any AE calibration (per-user or population) exists yet -- read-only,
    same key names `calibration.load_calibration` reads (Phase 13)."""
    return bool(redis.exists(calibration.user_calibration_key(user_id))) or bool(
        redis.exists(calibration.POPULATION_CALIBRATION_KEY)
    )


def _push_and_read_sequence(
    session_id: str, vector: list[float], *, redis: Redis
) -> tuple[list[list[float]], int]:
    """Push the current 9-dim behavior vector onto this session's capped ring buffer and
    read back the (left-padded) window. Returns (behavior_sequence, real_count); the
    caller derives the mask from real_count since padding is always at the front."""
    key = _k_seq(session_id)
    redis.rpush(key, json.dumps(vector))
    redis.ltrim(key, -SEQ_LEN, -1)
    redis.expire(key, SEQ_BUFFER_TTL_S)

    raw_rows = redis.lrange(key, 0, -1)
    real_rows = [json.loads(row) for row in raw_rows]
    real_count = len(real_rows)

    pad_count = max(0, SEQ_LEN - real_count)
    padded = [[0.0] * N_FEATURES for _ in range(pad_count)] + real_rows[-SEQ_LEN:]
    return padded, real_count


def _resolve_ae(
    payload: FeatureReadContext, behavior_features: BehaviorFeatures, *, user_id: str, redis: Redis
) -> tuple[list[list[float]] | None, list[bool] | None, float | None, bool]:
    """(behavior_sequence, behavior_sequence_mask, ae_recon_error, ae_cold_start).
    Web assembles the rolling window for Phase 15's server-side AE; mobile already
    carries its own device-computed reconstruction error (Implementation.md Phase 14)
    and never uses the server-side window for inference.

    Both channels gate AE-as-primary behind the **same** `MIN_SEQ` warm-up: the first
    few events of a session route to the Isolation Forest shadow score and bias to
    `verify`, never letting a sparse early window drive a `block` (CLAUDE.md invariant
    9). For mobile this matters because a single login event produces only a sparse
    on-device window (no swipe/touch/motion yet), whose raw reconstruction error sits
    far outside the dense population calibration and would otherwise saturate
    Behavior_Score to 1.0. The per-session ring buffer is tracked for mobile purely to
    count real rows; the assembled sequence is discarded (the device's `ae_recon_error`
    is the AE signal, calibrated server-side once warm)."""
    has_calibration = _has_calibration(user_id, redis=redis)

    if not payload.session_id:
        # No session to count real rows against -> cold-start, bias to verify (CLAUDE.md
        # §6.9). The live login/payment/behavior flows always pass a session_id; this
        # guards only direct/test callers that don't.
        return None, None, payload.behavior.ae_recon_error, True

    vector = [getattr(behavior_features, name) for name in BEHAVIOR_COLUMNS]
    behavior_sequence, real_count = _push_and_read_sequence(payload.session_id, vector, redis=redis)
    pad_count = SEQ_LEN - real_count
    behavior_sequence_mask = [False] * max(pad_count, 0) + [True] * min(real_count, SEQ_LEN)
    ae_cold_start = real_count < MIN_SEQ or not has_calibration

    if payload.behavior.channel == "mobile":
        # AE ran on-device; the server-side window above is only a row counter for the
        # MIN_SEQ warm-up, so hand back the device's recon error with no assembled
        # sequence (stack.py reads `ae_recon_error` directly for mobile).
        return None, None, payload.behavior.ae_recon_error, ae_cold_start

    return behavior_sequence, behavior_sequence_mask, None, ae_cold_start


def read_bundle(
    user_id: str,
    payload: FeatureReadContext,
    *,
    redis: Redis,
    device_trust_budgets: dict | None = None,
) -> FeatureBundle:
    """Assemble a `FeatureBundle` from Redis online features + the inline payload.
    Reads Redis ONLY (no Postgres). Missing keys (cold-start) fall back to defaults
    that bias the decision layer toward `verify`, never `block` (CLAUDE.md §6.9)."""
    profile = redis.hgetall(_k_profile(user_id))
    cold_start = not profile

    device_id = payload.device_id
    is_new_device = True
    _trust_raw: bytes | None = None
    if device_id:
        is_new_device = not redis.sismember(_k_known_devices(user_id), device_id)
        _trust_raw = redis.get(_k_device_trust(device_id))

    geo_distance_km = 0.0
    geo_change = False
    if payload.geo_lat is not None and payload.geo_lon is not None:
        current_geohash = geohash(payload.geo_lat, payload.geo_lon)
        geo_change = not redis.sismember(_k_known_geos(user_id), current_geohash)
        last_lat, last_lon = profile.get("last_geo_lat"), profile.get("last_geo_lon")
        if last_lat is not None and last_lon is not None:
            geo_distance_km = haversine(
                float(last_lat), float(last_lon), payload.geo_lat, payload.geo_lon
            )

    # Device trust: prefer the Redis-cached value written by a prior request.
    # On first encounter (cache miss) compute from signals already in hand and write
    # to Redis immediately so the next request is a fast cache hit (two small SETs,
    # only on new devices — well within latency budget).
    if _trust_raw is not None:
        device_trust = float(_trust_raw)
    elif device_id:
        _dt_result = _device_trust_engine.compute(
            is_rooted=payload.behavior.device.is_rooted,
            is_emulator=payload.behavior.device.is_emulator,
            is_new_device=is_new_device,
            geo_distance_km=geo_distance_km,
            hours_since_last_login=_device_trust_engine.hours_since(profile.get("last_login_ts")),
            budgets=device_trust_budgets,
        )
        device_trust = _dt_result.trust
        _device_trust_engine.persist(device_id, _dt_result, redis=redis)
    else:
        device_trust = 0.0

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

    behavior_features = _behavior_from_payload(payload.behavior)
    behavior_sequence, behavior_sequence_mask, ae_recon_error, ae_cold_start = _resolve_ae(
        payload, behavior_features, user_id=user_id, redis=redis
    )

    # Per-user identity baseline (Phase 20-22) -- written only by enrollment.finalize().
    # Its presence is what flips `enrolled` on and activates the identity Trust anchor.
    identity_raw = redis.get(identity.identity_baseline_key(user_id))
    identity_baseline = identity.parse_identity_baseline(identity_raw) if identity_raw else None

    # Per-user risk baseline for adaptive band thresholds (Phase B4).
    risk_baseline: dict | None = None
    _baseline_raw = redis.get(_k_risk_baseline(user_id))
    if _baseline_raw:
        try:
            risk_baseline = json.loads(_baseline_raw)
        except (TypeError, ValueError):
            pass

    # F4: Read cached encoder cosine similarity from previous clean session (background-written).
    embedding_sim = embedding_store.read_cached_sim(user_id, redis=redis)

    return FeatureBundle(
        user_id=user_id,
        behavior=behavior_features,
        behavior_sequence=behavior_sequence,
        behavior_sequence_mask=behavior_sequence_mask,
        ae_recon_error=ae_recon_error,
        ae_cold_start=ae_cold_start,
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
        identity_baseline=identity_baseline,
        enrolled=identity_baseline is not None,
        risk_baseline=risk_baseline,
        embedding_sim=embedding_sim,
    )


def snapshot_features(bundle: FeatureBundle, s3_client: object, session_id: str) -> None:
    """Write a FeatureBundle snapshot to S3 for offline training parity (Phase F2).

    Path: s3://features/{date}/{session_id}.json
    Only called on clean low-risk sessions (gated by caller; never step-up-passed).
    Silently no-ops on any S3 error so it never blocks the hot path.
    """
    from ..s3_client import get_s3
    from ..config import settings

    try:
        s3 = s3_client or get_s3()
        date_str = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        key = f"features/{date_str}/{session_id}.json"

        payload = json.dumps(
            {
                "session_id": session_id,
                "user_id": bundle.user_id,
                "snapshotted_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "behavior": (
                    bundle.behavior.model_dump()
                    if hasattr(bundle.behavior, "model_dump")
                    else vars(bundle.behavior)
                ),
                "device": (
                    bundle.device.model_dump()
                    if hasattr(bundle.device, "model_dump")
                    else vars(bundle.device)
                ),
                "network": (
                    bundle.network.model_dump()
                    if hasattr(bundle.network, "model_dump")
                    else vars(bundle.network)
                ),
                "txn": (
                    bundle.txn.model_dump()
                    if hasattr(bundle.txn, "model_dump")
                    else vars(bundle.txn)
                ),
                "context": (
                    bundle.context.model_dump()
                    if hasattr(bundle.context, "model_dump")
                    else vars(bundle.context)
                ),
                "cold_start": bundle.cold_start,
                "enrolled": bundle.enrolled,
                "ae_recon_error": bundle.ae_recon_error,
                "ae_cold_start": bundle.ae_cold_start,
            }
        )
        s3.put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=payload.encode(),
            ContentType="application/json",
        )
    except Exception:
        pass
