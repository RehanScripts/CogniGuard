"""Phase 9 acceptance check (Implementation.md lines 559-567): quarantine promotion --
a clean-window sample promotes (`accepted=True`), a sample with a `high`/`very_high`
`RiskScore` inside its window discards.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app.db import SessionLocal
from app.jobs.quarantine import run_promotion
from app.models.behavior import BehaviorSample
from app.models.scoring import RiskScore
from app.models.user import User
from app.utils import security


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def _make_user(db) -> User:
    user = User(
        customer_ref=f"quarantine-{uuid.uuid4().hex[:12]}",
        password_hash=security.hash_password("x"),
    )
    db.add(user)
    db.commit()
    return user


def test_clean_window_sample_is_promoted(db):
    user = _make_user(db)
    captured = _now() - dt.timedelta(days=8)
    sample = BehaviorSample(
        user_id=user.user_id,
        accepted=False,
        quarantine_until=captured + dt.timedelta(days=7),
        captured_at=captured,
    )
    db.add(sample)
    db.commit()
    sample_id = sample.sample_id

    result = run_promotion(db)
    assert result["promoted"] >= 1

    db.expire_all()
    promoted = db.get(BehaviorSample, sample_id)
    assert promoted is not None
    assert promoted.accepted is True
    assert promoted.quarantine_until is None


def test_high_risk_event_in_window_discards_sample(db):
    user = _make_user(db)
    captured = _now() - dt.timedelta(days=8)
    sample = BehaviorSample(
        user_id=user.user_id,
        accepted=False,
        quarantine_until=captured + dt.timedelta(days=7),
        captured_at=captured,
    )
    db.add(sample)
    db.flush()
    sample_id = sample.sample_id

    db.add(
        RiskScore(
            entity_type="login",
            entity_id=uuid.uuid4(),
            user_id=user.user_id,
            behavior_score=80.0,
            transaction_score=80.0,
            final_risk_score=80.0,
            risk_band="high",
            model_version="test",
            scored_at=captured + dt.timedelta(days=1),
        )
    )
    db.commit()

    result = run_promotion(db)
    assert result["discarded"] >= 1

    db.expire_all()
    assert db.get(BehaviorSample, sample_id) is None
