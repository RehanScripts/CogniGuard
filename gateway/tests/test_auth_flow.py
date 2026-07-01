"""Phase 8 acceptance check (Implementation.md lines 520-530), against the real running
app + the real `Registry()` -- whatever Phase 5/6 actually trained and registered in
this environment (confirmed deliberately over a synthetic-model override, since real
model quality is a known, already-documented Phase 5/6 gap, out of scope here).
Assertions are on structure/contract correctness and the decision-action's
consequences, not on a specific genuine-vs-impostor outcome.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.kafka_client import ping as kafka_ping
from app.main import app
from app.models.scoring import AuthChallenge
from app.models.session import Session as SessionModel
from app.models.user import User
from app.redis_client import ping as redis_ping
from app.redis_client import redis_client
from app.s3_client import ping as s3_ping
from app.schemas.behavior import ActionBlock, BehaviorPayload, DeviceInfo, KeyEvent, KeystrokeBlock
from app.services import integrity
from app.utils import fingerprint

pytestmark = pytest.mark.skipif(
    not (redis_ping() and kafka_ping() and s3_ping()), reason="live infra not reachable"
)


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _signed_behavior(
    client: TestClient, *, seq: int, device_fp: str, action_type: str = "LOGIN"
) -> dict:
    nonce = client.get("/api/v1/auth/nonce").json()["nonce"]
    payload = BehaviorPayload(
        channel="web",
        source="web_sdk",
        nonce=nonce,
        seq=seq,
        ts=_now_iso(),
        integrity_sig="placeholder",
        device=DeviceInfo(
            fingerprint=device_fp,
            ua="pytest",
            screen="1920x1080",
            timezone="Asia/Kolkata",
            language="en-IN",
            platform="web",
        ),
        action=ActionBlock(type=action_type),
        keystroke=KeystrokeBlock(
            events=[
                KeyEvent(key="x", down=10, up=90),
                KeyEvent(key="x", down=200, up=290),
                KeyEvent(key="x", down=420, up=500),
            ],
            field_id="username",
        ),
    )
    payload.integrity_sig = integrity.compute_signature(payload)
    return payload.model_dump()


def _register_and_consent(client: TestClient, username: str, password: str) -> None:
    r = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": password, "email": f"{username}@test.local"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    challenge_id = data["challenge_id"]
    # Read OTP directly from Redis (SMTP not configured in test environment).
    otp = redis_client.get(f"otp:{challenge_id}")
    assert otp is not None, "OTP not found in Redis"
    otp_code = otp.decode() if isinstance(otp, bytes) else otp
    r_verify = client.post(
        "/api/v1/auth/register/verify-email",
        json={"challenge_id": challenge_id, "otp_code": otp_code},
    )
    assert r_verify.status_code == 200, r_verify.text
    r2 = client.post(
        "/api/v1/auth/consent",
        json={"username": username, "action": "GRANT", "consent_version": "v1"},
    )
    assert r2.status_code == 200, r2.text


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def username():
    return f"authflow-{uuid.uuid4().hex[:12]}"


PASSWORD = "Passw0rd!1"


def test_login_returns_well_formed_decision_response_with_consequences(client, username):
    _register_and_consent(client, username, PASSWORD)
    behavior = _signed_behavior(client, seq=1, device_fp=f"device-{username}")

    r = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": PASSWORD, "behavior": behavior},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["action"] in ("allow", "verify", "block")
    assert body["entity_type"] == "login"
    assert body["integrity"] == "OK"

    db = SessionLocal()
    try:
        if body["action"] == "allow":
            assert body["session_token"]
            from app.utils import security

            claims = security.decode_jwt(body["session_token"])
            session = db.get(SessionModel, uuid.UUID(claims["session_id"]))
            assert session is not None
            assert session.status == "active"
        elif body["action"] == "verify":
            assert body["session_token"] is None
            assert body["step_up"] is not None
            challenge = db.get(AuthChallenge, uuid.UUID(body["step_up"]["challenge_id"]))
            assert challenge is not None
            assert challenge.status == "issued"
        else:  # block
            assert body["session_token"] is None
    finally:
        db.close()


def test_replayed_nonce_rejected(client, username):
    _register_and_consent(client, username, PASSWORD)
    behavior = _signed_behavior(client, seq=1, device_fp=f"device-{username}")

    r1 = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": PASSWORD, "behavior": behavior},
    )
    assert r1.status_code == 200  # first use consumes the nonce

    r2 = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": PASSWORD, "behavior": behavior},
    )
    assert r2.status_code == 400
    assert r2.json()["integrity"] == "INTEGRITY_REJECT"


def test_lockout_after_five_failures_other_ip_device_unaffected(username):
    with (
        TestClient(app, client=("10.50.1.1", 12345)) as attacker,
        TestClient(app, client=("10.50.1.2", 12345)) as clean,
    ):
        _register_and_consent(attacker, username, PASSWORD)
        device_fp = f"device-{username}"

        for i in range(5):
            behavior = _signed_behavior(attacker, seq=i + 1, device_fp=device_fp)
            r = attacker.post(
                "/api/v1/auth/login",
                json={"username": username, "password": "WrongPassword!", "behavior": behavior},
            )
            assert r.json()["action"] == "block"

        behavior_locked = _signed_behavior(attacker, seq=6, device_fp=device_fp)
        r_locked = attacker.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "WrongPassword!", "behavior": behavior_locked},
        )
        assert r_locked.status_code == 423

        clean_username = f"{username}-clean"
        _register_and_consent(clean, clean_username, PASSWORD)
        clean_behavior = _signed_behavior(
            clean, seq=1, device_fp=f"clean-device-{uuid.uuid4().hex}"
        )
        r_clean = clean.post(
            "/api/v1/auth/login",
            json={"username": clean_username, "password": PASSWORD, "behavior": clean_behavior},
        )
        assert r_clean.status_code == 200
        assert r_clean.json()["action"] in ("allow", "verify")


def test_login_session_id_feeds_the_ae_sequence_buffer(client, username):
    """Phase 15 follow-up: login mints `kafka_session_id` and scores under it
    (`session_id` in `FeatureReadContext`) *before* any `Session` row exists. On
    `allow`, that same UUID becomes the real `Session.session_id`, so the AE ring
    buffer login just pushed one row into is the exact buffer continuous-ingest/
    payment will keep accumulating into -- not a discarded one-off key."""
    _register_and_consent(client, username, PASSWORD)
    behavior = _signed_behavior(client, seq=1, device_fp=f"device-{username}")

    r = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": PASSWORD, "behavior": behavior},
    )
    assert r.status_code == 200
    body = r.json()
    if body["action"] != "allow":
        pytest.skip("model-quality gap: this run didn't resolve to allow")

    from app.utils import security

    claims = security.decode_jwt(body["session_token"])
    session_id = claims["session_id"]
    assert redis_client.llen(f"behavior:{session_id}:seq") == 1


def test_login_verify_branch_carries_kafka_session_id_into_stepup_state(
    client, username, monkeypatch
):
    """Same Phase 15 follow-up as above, for the `verify` branch: the `stepup:{id}`
    Redis blob now carries `kafka_session_id` so `verify_step_up` can assign the
    *same* session id login already scored under, instead of a fresh one that would
    orphan login's AE buffer row."""
    from app.services import auth_flow
    from app.services.decision_engine import Decision

    forced = Decision(action="verify", assurance="light", action_sensitivity="low")
    monkeypatch.setattr(auth_flow, "decide", lambda *a, **kw: forced)

    _register_and_consent(client, username, PASSWORD)
    behavior = _signed_behavior(client, seq=1, device_fp=f"device-{username}")
    r = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": PASSWORD, "behavior": behavior},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["action"] == "verify"
    challenge_id = body["step_up"]["challenge_id"]

    raw = redis_client.get(f"stepup:{challenge_id}")
    state = json.loads(raw)
    kafka_session_id = state["kafka_session_id"]
    assert redis_client.llen(f"behavior:{kafka_session_id}:seq") == 1

    # Read the actual OTP that the login flow generated in Redis (random 6-digit code).
    otp_raw = redis_client.get(f"otp:{challenge_id}")
    assert otp_raw is not None, "login flow should have generated an OTP in Redis"
    actual_otp = otp_raw.decode() if isinstance(otp_raw, bytes) else otp_raw

    good = client.post(
        "/api/v1/auth/step-up/verify",
        json={"challenge_id": challenge_id, "otp_or_assertion": actual_otp},
    )
    assert good.status_code == 200
    from app.utils import security

    claims = security.decode_jwt(good.json()["session_token"])
    assert claims["session_id"] == kafka_session_id


