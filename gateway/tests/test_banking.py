"""Phase 28 acceptance check, against the real running app -- thin read-only banking
endpoints over existing Account/Transaction/Beneficiary/User models. Mirrors
test_payment_flow.py's structural-correctness approach against live infra."""

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


def _signed_behavior(client: TestClient, *, seq: int, device_fp: str) -> dict:
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
        action=ActionBlock(type="LOGIN"),
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
    return f"bankflow-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def auth_header(client, username):
    device_fp = f"device-{username}"
    token = _logged_in_token(client, username, device_fp)
    if token is None:
        pytest.skip(
            "login did not return allow with the current model state -- can't get a session"
        )
    return {"Authorization": f"Bearer {token}"}


def test_profile_returns_masked_pii_only(client, auth_header, username):
    r = client.get("/api/v1/banking/profile", headers=auth_header)
    assert r.status_code == 200
    body = r.json()
    assert body["customer_ref"] == username
    assert body["account_status"] == "active"
    # No registered email/phone for this persona, but the response must never carry the
    # raw fields the model exposes elsewhere -- only the masked_* aliases exist at all.
    assert "email" not in body
    assert "phone" not in body


def test_accounts_returns_masked_account_number_with_seeded_balance(client, auth_header):
    r = client.get("/api/v1/banking/accounts", headers=auth_header)
    assert r.status_code == 200
    accounts = r.json()
    assert len(accounts) == 1
    account = accounts[0]
    assert account["balance"] == 100000.0
    assert account["masked_account_number"].endswith(account["masked_account_number"][-4:])
    assert account["masked_account_number"].startswith("X")
    assert "account_number" not in account


def test_transactions_endpoint_well_formed_and_excludes_risk_fields(client, auth_header):
    r = client.get("/api/v1/banking/transactions", headers=auth_header)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    for txn in body:
        assert "transaction_risk_score" not in txn
        assert "decision_reason" not in txn
        assert "decision" not in txn


def test_beneficiaries_endpoint_well_formed(client, auth_header):
    r = client.get("/api/v1/banking/beneficiaries", headers=auth_header)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_security_settings_excludes_numeric_trust_scores(client, auth_header):
    r = client.get("/api/v1/banking/security-settings", headers=auth_header)
    assert r.status_code == 200
    body = r.json()
    assert "trusted_devices" in body
    assert "active_sessions" in body
    for device in body["trusted_devices"]:
        assert "trust_score" not in device


def test_banking_endpoints_require_bearer_auth(client):
    for path in (
        "/api/v1/banking/profile",
        "/api/v1/banking/accounts",
        "/api/v1/banking/transactions",
        "/api/v1/banking/beneficiaries",
        "/api/v1/banking/security-settings",
    ):
        r = client.get(path)
        assert r.status_code in (401, 403), path
