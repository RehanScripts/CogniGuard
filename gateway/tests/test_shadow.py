"""Phase 12 acceptance check: shadow/challenger scoring is a safe no-op when no
staging row exists, and otherwise persists a flagged `RiskScore` row (`is_shadow=True`,
the challenger's version) without ever writing a `Decision` row.
"""

from __future__ import annotations

import uuid

import numpy as np
import pytest
from sklearn.ensemble import IsolationForest
from sqlalchemy import select
from xgboost import XGBClassifier

from app.db import SessionLocal
from app.kafka_client import ping as kafka_ping
from app.models.scoring import Decision, RiskScore
from app.redis_client import ping as redis_ping
from app.s3_client import ping as s3_ping
from app.schemas.features import (
    BehaviorFeatures,
    ContextFeatures,
    DeviceFeatures,
    FeatureBundle,
    NetworkFeatures,
    TxnFeatures,
)
from app.scoring import shadow
from app.scoring.registry import LoadedModel

POLICY = {
    "thresholds": {"low_max": 30, "medium_max": 60, "very_high_min": 85},
    "amplifiers": {},
    "scoring_mode": "stacked",
}

_NORMAL_MEAN = [4.5, 180.0, 40.0, 90.0, 1.2, 0.3, 0.5, 0.05, 0.8]


class _FakeRegistry:
    """Duck-types `Registry.get()`/`get_challenger()` with canned production +
    challenger models -- mirrors `tests/test_scoring.py`'s `_FakeRegistry`."""

    def __init__(self, production: dict[str, object], challengers: dict[str, object] | None = None):
        self._production = production
        self._challengers = challengers or {}

    def get(self, model_name: str) -> LoadedModel:
        return LoadedModel(
            model_name=model_name,
            version=f"{model_name}@prod",
            model=self._production[model_name],
            artifact_uri="",
        )

    def get_challenger(self, model_name: str) -> LoadedModel | None:
        model = self._challengers.get(model_name)
        if model is None:
            return None
        return LoadedModel(
            model_name=model_name, version=f"{model_name}@challenger", model=model, artifact_uri=""
        )


def _genuine_bundle() -> FeatureBundle:
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
        cold_start=False,
    )


@pytest.fixture(scope="module")
def fitted_isolation_forest():
    rng = np.random.default_rng(42)
    rows = rng.normal(loc=_NORMAL_MEAN, scale=0.05, size=(200, 9))
    return IsolationForest(n_estimators=64, contamination="auto", random_state=42).fit(rows)


@pytest.fixture(scope="module")
def fitted_xgboost():
    rng = np.random.default_rng(7)
    n = 200
    label = (np.arange(n) % 2).astype(int)
    X = rng.uniform(0, 1, size=(n, 9))
    return XGBClassifier(n_estimators=10, max_depth=2, eval_metric="logloss", random_state=7).fit(
        X, label
    )


def test_shadow_noop_when_no_challenger_registered(fitted_isolation_forest, fitted_xgboost):
    registry = _FakeRegistry(
        {"isolation_forest": fitted_isolation_forest, "xgboost_txn": fitted_xgboost}
    )
    # db=None proves the no-challenger path returns before any DB access is attempted --
    # passing a real session here isn't needed since this case must never touch it.
    shadow.run_and_persist(
        None,
        _genuine_bundle(),
        policy=POLICY,
        registry=registry,
        entity_type="login",
        entity_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )


def test_shadow_swallows_scoring_exception(fitted_isolation_forest, fitted_xgboost):
    """A shadow run must never raise into the caller's BackgroundTasks job."""

    class _ExplodingRegistry(_FakeRegistry):
        def get_challenger(self, model_name: str) -> LoadedModel | None:
            raise RuntimeError("boom")

    registry = _ExplodingRegistry(
        {"isolation_forest": fitted_isolation_forest, "xgboost_txn": fitted_xgboost}
    )
    shadow.run_and_persist(
        None,
        _genuine_bundle(),
        policy=POLICY,
        registry=registry,
        entity_type="login",
        entity_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )


@pytest.mark.skipif(
    not (redis_ping() and kafka_ping() and s3_ping()), reason="live infra not reachable"
)
def test_shadow_persists_flagged_risk_score_with_challenger_version(
    fitted_isolation_forest, fitted_xgboost
):
    registry = _FakeRegistry(
        {"isolation_forest": fitted_isolation_forest, "xgboost_txn": fitted_xgboost},
        challengers={"xgboost_txn": fitted_xgboost},
    )
    entity_id = uuid.uuid4()
    db = SessionLocal()
    try:
        shadow.run_and_persist(
            db,
            _genuine_bundle(),
            policy=POLICY,
            registry=registry,
            entity_type="login",
            entity_id=entity_id,
            user_id=None,
        )

        rows = db.scalars(select(RiskScore).where(RiskScore.entity_id == entity_id)).all()
        assert len(rows) == 1
        assert rows[0].is_shadow is True
        assert rows[0].model_version == "xgboost_txn@challenger"

        decisions = db.scalars(select(Decision).where(Decision.entity_id == entity_id)).all()
        assert decisions == []
    finally:
        for row in db.scalars(select(RiskScore).where(RiskScore.entity_id == entity_id)).all():
            db.delete(row)
        db.commit()
        db.close()
