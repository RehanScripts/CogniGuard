"""Phase 15 acceptance check (Implementation.md lines 726-760): AE-primary / IF-shadow /
fallback routing in `stack.py`. Pure-logic unit tests -- stub IF/AE models + a fake
Registry + a dict-backed fake Redis, same style as `test_scoring.py` (Phase 6) and
`test_autoencoder.py`/`test_calibration.py` (Phase 13). No live Postgres/Redis/S3.

`test_scoring.py` is the regression proof for "no AE input at all" bundles -- it is
*not* modified here; every assertion in it must keep passing unmodified alongside this
file (case 5 below reproduces its bundle shape directly to pin that down locally too).
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from app.schemas.features import FeatureBundle
from app.scoring import stack
from app.scoring.autoencoder import N_FEATURES, SEQ_LEN
from app.scoring.registry import LoadedModel
from training.train_xgboost import FEATURE_COLUMNS

POLICY = {
    "thresholds": {"low_max": 30, "medium_max": 60, "very_high_min": 85},
    "amplifiers": {
        "NEW_BENEF_HIGHVAL": 1.5,
        "RAPID_FANOUT": 1.4,
        "DRAIN": 1.3,
        "COERCION_TIME": 1.2,
    },
    "scoring_mode": "stacked",
}

_ZERO_SEQUENCE = [[0.0] * N_FEATURES for _ in range(SEQ_LEN)]
_ALL_REAL_MASK = [True] * SEQ_LEN
_BSCORE_IDX = FEATURE_COLUMNS.index("behavior_score")


class _FakeRegistry:
    """Duck-types app.scoring.registry.Registry.get() with canned models -- same shape
    as test_scoring.py's _FakeRegistry, generalized to also serve lstm_autoencoder."""

    def __init__(self, models: dict[str, object], *, fail: set[str] = frozenset()):
        self._models = models
        self._fail = fail

    def get(self, model_name: str) -> LoadedModel:
        if model_name in self._fail:
            raise RuntimeError(f"forced load failure for {model_name}")
        return LoadedModel(
            model_name=model_name,
            version=f"{model_name}@test",
            model=self._models[model_name],
            artifact_uri="",
        )


class _FakeRedis:
    """dict-backed `.get()` only -- everything stack.py's AE/IF routing reads from
    Redis (calibration, IF baseline) goes through `.get()`, same as
    test_calibration.py's fake."""

    def __init__(self, data: dict[str, str] | None = None):
        self._data = data or {}

    def get(self, key: str) -> str | None:
        return self._data.get(key)


class _StubIFModel:
    """Deterministic decision_function so if_score is exactly known/controlled."""

    def __init__(self, raw: float):
        self._raw = raw

    def decision_function(self, X):
        return [self._raw]


class _StubInput:
    name = "input"


class _StubAESession:
    """Duck-types onnxruntime.InferenceSession the same way test_autoencoder.py's
    _StubSession does -- returns a caller-supplied reconstruction regardless of input."""

    def __init__(self, reconstruction):
        self._reconstruction = reconstruction

    def get_inputs(self):
        return [_StubInput()]

    def run(self, output_names, inputs):
        return [self._reconstruction]


class _BscoreEchoXGBModel:
    """predict_proba derived purely from the `behavior_score` feature so tests can
    assert downstream stacking depends only on bscore's *value*, never its source."""

    def predict_proba(self, X):
        bscore = X[0][_BSCORE_IDX]
        p = 0.1 + 0.5 * bscore
        return [[1 - p, p]]


def _bundle(
    *,
    user_id: str = "u1",
    ae_cold_start: bool = False,
    behavior_sequence: list[list[float]] | None = None,
    behavior_sequence_mask: list[bool] | None = None,
    ae_recon_error: float | None = None,
) -> FeatureBundle:
    return FeatureBundle(
        user_id=user_id,
        ae_cold_start=ae_cold_start,
        behavior_sequence=behavior_sequence,
        behavior_sequence_mask=behavior_sequence_mask,
        ae_recon_error=ae_recon_error,
    )


def _registry(*, if_raw: float = 0.0, ae_recon: float = 0.0, fail: set[str] = frozenset()):
    """`ae_recon` is the constant offset added to the perfect (zero) reconstruction --
    `reconstruction_error` returns its *square* (masked MSE), not the offset itself."""
    ae_recon_array = (np.asarray(_ZERO_SEQUENCE, dtype="float32") + ae_recon).reshape(
        1, SEQ_LEN, N_FEATURES
    )
    return _FakeRegistry(
        {
            "isolation_forest": _StubIFModel(if_raw),
            "xgboost_txn": _BscoreEchoXGBModel(),
            "lstm_autoencoder": _StubAESession(ae_recon_array),
        },
        fail=fail,
    )


