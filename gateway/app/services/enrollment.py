"""Data-driven per-user enrollment (Implementation.md Phase 21).

Rehan and Ojas are ordinary registered users; there is **no seeding or hardcoding** of
behavioral baselines. Each completes ~`MIN_ENROLL_SESSIONS` genuine login/app-open
cycles, and this service computes the two durable identity artifacts entirely from that
captured data:

- `behavior:{uid}:identity_baseline` -- per-dim median/MAD over the 9 BehaviorFeatures
  dims **and** the identity-distance calibration fit from the user's own self-distances.
- `behavior:{uid}:ae_calib` -- the per-user AE calibration (the long-defined-but-never-
  written key `calibration.user_calibration_key`), fit from the reconstruction errors
  observed across this user's enrollment windows. Written only when enough real recon
  errors were captured (mobile carries one per cycle; the population fallback otherwise
  stays in force -- never a per-user fabrication).

`record()` is called once per genuine login/app-open while the user is not yet enrolled;
on the cycle that reaches `required` it auto-`finalize()`s. Everything is derived from the
buffered sessions -- no parameter is ever read from a constant as a baseline.
"""

from __future__ import annotations

import datetime as dt
import json
import statistics
from typing import Sequence

from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from training.train_isolation_forest import BEHAVIOR_COLUMNS

from ..models.user import User
from ..schemas.enrollment import EnrollRequest, EnrollmentProgress, EnrollResponse
from ..scoring import calibration, identity
from ..scoring.calibration import CalibrationParams
from .policy import active_policy

# Buffer + finalized-baseline both expire well after a demo window; the buffer is cleared
# on finalize anyway.
ENROLL_BUFFER_TTL_S = 30 * 24 * 3600
N_FEATURES = len(BEHAVIOR_COLUMNS)
# Minimum real recon errors before fitting a *per-user* ae_calib; below this we keep the
# population calibration rather than fabricate one from too little data.
MIN_AE_SAMPLES = 5


def _enroll_buffer_key(user_id: str) -> str:
    return f"behavior:{user_id}:enroll"


def min_sessions(policy: dict | None = None, *, redis: Redis | None = None) -> int:
    pol = policy if policy is not None else active_policy(redis=redis)
    return int(pol.get("enrollment", {}).get("min_sessions", 10))


def is_enrolled(user_id: str, *, redis: Redis) -> bool:
    """A finalized identity baseline exists -> the identity gate is active for this user."""
    return bool(redis.exists(identity.identity_baseline_key(user_id)))


def progress(user_id: str, *, required: int, redis: Redis) -> EnrollmentProgress:
    if is_enrolled(user_id, redis=redis):
        return EnrollmentProgress(collected=required, required=required, complete=True)
    collected = int(redis.llen(_enroll_buffer_key(user_id)))
    return EnrollmentProgress(collected=min(collected, required), required=required, complete=False)


def record(
    user_id: str,
    behavior_vector: Sequence[float],
    ae_recon_error: float | None,
    *,
    required: int,
    redis: Redis,
) -> EnrollmentProgress:
    """Append one genuine session's 9-dim vector (+ optional AE recon error) to the
    enrollment buffer; auto-finalize on the cycle that reaches `required`. No-op once the
    user is already enrolled."""
    if is_enrolled(user_id, redis=redis):
        return EnrollmentProgress(collected=required, required=required, complete=True)

    key = _enroll_buffer_key(user_id)
    redis.rpush(
        key,
        json.dumps({"v": [float(x) for x in behavior_vector], "ae": ae_recon_error}),
    )
    redis.ltrim(key, -required, -1)  # keep at most `required` most-recent genuine sessions
    redis.expire(key, ENROLL_BUFFER_TTL_S)

    collected = int(redis.llen(key))
    if collected >= required:
        finalize(user_id, required=required, redis=redis)
        return EnrollmentProgress(
            collected=required, required=required, complete=True, just_finalized=True
        )
    return EnrollmentProgress(collected=collected, required=required, complete=False)


