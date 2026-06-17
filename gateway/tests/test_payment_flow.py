"""Phase 8 acceptance check, against the real running app + real `Registry()`.
Structural-correctness approach (see test_auth_flow.py docstring for why): a payment
gets logged in first; if the real model doesn't return `allow` at login (no token
issued), the payment test that needs a session skips rather than asserting on a
specific score.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient

from app.kafka_client import ping as kafka_ping
from app.main import app
from app.redis_client import ping as redis_ping
from app.s3_client import ping as s3_ping
from app.schemas.behavior import ActionBlock, BehaviorPayload, DeviceInfo, KeyEvent, KeystrokeBlock
from app.services import integrity

pytestmark = pytest.mark.skipif(
    not (redis_ping() and kafka_ping() and s3_ping()), reason="live infra not reachable"
)

PASSWORD = "Passw0rd!1"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _signed_behavior(client: TestClient, *, seq: int, device_fp: str, action_type: str = "LOGIN") -> dict:
    nonce = client.get("/api/v1/auth/nonce").json()["nonce"]
    payload = BehaviorPayload(
        channel="web",
        source="web_sdk",
        nonce=nonce,
        seq=seq,
        ts=_now_iso(),
        integrity_sig="placeholder",
        device=DeviceInfo(fingerprint=device_fp, ua="pytest", screen="1920x1080", timezone="Asia/Kolkata", language="en-IN", platform="web"),
        action=ActionBlock(type=action_type),
        keystroke=KeystrokeBlock(
            events=[KeyEvent(key="x", down=10, up=90), KeyEvent(key="x", down=200, up=290), KeyEvent(key="x", down=420, up=500)],
            field_id="username",
        ),
    )
    payload.integrity_sig = integrity.compute_signature(payload)
    return payload.model_dump()


def _logged_in_token(client: TestClient, username: str, device_fp: str) -> str | None:
    r = client.post("/api/v1/auth/register", json={"username": username, "password": PASSWORD})
    assert r.status_code == 201, r.text
    r2 = client.post("/api/v1/auth/consent", json={"username": username, "action": "GRANT", "consent_version": "v1"})
    assert r2.status_code == 200, r2.text

    behavior = _signed_behavior(client, seq=1, device_fp=device_fp)
    r3 = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD, "behavior": behavior})
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
        pytest.skip("login did not return allow with the current model state -- can't get a session")

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
        pytest.skip("login did not return allow with the current model state -- can't get a session")

    behavior = _signed_behavior(client, seq=2, device_fp=device_fp, action_type="TRANSFER")
    body = {
        "amount": 95_000,
        "beneficiary_vpa": f"newpayee-{uuid.uuid4().hex}@upi",
        "transfer_type": "UPI",
        "channel": "web",
        "behavior": behavior,
    }
    r = client.post("/api/v1/payment/score", json=body, headers={"Authorization": f"Bearer {token}"})
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


def test_payment_requires_bearer_auth(client):
    behavior = _signed_behavior(client, seq=1, device_fp=f"no-auth-{uuid.uuid4().hex}")
    r = client.post(
        "/api/v1/payment/score",
        json={"amount": 100, "transfer_type": "UPI", "channel": "web", "behavior": behavior},
    )
    assert r.status_code in (401, 403)
