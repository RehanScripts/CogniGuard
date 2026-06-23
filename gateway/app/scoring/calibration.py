"""Common calibration layer (Implementation.md Phase 13) -- maps either behavioral
model's raw anomaly signal onto one unified Behavior_Score in [0,1], 0=normal /
1=anomalous: the polarity `isolation_forest.behavior_score` already returns. This is
what lets Phase 15's `stack.py` treat the LSTM Autoencoder's reconstruction error and
Isolation Forest's `decision_function` as interchangeable inputs to the same downstream
band/XGBoost logic. No caller wires this in yet -- it is pure, injectable math.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from redis import Redis

EPS = 1e-9

# Seeded by Phase 16's seed_calibration.py; read-only here -- nothing writes this key
# in Phase 13.
POPULATION_CALIBRATION_KEY = "calib:ae:population"

# Used before either a per-user or population calibration exists (fresh install, ahead
# of Phase 16's seeding). Anchoring threshold=0.5 with scale=1.0 keeps a raw signal of
# 0.5 calibrating to ~0.5 -- a neutral midpoint rather than an arbitrary extreme, which
# matters because this is the same cold-start path Phase 15 must bias toward `verify`,
# never an outright high score, never an outright "definitely safe" score either.
_DEFAULT_PARAMS_KWARGS = {"scale": 1.0, "threshold": 0.5, "temperature": 1.0}


@dataclass(frozen=True)
class CalibrationParams:
    scale: float
    threshold: float
    temperature: float = 1.0


def _logistic(z: float) -> float:
    """Numerically stable sigmoid -- `math.exp` overflows for large-magnitude `z` in
    the naive `1/(1+exp(-z))` form (extreme raw signals are expected at the tails of a
    robust-z calibration, not just a theoretical edge case)."""
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def _clamp01(p: float) -> float:
    return min(1.0, max(0.0, p))


def _calibrate(raw: float, params: CalibrationParams) -> float:
    """robust-z -> logistic, anchored so `raw == threshold` lands at sigmoid(0) == 0.5.
    Always returns a value in [0,1] -- extreme raw inputs clamp to (near) 0 or 1 rather
    than relying on the logistic's natural saturation alone (belt-and-braces against
    float edge cases)."""
    scale = max(params.scale, EPS)
    z = (raw - params.threshold) / scale * params.temperature
    return _clamp01(_logistic(z))


def calibrate_ae(recon_error: float, params: CalibrationParams) -> float:
    """LSTM Autoencoder reconstruction error -> Behavior_Score [0,1]. Higher
    reconstruction error means more anomalous, so no sign flip is needed (unlike
    Isolation Forest's `decision_function`, see `calibrate_if` below)."""
    return _calibrate(recon_error, params)


def calibrate_distance(distance: float, params: CalibrationParams) -> float:
    """Per-user identity-distance (robust-z RMS, `scoring/identity.py`) -> identity
    anomaly [0,1]. Higher distance == less like the enrolled user == more anomalous, so
    -- exactly like `calibrate_ae` -- no sign flip is needed. A public wrapper over the
    shared robust-z -> logistic transform so the identity scorer reuses this calibration
    layer without reaching into a private symbol."""
    return _calibrate(distance, params)


def calibrate_if(decision_function_raw: float, params: CalibrationParams) -> float:
    """Isolation Forest's raw `decision_function` output (higher == more normal) ->
    Behavior_Score [0,1] in the *same* polarity as `calibrate_ae`, for Phase 15's
    IF-shadow comparison against the AE-primary score. Sign-flipped first since a lower
    `decision_function` means more anomalous -- the opposite of `recon_error`."""
    return _calibrate(-decision_function_raw, params)


def default_calibration() -> CalibrationParams:
    """The pre-Phase-16 / fresh-install fallback when no calibration data exists at
    all -- never raises, so callers always get usable params."""
    return CalibrationParams(**_DEFAULT_PARAMS_KWARGS)


def _parse(raw: str) -> CalibrationParams:
    data = json.loads(raw)
    return CalibrationParams(
        scale=float(data.get("scale", _DEFAULT_PARAMS_KWARGS["scale"])),
        threshold=float(data.get("threshold", _DEFAULT_PARAMS_KWARGS["threshold"])),
        temperature=float(data.get("temperature", _DEFAULT_PARAMS_KWARGS["temperature"])),
    )


def user_calibration_key(user_id: str) -> str:
    return f"behavior:{user_id}:ae_calib"


def load_calibration(user_id: str, *, redis: Redis) -> CalibrationParams:
    """Per-user `behavior:{user_id}:ae_calib` if present, else the population fallback
    `calib:ae:population`, else `default_calibration()`. Nothing writes either Redis key
    in this phase (that's Phase 16's `seed_calibration.py`) -- this is a read-only lookup
    exercised here against injected fakes, not live Redis state."""
    raw = redis.get(user_calibration_key(user_id)) or redis.get(POPULATION_CALIBRATION_KEY)
    if not raw:
        return default_calibration()
    return _parse(raw)
