"""Phase 9 acceptance check (Implementation.md lines 559-567): RTBF cascading purge --
a `WITHDRAWN` user's `BehaviorSample` rows + Redis baseline are hard-deleted, the audit
trail is retained; `retention_expires_at` purges independent of consent status.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.jobs.rtbf import run_rtbf
from app.models.behavior import BehaviorSample
from app.models.governance import AuditLog
from app.models.user import User
from app.redis_client import redis_client
from app.utils import security


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_withdrawn_user_samples_and_baseline_purged_audit_retained(db):
    user = User(
        customer_ref=f"rtbf-{uuid.uuid4().hex[:12]}",
        password_hash=security.hash_password("x"),
        consent_status="WITHDRAWN",
    )
    db.add(user)
    db.flush()
    db.add(BehaviorSample(user_id=user.user_id, accepted=True))
    db.add(
        BehaviorSample(
            user_id=user.user_id,
            accepted=False,
            quarantine_until=_now() + dt.timedelta(days=3),
        )
    )
    db.commit()

    baseline_key = f"behavior:{user.user_id}:baseline"
    redis_client.set(baseline_key, "{}")

    result = run_rtbf(db)
    assert result["users_purged"] >= 1
    assert result["samples_deleted"] >= 2

    db.expire_all()
    remaining = db.scalars(
        select(BehaviorSample).where(BehaviorSample.user_id == user.user_id)
    ).all()
    assert remaining == []
    assert redis_client.exists(baseline_key) == 0

    audit_row = db.scalar(
        select(AuditLog).where(AuditLog.entity_id == user.user_id, AuditLog.action == "RTBF_PURGE")
    )
    assert audit_row is not None


def test_retention_expiry_purges_regardless_of_consent(db):
    user = User(
        customer_ref=f"rtbf-ret-{uuid.uuid4().hex[:12]}", password_hash=security.hash_password("x")
    )
    db.add(user)
    db.flush()
    sample = BehaviorSample(
        user_id=user.user_id,
        accepted=True,
        retention_expires_at=_now() - dt.timedelta(days=1),
    )
    db.add(sample)
    db.commit()
    sample_id = sample.sample_id

    result = run_rtbf(db)
    assert result["retention_purged"] >= 1

    db.expire_all()
    assert db.get(BehaviorSample, sample_id) is None