def test_step_up_verify_with_demo_otp_completes_login(client, username):
    _register_and_consent(client, username, PASSWORD)
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.customer_ref == username))
        device = fingerprint.get_or_create_device(
            db, DeviceInfo(fingerprint=f"stepup-device-{username}")
        )
        db.commit()

        challenge = AuthChallenge(challenge_type="OTP", status="issued")
        db.add(challenge)
        db.commit()
        challenge_id = str(challenge.challenge_id)

        redis_client.set(
            f"stepup:{challenge_id}",
            json.dumps(
                {
                    "user_id": str(user.user_id),
                    "device_id": str(device.device_id),
                    "ip": "10.0.0.9",
                    "asn": None,
                    "risk_band": "medium",
                    "final_risk_score": 45.0,
                    "challenge_type": "OTP",
                    "assurance": "light",
                }
            ),
            ex=300,
        )
        # Seed the OTP that the verify endpoint will look up in Redis.
        redis_client.set(f"otp:{challenge_id}", "123456", ex=300)
    finally:
        db.close()

    bad = client.post(
        "/api/v1/auth/step-up/verify",
        json={"challenge_id": challenge_id, "otp_or_assertion": "000000"},
    )
    assert bad.status_code == 401
    # Re-seed OTP after the bad attempt consumed it (verify_otp only deletes on success,
    # but a wrong code leaves the key intact — still, re-seed to be explicit).
    redis_client.set(f"otp:{challenge_id}", "123456", ex=300)

    good = client.post(
        "/api/v1/auth/step-up/verify",
        json={"challenge_id": challenge_id, "otp_or_assertion": "123456"},
    )
    assert good.status_code == 200
    body = good.json()
    assert body["action"] == "allow"
    assert body["session_token"]