def test_ae_primary_drives_bscore_if_shadow_logged_not_acted_on():
    """AE-primary happy path. IF-only run (ae_cold_start=True) and AE-only run
    (ae_cold_start=False, AE calibrated to the *same* 0.5 value as IF) must produce
    identical final_risk_score/risk_band despite different behavior_score_source --
    the literal regression guard from the acceptance check."""
    registry = _registry(if_raw=0.0, ae_recon=0.0)  # if_score = sigmoid(0) = 0.5
    redis = _FakeRedis(
        {"calib:ae:population": json.dumps({"scale": 1.0, "threshold": 0.0, "temperature": 1.0})}
    )  # calibrate_ae(0.0, ...) = 0.5 too -- same bscore value as IF

    if_result = stack.score(
        _bundle(ae_cold_start=True), policy=POLICY, registry=registry, redis=redis
    )
    ae_result = stack.score(
        _bundle(
            ae_cold_start=False,
            behavior_sequence=_ZERO_SEQUENCE,
            behavior_sequence_mask=_ALL_REAL_MASK,
        ),
        policy=POLICY,
        registry=registry,
        redis=redis,
    )

    assert if_result.behavior_score_source == "if"
    assert ae_result.behavior_score_source == "ae"
    assert if_result.behavior_score == pytest.approx(0.5)
    assert ae_result.behavior_score == pytest.approx(0.5)
    assert ae_result.if_shadow_score is not None  # IF still computed in shadow
    assert ae_result.degraded_mode is False

    assert if_result.final_risk_score == pytest.approx(ae_result.final_risk_score)
    assert if_result.risk_band == ae_result.risk_band


def test_ae_failure_falls_back_to_if_degraded():
    registry = _registry(if_raw=0.0, fail={"lstm_autoencoder"})
    redis = _FakeRedis({})

    result = stack.score(
        _bundle(
            ae_cold_start=False,
            behavior_sequence=_ZERO_SEQUENCE,
            behavior_sequence_mask=_ALL_REAL_MASK,
        ),
        policy=POLICY,
        registry=registry,
        redis=redis,
    )

    assert result.behavior_score_source == "if"
    assert result.degraded_mode is True
    assert result.behavior_score == pytest.approx(0.5)  # sigmoid(0)


def test_ae_cold_start_falls_back_to_if_not_degraded():
    registry = _registry(if_raw=0.0)
    redis = _FakeRedis({})

    result = stack.score(
        _bundle(ae_cold_start=True, behavior_sequence=None),
        policy=POLICY,
        registry=registry,
        redis=redis,
    )

    assert result.behavior_score_source == "if"
    assert result.degraded_mode is False
    assert result.behavior_score == pytest.approx(0.5)


def test_both_if_and_ae_fail_yields_zero_fallback_degraded():
    registry = _registry(fail={"lstm_autoencoder", "isolation_forest"})
    redis = _FakeRedis({})

    result = stack.score(
        _bundle(
            ae_cold_start=False,
            behavior_sequence=_ZERO_SEQUENCE,
            behavior_sequence_mask=_ALL_REAL_MASK,
        ),
        policy=POLICY,
        registry=registry,
        redis=redis,
    )

    assert result.behavior_score_source == "fallback"
    assert result.degraded_mode is True
    assert result.behavior_score == 0.0
    assert result.if_shadow_score is None


def test_legacy_bundle_with_no_ae_input_treated_as_cold_start_not_failure():
    """A bundle that never sets ae_cold_start/behavior_sequence/ae_recon_error at all --
    exactly test_scoring.py's _genuine_bundle() shape -- must still resolve to the IF
    path with degraded_mode=False, proving the Phase 6 baseline suite needs no changes."""
    registry = _registry(if_raw=0.0)
    redis = _FakeRedis({})

    bundle = FeatureBundle(user_id="u1")  # ae_cold_start defaults False, no AE fields set
    result = stack.score(bundle, policy=POLICY, registry=registry, redis=redis)

    assert result.behavior_score_source == "if"
    assert result.degraded_mode is False
    assert result.behavior_score == pytest.approx(0.5)


def test_mobile_path_uses_device_supplied_recon_error_without_calling_registry():
    registry = _FakeRegistry(
        {
            "isolation_forest": _StubIFModel(0.0),
            "xgboost_txn": _BscoreEchoXGBModel(),
            # deliberately no "lstm_autoencoder" entry -- the mobile branch must never
            # call registry.get("lstm_autoencoder") at all.
        }
    )
    redis = _FakeRedis(
        {"calib:ae:population": json.dumps({"scale": 1.0, "threshold": 0.0, "temperature": 1.0})}
    )

    result = stack.score(
        _bundle(ae_cold_start=False, ae_recon_error=0.3),
        policy=POLICY,
        registry=registry,
        redis=redis,
    )

    assert result.behavior_score_source == "ae"
    assert result.ae_recon_error == pytest.approx(0.3)


def test_behavior_ae_anomaly_reason_code_fires_only_when_ae_primary_and_anomalous():
    redis_anomalous = _FakeRedis(
        {"calib:ae:population": json.dumps({"scale": 1.0, "threshold": 0.0, "temperature": 1.0})}
    )
    registry = _registry(if_raw=0.0, ae_recon=5.0)  # well above threshold -> bscore > 0.5

    anomalous = stack.score(
        _bundle(
            ae_cold_start=False,
            behavior_sequence=_ZERO_SEQUENCE,
            behavior_sequence_mask=_ALL_REAL_MASK,
        ),
        policy=POLICY,
        registry=registry,
        redis=redis_anomalous,
    )
    assert any(rc.code == "BEHAVIOR_AE_ANOMALY" for rc in anomalous.reason_codes)

    # IF-sourced result (ae_cold_start=True) must never carry the AE-specific code.
    if_only = stack.score(
        _bundle(ae_cold_start=True), policy=POLICY, registry=registry, redis=redis_anomalous
    )
    assert not any(rc.code == "BEHAVIOR_AE_ANOMALY" for rc in if_only.reason_codes)