def _read_buffer(user_id: str, *, redis: Redis) -> tuple[list[list[float]], list[float]]:
    rows = redis.lrange(_enroll_buffer_key(user_id), 0, -1)
    vectors: list[list[float]] = []
    ae_errors: list[float] = []
    for raw in rows:
        try:
            obj = json.loads(raw)
        except (TypeError, ValueError):
            continue
        vec = obj.get("v")
        if isinstance(vec, list) and len(vec) == N_FEATURES:
            vectors.append([float(x) for x in vec])
        ae = obj.get("ae")
        if ae is not None:
            ae_errors.append(float(ae))
    return vectors, ae_errors


def _fit_baseline_stats(vectors: list[list[float]]) -> dict[str, tuple[float, float]]:
    """Per-dim (median, MAD) over the enrollment vectors -- robust to the handful of noisy
    live samples (median/MAD rather than mean/std)."""
    stats: dict[str, tuple[float, float]] = {}
    for i, name in enumerate(BEHAVIOR_COLUMNS):
        col = [v[i] for v in vectors]
        median = statistics.median(col)
        mad = statistics.median([abs(x - median) for x in col])
        stats[name] = (median, mad)
    return stats


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """Nearest-rank percentile over an already-sorted list."""
    if not sorted_vals:
        return 0.0
    n = len(sorted_vals)
    idx = max(0, min(n - 1, int(-(-pct * n // 100)) - 1))  # ceil(pct/100 * n) - 1
    return sorted_vals[idx]


def _fit_ae_calibration(errors: list[float]) -> CalibrationParams:
    """Per-user AE calibration from collected recon errors -- mirrors
    `training.train_lstm_autoencoder.fit_calibration` (median/MAD + 95th-percentile
    threshold) with stdlib statistics, no TF/numpy in the gateway."""
    median = statistics.median(errors)
    mad = statistics.median([abs(e - median) for e in errors]) * identity.MAD_TO_STD
    threshold = _percentile(sorted(errors), 95.0)
    scale = max(mad, calibration.EPS)
    return CalibrationParams(scale=scale, threshold=threshold, temperature=1.0)


def finalize(user_id: str, *, required: int, redis: Redis) -> bool:
    """Compute + persist both identity artifacts from the buffered sessions, then clear
    the buffer. Returns False (no-op) if there is nothing usable to finalize from."""
    vectors, ae_errors = _read_buffer(user_id, redis=redis)
    if not vectors:
        return False

    stats = _fit_baseline_stats(vectors)
    probe = identity.IdentityBaseline(
        stats=stats,
        distance_calib=calibration.default_calibration(),
        count=len(vectors),
        enrolled_at="",
    )
    self_distances = [identity.identity_distance(v, probe) for v in vectors]
    distance_calib = identity.fit_distance_calibration(self_distances)

    baseline_json = identity.build_identity_baseline(
        stats,
        distance_calib,
        count=len(vectors),
        enrolled_at=dt.datetime.now(dt.timezone.utc).isoformat(),
    )
    redis.set(
        identity.identity_baseline_key(user_id),
        json.dumps(baseline_json),
        ex=ENROLL_BUFFER_TTL_S,
    )

    # Per-user AE calibration only when enough real recon errors were captured (mobile);
    # otherwise the population fallback stays -- never a per-user fabrication.
    if len(ae_errors) >= MIN_AE_SAMPLES:
        ae_calib = _fit_ae_calibration(ae_errors)
        redis.set(
            calibration.user_calibration_key(user_id),
            json.dumps(
                {
                    "scale": ae_calib.scale,
                    "threshold": ae_calib.threshold,
                    "temperature": ae_calib.temperature,
                }
            ),
            ex=ENROLL_BUFFER_TTL_S,
        )

    redis.delete(_enroll_buffer_key(user_id))
    return True


def enroll_user(
    db: DbSession, redis: Redis, req: EnrollRequest
) -> tuple[int, EnrollResponse | dict]:
    """Standalone `POST /enroll` orchestration -- resolve the user, record one captured
    session, return progress. Same logic the login path drives automatically per cycle."""
    user = db.scalar(select(User).where(User.customer_ref == req.username))
    if user is None:
        return 404, {"detail": f"unknown username {req.username!r}"}
    required = min_sessions(redis=redis)
    prog = record(
        str(user.user_id),
        req.behavior_vector,
        req.ae_recon_error,
        required=required,
        redis=redis,
    )
    return 200, EnrollResponse(user_id=str(user.user_id), progress=prog)
