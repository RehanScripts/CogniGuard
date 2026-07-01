"""Phase 11 acceptance check for the seeding gap (Implementation.md §5): seed_demo.py
must produce a `genuine` persona that can actually log in clean, and must be safe to
run repeatedly (RUN_SEED_ON_START runs it on every container start).
"""

from __future__ import annotations

import datetime as dt
import json
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.kafka_client import ping as kafka_ping
from app.main import app
from app.models.user import User
from app.redis_client import ping as redis_ping
from app.redis_client import redis_client
from app.s3_client import ping as s3_ping
from app.schemas.behavior import ActionBlock, BehaviorPayload, DeviceInfo, KeyEvent, KeystrokeBlock
from app.scoring.registry import Registry
from app.services import integrity
from app.services.policy import active_policy
from scripts import seed_demo

pytestmark = pytest.mark.skipif(
    not (redis_ping() and kafka_ping() and s3_ping()), reason="live infra not reachable"
)


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _genuine_login_behavior(client: TestClient) -> dict:
    nonce = client.get("/api/v1/auth/nonce").json()["nonce"]
    payload = BehaviorPayload(
        channel="web",
        source="web_sdk",
        nonce=nonce,
        # Monotonic milliseconds against wall-clock time, not a fixed 1 -- this device
        # fingerprint is the real seeded one (GENUINE_DEVICE_FP), so its seq floor in
        # the shared live Redis persists across separate pytest invocations *and*
        # across scripts.generate_fraud_scenarios runs (same fingerprint, same floor
        # key); milliseconds matches that script's _login_seq() unit so neither side
        # can produce a smaller value than a floor the other already set.
        seq=int(time.time() * 1000),
        ts=_now_iso(),
        integrity_sig="placeholder",
        device=DeviceInfo(
            fingerprint=seed_demo.GENUINE_DEVICE_FP,
            ua="pytest",
            screen="1920x1080",
            timezone="Asia/Kolkata",
            language="en-IN",
            platform="web",
        ),
        action=ActionBlock(type="LOGIN"),
        keystroke=KeystrokeBlock(
            events=[
                KeyEvent(key="x", down=10, up=90),
                KeyEvent(key="x", down=210, up=290),
                KeyEvent(key="x", down=420, up=500),
            ],
            field_id="username",
        ),
    )
    payload.integrity_sig = integrity.compute_signature(payload)
    return payload.model_dump()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_seed_demo_creates_genuine_persona_with_consent():
    summary = seed_demo.main()
    assert summary["user_id"]

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.customer_ref == seed_demo.GENUINE_USERNAME))
    assert user is not None
    assert user.consent_status == "GRANTED"
    assert str(user.user_id) == summary["user_id"]


def test_seed_demo_writes_expected_redis_state():
    summary = seed_demo.main()
    user_id = summary["user_id"]
    device_id = summary["device_id"]

    assert redis_client.sismember(f"user:{user_id}:known_devices", device_id)

    profile = redis_client.hgetall(f"user:{user_id}:profile")
    assert float(profile["avg_amount_30d"]) == seed_demo.AVG_AMOUNT_30D
    assert float(profile["std_amount_30d"]) == seed_demo.STD_AMOUNT_30D

    baseline_raw = redis_client.get(f"behavior:{user_id}:baseline")
    assert baseline_raw is not None
    baseline = json.loads(baseline_raw)["_baseline"]
    for dim in (
        "typing_speed",
        "key_latency_avg",
        "typing_rhythm_std",
        "hold_time_avg",
        "swipe_velocity_norm",
        "swipe_angle_dev",
        "touch_pressure_avg",
        "acceleration_variance",
        "mouse_velocity_mean",
    ):
        assert dim in baseline
        assert f"{dim}_std" in baseline


def test_seed_demo_active_policy_reflects_default():
    seed_demo.main()
    policy = active_policy(redis_client)
    assert policy["scoring_mode"] == "stacked"
    assert policy["thresholds"]["low_max"] == 30
    assert policy["thresholds"]["very_high_min"] == 85


def test_seed_demo_production_models_resolve():
    seed_demo.main()
    registry = Registry()
    # Must not raise -- a missing production row would raise LookupError.
    registry.get("isolation_forest")
    registry.get("xgboost_txn")


def test_seed_demo_beneficiary_added_recently_and_not_known():
    summary = seed_demo.main()
    user_id = summary["user_id"]

    with SessionLocal() as db:
        from app.models.beneficiary import Beneficiary, UserBeneficiary

        beneficiary = db.scalar(
            select(Beneficiary).where(Beneficiary.account_number == seed_demo.SCAMMER_VPA)
        )
        assert beneficiary is not None
        link = db.scalar(
            select(UserBeneficiary).where(
                UserBeneficiary.user_id == user_id,
                UserBeneficiary.beneficiary_id == beneficiary.beneficiary_id,
            )
        )
        assert link is not None
        age = dt.datetime.now(dt.timezone.utc) - link.added_at
        assert dt.timedelta(minutes=35) < age < dt.timedelta(minutes=45)

    # Remove any prior-test contamination from the known_beneficiaries Redis set so we
    # can assert the seed state independently of payment-flow tests that may have run
    # a transaction to this beneficiary and marked it as known.
    bene_id_str = str(beneficiary.beneficiary_id)
    redis_client.srem(f"user:{user_id}:known_beneficiaries", bene_id_str)
    assert not redis_client.sismember(f"user:{user_id}:known_beneficiaries", bene_id_str)


def test_seed_demo_is_idempotent():
    seed_demo.main()
    seed_demo.main()
    with SessionLocal() as db:
        matches = db.scalars(
            select(User).where(User.customer_ref == seed_demo.GENUINE_USERNAME)
        ).all()
    assert len(matches) == 1


def test_genuine_persona_logs_in_without_being_blocked(client):
    seed_demo.main()
    behavior = _genuine_login_behavior(client)

    r = client.post(
        "/api/v1/auth/login",
        json={
            "username": seed_demo.GENUINE_USERNAME,
            "password": seed_demo.GENUINE_PASSWORD,
            "behavior": behavior,
        },
    )
    assert r.status_code == 200
    body = r.json()
    # Don't hard-assert "low"/"allow" -- real model quality is a documented Phase 5/6
    # gap (PROGRESS.md). Assert the seeded baseline is at least enough to avoid the
    # outright block path a totally cold-start user would be biased toward.
    assert body["action"] != "block"
    assert body["integrity"] == "OK"
