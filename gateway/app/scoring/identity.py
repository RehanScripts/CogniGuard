"""Per-user identity verification scorer (Implementation.md Phase 20).

Turns CogniGuard from a *global* genuine-human anomaly detector into a *per-user*
identity **verifier**: it measures how far the live 9-dim behavior vector sits from the
*claimed* user's own enrolled baseline (robust per-feature z over median/MAD), calibrates
that distance to a [0,1] identity anomaly through the shared calibration logistic, and
folds the resulting behavior-match into an identity-gated Trust Score.

This is the signal that separates two genuine humans (Rehan vs Ojas) -- something the
global LSTM Autoencoder cannot do, since it reconstructs *every* genuine human well. The
AE's genuineness score stays fully active as the *coherence* term in the Trust Score (and
still feeds XGBoost on the payment path): identity is added **alongside** the AE, never
instead of it (CLAUDE.md invariant 5 -- AE stays primary/active). It is also strictly
**verification, not identification** -- we only ever load the claimed username's baseline
and ask "is this that enrolled human?", never "who is this?".

Pure functions + frozen dataclasses, mirroring `isolation_forest.py`'s shape and reusing
`scoring/calibration.py`'s logistic. No I/O here -- the baseline JSON is loaded by
`feature_reader` and parsed via `parse_identity_baseline`; it is written only by the
data-driven enrollment service (`services/enrollment.py`), never seeded/hardcoded.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from training.train_isolation_forest import BEHAVIOR_COLUMNS

from . import calibration
from .calibration import CalibrationParams

EPS = 1e-9
MAD_TO_STD = 1.4826  # MAD -> std consistency constant for a normal distribution


def identity_baseline_key(user_id: str) -> str:
    return f"behavior:{user_id}:identity_baseline"


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass(frozen=True)
class IdentityBaseline:
    """A user's enrolled identity profile (written by `enrollment.finalize()`).

    `stats` maps each `BehaviorFeatures` dim name -> (median, MAD) over the user's own
    enrollment sessions; `distance_calib` is the identity-distance calibration fit from
    that same user's genuine self-distances (so a genuine login calibrates below 0.5 and
    an impostor above)."""

    stats: dict[str, tuple[float, float]]
    distance_calib: CalibrationParams
    count: int
    enrolled_at: str


def build_identity_baseline(
    stats: Mapping[str, tuple[float, float]],
    distance_calib: CalibrationParams,
    *,
    count: int,
    enrolled_at: str,
) -> dict[str, Any]:
    """JSON-able dict for the `behavior:{uid}:identity_baseline` Redis key. The single
    source of the on-the-wire shape `parse_identity_baseline` reads back."""
    return {
        "stats": {name: {"median": m, "mad": d} for name, (m, d) in stats.items()},
        "distance_calib": {
            "scale": distance_calib.scale,
            "threshold": distance_calib.threshold,
            "temperature": distance_calib.temperature,
        },
        "count": count,
        "enrolled_at": enrolled_at,
    }


def parse_identity_baseline(raw: str | bytes) -> IdentityBaseline | None:
    """Parse the Redis JSON written by `enrollment.finalize()`. Returns None on any
    malformed/empty blob (treated as not-yet-enrolled / cold-start, never an error)."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    raw_stats = data.get("stats")
    if not isinstance(raw_stats, dict) or not raw_stats:
        return None
    stats: dict[str, tuple[float, float]] = {}
    for name, entry in raw_stats.items():
        if isinstance(entry, dict) and "median" in entry and "mad" in entry:
            stats[name] = (float(entry["median"]), float(entry["mad"]))
    if not stats:
        return None
    calib_raw = data.get("distance_calib", {})
    distance_calib = CalibrationParams(
        scale=float(calib_raw.get("scale", 1.0)),
        threshold=float(calib_raw.get("threshold", 0.5)),
        temperature=float(calib_raw.get("temperature", 1.0)),
    )
    return IdentityBaseline(
        stats=stats,
        distance_calib=distance_calib,
        count=int(data.get("count", 0)),
        enrolled_at=str(data.get("enrolled_at", "")),
    )


def identity_distance(vector: Sequence[float], baseline: IdentityBaseline) -> float:
    """RMS robust-z distance of the live 9-dim vector from the enrolled baseline.

    Robust-z (median/MAD) rather than Mahalanobis because live enrollment yields few,
    noisy samples -- MAD is outlier-resistant and needs no stable covariance matrix. Only
    dims the baseline actually carries are scored (a web-enrolled user has 0/0 stats for
    the mobile-only touch/accel dims; the live web vector is 0 there too, so they
    contribute ~0 and don't distort the distance)."""
    squares: list[float] = []
    for name, x in zip(BEHAVIOR_COLUMNS, vector):
        stat = baseline.stats.get(name)
        if stat is None:
            continue
        median, mad = stat
        z = (x - median) / (MAD_TO_STD * mad + EPS)
        squares.append(z * z)
    if not squares:
        return 0.0
    return math.sqrt(sum(squares) / len(squares))


