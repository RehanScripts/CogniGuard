"""Phase 12 acceptance check (Implementation.md lines 641-668 subset): PSI/KS score-drift
math behaves correctly on known distributions, outcome-drift precision is computed from
resolved cases, and `run()` flags a breach on persisted `risk_scores` rows without ever
auto-promoting past `staging` (CLAUDE.md invariant 18 -- a breach only ever registers a
new staging challenger, so `trigger_retrain=False` here just keeps the test from kicking
off a real training job, not from skipping anything safety-relevant).
"""

from __future__ import annotations

import datetime as dt
import uuid

import numpy as np
import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.kafka_client import ping as kafka_ping
from app.models.governance import Case
from app.models.scoring import RiskScore
from app.redis_client import ping as redis_ping
from app.s3_client import ping as s3_ping
from training import drift_monitor


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def test_psi_near_zero_for_identical_distributions():
    rng = np.random.default_rng(1)
    sample = rng.normal(50, 10, size=500)
    metrics = drift_monitor.score_drift(sample, sample)
    assert metrics["psi"] < 0.02
    assert metrics["ks_stat"] < 0.05


def test_psi_and_ks_high_for_shifted_distributions():
    rng = np.random.default_rng(2)
    reference = rng.normal(20, 3, size=300)
    live = rng.normal(80, 3, size=300)
    metrics = drift_monitor.score_drift(live, reference)
    assert metrics["psi"] > 1.0
    assert metrics["ks_stat"] > 0.9
    assert metrics["ks_pvalue"] < 0.01


_live_infra = pytest.mark.skipif(
    not (redis_ping() and kafka_ping() and s3_ping()), reason="live infra not reachable"
)


@_live_infra
def test_outcome_drift_precision_over_resolved_cases():
    since = _now() - dt.timedelta(hours=1)
    db = SessionLocal()
    case_ids: list[uuid.UUID] = []
    try:
        for status in ("confirmed_fraud", "confirmed_fraud", "false_positive"):
            case = Case(status=status, resolved_at=_now())
            db.add(case)
            db.flush()
            case_ids.append(case.case_id)
        db.commit()

        report = drift_monitor.outcome_drift(db, since=since)
        assert report["n_confirmed_fraud"] >= 2
        assert report["n_false_positive"] >= 1
        assert report["precision"] is not None
    finally:
        for cid in case_ids:
            row = db.get(Case, cid)
            if row is not None:
                db.delete(row)
        db.commit()
        db.close()


@_live_infra
def test_run_flags_breach_on_final_risk_score_without_retraining():
    db = SessionLocal()
    now = _now()
    policy = {
        "drift": {
            "psi_alert": 0.25,
            "ks_alert": 0.2,
            "lookback_hours": 1,
            "reference_hours": 2,
            "min_samples": 20,
        }
    }
    rng = np.random.default_rng(3)
    entity_ids: list[uuid.UUID] = []
    try:
        for value in rng.uniform(80, 95, size=30):
            entity_id = uuid.uuid4()
            entity_ids.append(entity_id)
            db.add(
                RiskScore(
                    entity_type="login",
                    entity_id=entity_id,
                    final_risk_score=float(value),
                    risk_band="high",
                    scored_at=now - dt.timedelta(minutes=30),
                )
            )
        for value in rng.uniform(10, 25, size=30):
            entity_id = uuid.uuid4()
            entity_ids.append(entity_id)
            db.add(
                RiskScore(
                    entity_type="login",
                    entity_id=entity_id,
                    final_risk_score=float(value),
                    risk_band="low",
                    scored_at=now - dt.timedelta(hours=1, minutes=30),
                )
            )
        db.commit()

        report = drift_monitor.run(db, policy=policy, trigger_retrain=False)

        assert report["columns"]["final_risk_score"]["breached"] is True
        breached_columns = {b["column"] for b in report["breaches"]}
        assert "final_risk_score" in breached_columns
        assert report["retrained_models"] == []
    finally:
        for entity_id in entity_ids:
            row = db.scalar(select(RiskScore).where(RiskScore.entity_id == entity_id))
            if row is not None:
                db.delete(row)
        db.commit()
        db.close()
