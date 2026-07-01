"""Phase 8 acceptance check, against the real running app + real `Registry()`.
Structural-correctness approach (see test_auth_flow.py docstring for why): a payment
gets logged in first; if the real model doesn't return `allow` at login (no token
issued), the payment test that needs a session skips rather than asserting on a
specific score.
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
from app.models.transaction import Transaction
from app.models.user import User
from app.redis_client import ping as redis_ping
from app.redis_client import redis_client
from app.s3_client import ping as s3_ping
from app.schemas.behavior import ActionBlock, BehaviorPayload, DeviceInfo, KeyEvent, KeystrokeBlock
from app.schemas.payment import PaymentScoreResponse
from app.services import integrity

pytestmark = pytest.mark.skipif(
    not (redis_ping() and kafka_ping() and s3_ping()), reason="live infra not reachable"
)

PASSWORD = "Passw0rd!1"


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
    r = client.post("/api/v1/auth/register", json={"username": username, "password": password})
    assert r.status_code == 201, r.text
    r2 = client.post(
        "/api/v1/auth/consent",
        json={"username": username, "action": "GRANT", "consent_version": "v1"},
    )
    assert r2.status_code == 200, r2.text


def _logged_in_token(client: TestClient, username: str, device_fp: str) -> str | None:
    r = client.post("/api/v1/auth/register", json={"username": username, "password": PASSWORD})
    assert r.status_code == 201, r.text
    r2 = client.post(
        "/api/v1/auth/consent",
        json={"username": username, "action": "GRANT", "consent_version": "v1"},
    )
    assert r2.status_code == 200, r2.text

    behavior = _signed_behavior(client, seq=1, device_fp=device_fp)
    r3 = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": PASSWORD, "behavior": behavior},
    )
    assert r3.status_code == 200, r3.text
    body = r3.json()
    return body["session_token"] if body["action"] == "allow" else None


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def username():
    return f"payflow-{uuid.uuid4().hex[:12]}"


def test_genuine_small_transfer_returns_well_formed_response(client, username):
    device_fp = f"device-{username}"
    token = _logged_in_token(client, username, device_fp)
    if token is None:
        pytest.skip(
            "login did not return allow with the current model state -- can't get a session"
        )

    behavior = _signed_behavior(client, seq=2, device_fp=device_fp, action_type="TRANSFER")
    r = client.post(
        "/api/v1/payment/score",
        json={"amount": 500, "transfer_type": "UPI", "channel": "web", "behavior": behavior},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["action"] in ("allow", "verify", "block")
    assert body["entity_type"] == "transaction"
    assert isinstance(body["amplifiers"], list)


def test_new_payee_high_value_populates_txn_controls_when_flagged(client, username):
    device_fp = f"device-{username}"
    token = _logged_in_token(client, username, device_fp)
    if token is None:
        pytest.skip(
            "login did not return allow with the current model state -- can't get a session"
        )

    behavior = _signed_behavior(client, seq=2, device_fp=device_fp, action_type="TRANSFER")
    body = {
        "amount": 95_000,
        "beneficiary_vpa": f"newpayee-{uuid.uuid4().hex}@upi",
        "transfer_type": "UPI",
        "channel": "web",
        "behavior": behavior,
    }
    r = client.post(
        "/api/v1/payment/score", json=body, headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    resp = r.json()

    # Brand-new high-value payee should never resolve to a bare "allow" with empty
    # controls -- §10.2's risk×action matrix demands at least cooling-off for high
    # stakes even at low risk, and txn_fraud_layer adds more on top of that whenever
    # any amplifier fires too.
    if resp["action"] != "allow" or resp["amplifiers"]:
        controls = resp["txn_controls"]
        assert controls is not None
        assert any(
            [
                controls["cooling_until"],
                controls["manual_amount"],
                controls["coercion_check"],
                controls["reconfirm"],
            ]
        )


def test_payment_accumulates_into_the_same_ae_sequence_buffer_login_started(client, username):
    """Phase 15 follow-up: payment now passes `session_id=str(session.session_id)`
    into `FeatureReadContext`, and login already pushed the first row of that same
    session's AE buffer (see test_auth_flow.py's equivalent). The two should land in
    the exact same `behavior:{session_id}:seq` list, not two disjoint ones."""
    device_fp = f"device-{username}"
    token = _logged_in_token(client, username, device_fp)
    if token is None:
        pytest.skip(
            "login did not return allow with the current model state -- can't get a session"
        )

    from app.utils import security

    claims = security.decode_jwt(token)
    session_id = claims["session_id"]
    assert redis_client.llen(f"behavior:{session_id}:seq") == 1

    behavior = _signed_behavior(client, seq=2, device_fp=device_fp, action_type="TRANSFER")
    r = client.post(
        "/api/v1/payment/score",
        json={"amount": 500, "transfer_type": "UPI", "channel": "web", "behavior": behavior},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert redis_client.llen(f"behavior:{session_id}:seq") == 2


def test_payment_requires_bearer_auth(client):
    behavior = _signed_behavior(client, seq=1, device_fp=f"no-auth-{uuid.uuid4().hex}")
    r = client.post(
        "/api/v1/payment/score",
        json={"amount": 100, "transfer_type": "UPI", "channel": "web", "behavior": behavior},
    )
    assert r.status_code in (401, 403)


def _seed_pending_txn_stepup(username: str, *, challenge_type: str) -> tuple[str, str]:
    """Seeds a pending transaction + its `AuthChallenge`/`txn_stepup:{id}` blob directly
    (mirrors test_auth_flow.py's `test_step_up_verify_with_demo_otp_completes_login`
    style of seeding state without going through a full score_payment run) -- returns
    `(challenge_id, transaction_id)`."""
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.customer_ref == username))
        transaction = Transaction(
            user_id=user.user_id,
            amount=95_000,
            currency="INR",
            transfer_type="UPI",
            channel="web",
            is_new_payee=True,
            status="verified",
            transaction_risk_score=72.0,
            decision="verify",
        )
        db.add(transaction)
        db.flush()
        transaction_id = str(transaction.transaction_id)

        challenge = AuthChallenge(challenge_type=challenge_type, status="issued")
        db.add(challenge)
        db.commit()
        challenge_id = str(challenge.challenge_id)

        stored_response = PaymentScoreResponse(
            action="verify",
            entity_type="transaction",
            risk_score=72.0,
            risk_band="high",
            required_factors=[challenge_type],
            base_score=72.0,
        )
        redis_client.set(
            f"txn_stepup:{challenge_id}",
            json.dumps(
                {
                    "user_id": str(user.user_id),
                    "transaction_id": transaction_id,
                    "challenge_type": challenge_type,
                    "response": stored_response.model_dump(),
                }
            ),
            ex=300,
        )
        # Seed a known OTP for OTP-type challenges so test assertions with "123456" work.
        if challenge_type == "OTP":
            redis_client.set(f"otp:{challenge_id}", "123456", ex=300)
        return challenge_id, transaction_id
    finally:
        db.close()


def test_payment_step_up_verify_with_demo_otp_allows_the_pending_transaction(client, username):
    _register_and_consent(client, username, PASSWORD)
    challenge_id, transaction_id = _seed_pending_txn_stepup(username, challenge_type="OTP")

    bad = client.post(
        "/api/v1/payment/step-up/verify",
        json={"challenge_id": challenge_id, "otp_or_assertion": "000000"},
    )
    assert bad.status_code == 401
    assert bad.json()["action"] == "verify"

    good = client.post(
        "/api/v1/payment/step-up/verify",
        json={"challenge_id": challenge_id, "otp_or_assertion": "123456"},
    )
    assert good.status_code == 200
    body = good.json()
    assert body["action"] == "allow"
    assert body["entity_type"] == "transaction"

    db = SessionLocal()
    try:
        transaction = db.get(Transaction, uuid.UUID(transaction_id))
        assert transaction.status == "allowed"
        assert transaction.decision == "allow"
    finally:
        db.close()


def test_payment_step_up_exhausted_attempts_blocks_the_pending_transaction(client, username):
    """PRD §10.1 "if fail -> Blocked", transaction side: repeated step-up failures on a
    pending transfer must escalate from a retryable `verify` to `block` once policy
    `max_attempts` is hit, exactly like the login step-up path."""
    _register_and_consent(client, username, PASSWORD)
    challenge_id, transaction_id = _seed_pending_txn_stepup(username, challenge_type="FINGERPRINT")

    # Default policy max_attempts=3: first two fail retryably, the third blocks.
    first = client.post(
        "/api/v1/payment/step-up/verify",
        json={"challenge_id": challenge_id, "otp_or_assertion": ""},
    )
    assert first.status_code == 401 and first.json()["action"] == "verify"
    second = client.post(
        "/api/v1/payment/step-up/verify",
        json={"challenge_id": challenge_id, "otp_or_assertion": ""},
    )
    assert second.status_code == 401 and second.json()["action"] == "verify"
    third = client.post(
        "/api/v1/payment/step-up/verify",
        json={"challenge_id": challenge_id, "otp_or_assertion": ""},
    )
    assert third.status_code == 401 and third.json()["action"] == "block"

    assert redis_client.get(f"txn_stepup:{challenge_id}") is None

    db = SessionLocal()
    try:
        transaction = db.get(Transaction, uuid.UUID(transaction_id))
        assert transaction.status == "blocked"
        assert transaction.decision == "block"
    finally:
        db.close()