def test_step_up_exhausted_attempts_escalate_to_block_and_open_case(client, username):
    """PRD §10.1 "if fail -> Blocked": repeated step-up failures must escalate from a
    retryable `verify` to `block` once policy `max_attempts` is hit, consume the
    challenge, and open a case (the "alert sent to bank")."""
    from app.models.governance import Case

    _register_and_consent(client, username, PASSWORD)
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.customer_ref == username))
        user_id = user.user_id
        device = fingerprint.get_or_create_device(
            db, DeviceInfo(fingerprint=f"stepup-lock-device-{username}")
        )
        db.commit()

        challenge = AuthChallenge(challenge_type="FINGERPRINT", status="issued")
        db.add(challenge)
        db.commit()
        challenge_id = str(challenge.challenge_id)

        redis_client.set(
            f"stepup:{challenge_id}",
            json.dumps(
                {
                    "user_id": str(user_id),
                    "device_id": str(device.device_id),
                    "ip": "10.0.0.11",
                    "asn": None,
                    "risk_band": "high",
                    "final_risk_score": 72.0,
                    "challenge_type": "FINGERPRINT",
                    "assurance": "strong",
                }
            ),
            ex=300,
        )
    finally:
        db.close()

    # Default policy max_attempts=3: first two fail retryably, the third blocks.
    first = client.post(
        "/api/v1/auth/step-up/verify", json={"challenge_id": challenge_id, "otp_or_assertion": ""}
    )
    assert first.status_code == 401 and first.json()["action"] == "verify"
    second = client.post(
        "/api/v1/auth/step-up/verify", json={"challenge_id": challenge_id, "otp_or_assertion": ""}
    )
    assert second.status_code == 401 and second.json()["action"] == "verify"

    third = client.post(
        "/api/v1/auth/step-up/verify", json={"challenge_id": challenge_id, "otp_or_assertion": ""}
    )
    assert third.status_code == 401
    body = third.json()
    assert body["action"] == "block"
    assert body["reason_codes"][0]["code"] == "STEP_UP_EXHAUSTED"

    # Challenge consumed -> a further attempt can't reuse it.
    assert redis_client.get(f"stepup:{challenge_id}") is None
    again = client.post(
        "/api/v1/auth/step-up/verify",
        json={"challenge_id": challenge_id, "otp_or_assertion": "123456"},
    )
    assert again.status_code == 404

    # A case (the bank alert) was opened for the user.
    db = SessionLocal()
    try:
        case = db.scalar(
            select(Case).where(Case.user_id == user_id).order_by(Case.created_at.desc())
        )
        assert case is not None and case.status == "open"
    finally:
        db.close()
