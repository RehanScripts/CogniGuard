"""Phase 6 acceptance check (Implementation.md lines 416-424). Pure-logic unit tests --
fits tiny in-memory IsolationForest/XGBClassifier models and a fake Registry, so none of
these need live Postgres/Redis/S3.
"""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.ensemble import IsolationForest
from xgboost import XGBClassifier

from app.schemas.features import (
    BehaviorFeatures,
    ContextFeatures,
    DeviceFeatures,
    FeatureBundle,
    NetworkFeatures,
    TxnFeatures,
)
from app.scoring import stack
from app.scoring.registry import LoadedModel

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

# "Typical" behavior vector the synthetic IsolationForest is trained around -- matches
# explain.py's _BEHAVIOR_REFERENCE means so genuine/impostor tests are self-consistent.
_NORMAL_MEAN = [4.5, 180.0, 40.0, 90.0, 1.2, 0.3, 0.5, 0.05, 0.8]


class _FakeRegistry:
    """Duck-types app.scoring.registry.Registry.get() with canned models."""

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


def _genuine_bundle(*, cold_start: bool = False) -> FeatureBundle:
    return FeatureBundle(
        user_id="u1",
        behavior=BehaviorFeatures(
            typing_speed=4.5,
            key_latency_avg=180.0,
            typing_rhythm_std=40.0,
            hold_time_avg=90.0,
            swipe_velocity_norm=1.2,
            swipe_angle_dev=0.3,
            touch_pressure_avg=0.5,
            acceleration_variance=0.05,
            mouse_velocity_mean=0.8,
        ),
        device=DeviceFeatures(device_trust=80.0, is_new_device=False, is_rooted=False),
        network=NetworkFeatures(geo_distance_km=2.0, geo_change=False),
        txn=TxnFeatures(
            amount=500.0, amount_zscore=0.1, velocity_1h=1, velocity_24h=2, is_new_payee=False
        ),
        context=ContextFeatures(),
        cold_start=cold_start,
    )


def _impostor_bundle() -> FeatureBundle:
    return FeatureBundle(
        user_id="u2",
        behavior=BehaviorFeatures(
            typing_speed=0.2,
            key_latency_avg=900.0,
            typing_rhythm_std=300.0,
            hold_time_avg=10.0,
            swipe_velocity_norm=0.0,
            swipe_angle_dev=0.0,
            touch_pressure_avg=0.0,
            acceleration_variance=0.0,
            mouse_velocity_mean=0.0,
        ),
        device=DeviceFeatures(device_trust=0.0, is_new_device=True, is_rooted=False),
        network=NetworkFeatures(geo_distance_km=9000.0, geo_change=True),
        txn=TxnFeatures(
            amount=50000.0,
            amount_zscore=5.0,
            velocity_1h=10,
            velocity_24h=30,
            is_new_payee=True,
            beneficiary_risk=0.6,
            odd_time=True,
            high_velocity=True,
        ),
        context=ContextFeatures(),
        cold_start=False,
    )


@pytest.fixture(scope="module")
def fitted_isolation_forest():
    rng = np.random.default_rng(42)
    rows = rng.normal(loc=_NORMAL_MEAN, scale=0.05, size=(200, 9))
    return IsolationForest(n_estimators=64, contamination="auto", random_state=42).fit(rows)


@pytest.fixture(scope="module")
def fitted_xgboost():
    """Cleanly separable synthetic data: the fraud class always satisfies the PRD §6.6
    heuristic (amount_zscore>2 & is_new_payee & odd_time), the genuine class never does
    -- so a small model learns the boundary reliably instead of overfitting on a
    near-empty minority class (the real risk with fully-random labels)."""
    rng = np.random.default_rng(7)
    n = 400
    label = (np.arange(n) % 2).astype(int)

    amount_zscore = np.where(label == 1, rng.uniform(2.5, 5.0, n), rng.uniform(-2.0, 1.5, n))
    is_new_payee = np.where(label == 1, 1, rng.integers(0, 2, n))
    odd_time = np.where(label == 1, 1, rng.integers(0, 2, n))
    behavior_score = rng.uniform(0, 1, n)  # noise -- not part of the heuristic
    velocity_1h = rng.integers(0, 6, n)
    X = np.column_stack(
        [
            rng.uniform(100, 5000, n),  # amount
            amount_zscore,
            velocity_1h,
            rng.integers(0, 20, n),  # velocity_24h
            rng.uniform(0, 5000, n),  # amount_sum_24h
            is_new_payee,
            is_new_payee * 0.6,  # beneficiary_risk
            odd_time,
            behavior_score,
        ]
    )
    return XGBClassifier(n_estimators=30, max_depth=3, eval_metric="logloss", random_state=7).fit(
        X, label
    )


