"""Phase 13 acceptance check (Implementation.md lines 689-695): the common calibration
layer that maps either behavioral model's raw anomaly signal onto one unified
Behavior_Score [0,1], 0=normal/1=anomalous. Pure math + a fake Redis -- no live infra.
"""

from __future__ import annotations

import json

import pytest

from app.scoring.calibration import (
    POPULATION_CALIBRATION_KEY,
    CalibrationParams,
    calibrate_ae,
    calibrate_if,
    default_calibration,
    load_calibration,
)
from app.scoring.isolation_forest import _sigmoid


class _FakeRedis:
    def __init__(self, data: dict[str, str] | None = None):
        self._data = data or {}

    def get(self, key: str) -> str | None:
        return self._data.get(key)


_PARAMS = CalibrationParams(scale=2.0, threshold=5.0, temperature=1.0)


def test_calibrate_ae_monotonic_in_recon_error():
    errors = [0.0, 2.5, 5.0, 7.5, 10.0, 50.0]
    scores = [calibrate_ae(e, _PARAMS) for e in errors]
    assert scores == sorted(scores)
    assert len(set(scores)) == len(scores)  # strictly increasing, not just non-decreasing


def test_calibrate_ae_threshold_maps_to_half():
    assert calibrate_ae(_PARAMS.threshold, _PARAMS) == pytest.approx(0.5, abs=1e-9)


@pytest.mark.parametrize("recon_error", [-1e6, 1e6])
def test_calibrate_ae_clamped_to_unit_interval(recon_error: float):
    score = calibrate_ae(recon_error, _PARAMS)
    assert 0.0 <= score <= 1.0


def test_calibrate_ae_cold_start_clamp_with_default_params():
    """With no calibration data at all (fresh install, ahead of Phase 16's seeding),
    `default_calibration()` must still produce a finite, sane [0,1] score for an
    ordinary-sized reconstruction error -- never an unclamped blow-up, never a crash."""
    params = default_calibration()
    score = calibrate_ae(0.5, params)  # raw == default threshold
    assert score == pytest.approx(0.5, abs=1e-9)
    for recon_error in (0.0, 1.0, 1e9):
        score = calibrate_ae(recon_error, params)
        assert 0.0 <= score <= 1.0


def test_calibrate_if_polarity_matches_isolation_forest_behavior_score():
    """isolation_forest.behavior_score flips sign on decision_function (higher
    decision_function == more normal == lower Behavior_Score). calibrate_if must
    preserve that same ordering so Phase 15 can compare AE vs. IF scores directly."""
    normal_raw, anomalous_raw = 1.0, -1.0
    normal_score = calibrate_if(normal_raw, _PARAMS)
    anomalous_score = calibrate_if(anomalous_raw, _PARAMS)
    assert anomalous_score > normal_score

    # Cross-check against the existing isolation_forest sigmoid's own polarity directly.
    assert _sigmoid(-normal_raw) < _sigmoid(-anomalous_raw)


def test_load_calibration_per_user_takes_priority_over_population():
    redis = _FakeRedis(
        {
            "behavior:u1:ae_calib": json.dumps({"scale": 3.0, "threshold": 1.0, "temperature": 2.0}),
            POPULATION_CALIBRATION_KEY: json.dumps({"scale": 9.0, "threshold": 9.0}),
        }
    )
    params = load_calibration("u1", redis=redis)
    assert params == CalibrationParams(scale=3.0, threshold=1.0, temperature=2.0)


def test_load_calibration_population_fallback_when_no_per_user_key():
    redis = _FakeRedis({POPULATION_CALIBRATION_KEY: json.dumps({"scale": 4.0, "threshold": 2.0})})
    params = load_calibration("u1", redis=redis)
    assert params == CalibrationParams(scale=4.0, threshold=2.0, temperature=1.0)


def test_load_calibration_default_when_no_keys_present():
    redis = _FakeRedis({})
    assert load_calibration("u1", redis=redis) == default_calibration()