def identity_anomaly(vector: Sequence[float], baseline: IdentityBaseline) -> float:
    """Calibrated identity anomaly [0,1]: 0 == matches the enrolled user, 1 == far from
    them. Reuses the shared calibration logistic via `calibrate_distance`."""
    distance = identity_distance(vector, baseline)
    return calibration.calibrate_distance(distance, baseline.distance_calib)


def behavior_match_score(vector: Sequence[float], baseline: IdentityBaseline) -> float:
    """0..100 display score -- how well the live behavior matches the enrolled user
    (100 == perfect match). The PRIMARY identity signal that separates Rehan from Ojas."""
    return round(100.0 * (1.0 - identity_anomaly(vector, baseline)), 1)


def env_consistency(
    *, geo_change: bool, new_device: bool, vpn: bool, weights: Mapping[str, float]
) -> float:
    """0..100 environment-consistency score; each anomalous context flag subtracts its
    policy-configured penalty weight. Weights from policy (CLAUDE.md invariant 6)."""
    penalty = (
        weights.get("geo_change", 0.0) * float(geo_change)
        + weights.get("new_device", 0.0) * float(new_device)
        + weights.get("vpn", 0.0) * float(vpn)
    )
    return _clamp(100.0 - 100.0 * penalty, 0.0, 100.0)


@dataclass(frozen=True)
class TrustComponents:
    behavior_match: float | None  # None on cold-start (no enrolled baseline yet)
    genuineness: float
    device_trust: float
    env_consistency: float
    support: float
    trust_score: float
    identity_risk: float


def compute_trust(
    *,
    behavior_match: float | None,
    genuineness: float,
    device_trust: float,
    env_consistency: float,
    support_weights: Mapping[str, float],
) -> TrustComponents:
    """Identity-gated multiplicative Trust Score.

    `support` is the weighted composite of the supporting signals (AE genuineness +
    device trust + env consistency). Identity match is the multiplicative *anchor*:
    `trust = (behavior_match/100) * support`. So strong device/AE can never *rescue* a
    poor identity match (Ojas-as-Rehan ~0.25x85 -> ~21, very_high), but a weak
    AE/device/geo *can* pull a genuine match down. On cold-start (no baseline yet,
    `behavior_match is None`) the identity gate is inactive and `trust = support`, biasing
    to `verify`, never block (CLAUDE.md invariant 9). All weights from policy."""
    w_ae = support_weights.get("genuineness", 0.0)
    w_dev = support_weights.get("device", 0.0)
    w_env = support_weights.get("env", 0.0)
    support = _clamp(
        w_ae * genuineness + w_dev * device_trust + w_env * env_consistency, 0.0, 100.0
    )
    if behavior_match is None:
        trust = round(support, 1)
    else:
        trust = round((behavior_match / 100.0) * support, 1)
    return TrustComponents(
        behavior_match=behavior_match,
        genuineness=round(genuineness, 1),
        device_trust=round(device_trust, 1),
        env_consistency=round(env_consistency, 1),
        support=round(support, 1),
        trust_score=trust,
        identity_risk=round(100.0 - trust, 1),
    )


def fit_distance_calibration(self_distances: Sequence[float]) -> CalibrationParams:
    """Fit the identity-distance calibration from a user's own enrollment self-distances
    (used by `enrollment.finalize()`; lives here so the distance math stays in one
    module). Threshold = 90th percentile of genuine self-distances, scale = their MAD --
    anchored so a genuine login (distance below threshold) calibrates < 0.5 and an
    impostor (well above) calibrates > 0.5. Robust to the handful of noisy live samples."""
    vals = sorted(float(d) for d in self_distances)
    if not vals:
        return calibration.default_calibration()
    n = len(vals)
    # 90th-percentile threshold (nearest-rank); with very few samples this lands on the
    # worst genuine self-distance, which is the conservative choice.
    idx = max(0, min(n - 1, int(math.ceil(0.9 * n)) - 1))
    threshold = vals[idx]
    median = vals[n // 2] if n % 2 else 0.5 * (vals[n // 2 - 1] + vals[n // 2])
    mad = sorted(abs(v - median) for v in vals)
    mad_val = mad[n // 2] if n % 2 else 0.5 * (mad[n // 2 - 1] + mad[n // 2])
    scale = MAD_TO_STD * mad_val
    if scale < EPS:
        # Degenerate (near-identical self-distances): fall back to a fraction of the
        # threshold so the logistic still has a usable slope.
        scale = max(threshold * 0.25, EPS)
    return CalibrationParams(scale=scale, threshold=threshold, temperature=1.0)