def test_stacked_genuine_bundle_low_band(fitted_isolation_forest, fitted_xgboost):
    registry = _FakeRegistry(
        {"isolation_forest": fitted_isolation_forest, "xgboost_txn": fitted_xgboost}
    )
    result = stack.score(_genuine_bundle(), policy=POLICY, registry=registry)
    assert result.risk_band == "low"
    assert result.degraded_mode is False


def test_stacked_impostor_bundle_high_band(fitted_isolation_forest, fitted_xgboost):
    registry = _FakeRegistry(
        {"isolation_forest": fitted_isolation_forest, "xgboost_txn": fitted_xgboost}
    )
    result = stack.score(_impostor_bundle(), policy=POLICY, registry=registry)
    assert result.risk_band in ("high", "very_high")


def test_behavior_score_fed_as_xgb_feature():
    bundle = _genuine_bundle()
    feats = bundle.xgb_features(behavior_score=0.73)
    assert feats["behavior_score"] == 0.73
    assert set(feats.keys()) == {
        "amount",
        "amount_zscore",
        "velocity_1h",
        "velocity_24h",
        "amount_sum_24h",
        "is_new_payee",
        "beneficiary_risk",
        "odd_time",
        "behavior_score",
    }


def test_xgboost_load_failure_triggers_fallback(fitted_isolation_forest, fitted_xgboost):
    registry = _FakeRegistry(
        {"isolation_forest": fitted_isolation_forest, "xgboost_txn": fitted_xgboost},
        fail={"xgboost_txn"},
    )
    result = stack.score(_genuine_bundle(), policy=POLICY, registry=registry)
    assert result.degraded_mode is True
    assert result.model_version == "fallback"
    assert 0.0 <= result.transaction_score <= 1.0


def test_isolation_forest_failure_does_not_crash(fitted_xgboost):
    registry = _FakeRegistry({"xgboost_txn": fitted_xgboost}, fail={"isolation_forest"})
    result = stack.score(_genuine_bundle(), policy=POLICY, registry=registry)
    assert result.degraded_mode is True
    assert result.behavior_score == 0.0


def test_weighted_ensemble_mode_matches_formula(fitted_isolation_forest, fitted_xgboost):
    registry = _FakeRegistry(
        {"isolation_forest": fitted_isolation_forest, "xgboost_txn": fitted_xgboost}
    )
    bundle = _genuine_bundle()
    weighted_policy = {**POLICY, "scoring_mode": "weighted"}

    result = stack.score(bundle, policy=weighted_policy, registry=registry)

    from app.scoring import isolation_forest, xgboost_model

    bscore = isolation_forest.behavior_score(
        bundle.behavior_vector(), model=fitted_isolation_forest
    )
    txn_p = xgboost_model.fraud_probability(
        bundle.xgb_features(behavior_score=bscore), model=fitted_xgboost
    )
    device_signal = bundle.device.device_trust / 100.0
    expected_final_p = max(0.0, min(1.0, 0.60 * txn_p + 0.25 * bscore + 0.15 * (1 - device_signal)))

    assert result.transaction_score == pytest.approx(expected_final_p)


def test_cold_start_does_not_crash_and_leans_low(fitted_isolation_forest, fitted_xgboost):
    registry = _FakeRegistry(
        {"isolation_forest": fitted_isolation_forest, "xgboost_txn": fitted_xgboost},
        fail={"xgboost_txn"},
    )
    bundle = _genuine_bundle(cold_start=True)
    result = stack.score(bundle, policy=POLICY, registry=registry)
    assert result.risk_band != "very_high"


def test_amplifiers_appended_to_reason_codes(fitted_isolation_forest, fitted_xgboost):
    from app.scoring.amplifiers import TxnContext

    registry = _FakeRegistry(
        {"isolation_forest": fitted_isolation_forest, "xgboost_txn": fitted_xgboost}
    )
    txn_context = TxnContext(payee_age_minutes=30, daily_avg_amount=1000, amount=900)
    result = stack.score(
        _genuine_bundle(), policy=POLICY, registry=registry, txn_context=txn_context
    )

    assert any(a.code == "NEW_BENEF_HIGHVAL" for a in result.amplifiers)
    assert any(rc.code == "NEW_BENEF_HIGHVAL" for rc in result.reason_codes)
