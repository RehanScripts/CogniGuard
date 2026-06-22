"""Phase 30 acceptance check, against the real running app -- admin-track JWT login +
deps.require_role RBAC over /api/v1/admin/*. Mirrors test_banking.py's live-infra
pattern. Relies on scripts.seed_demo having seeded admin@cogniguard.dev (role=admin)
and analyst@cogniguard.dev (role=analyst)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.kafka_client import ping as kafka_ping
from app.main import app
from app.redis_client import ping as redis_ping
from app.s3_client import ping as s3_ping
from scripts.seed_demo import ADMIN_EMAIL, ADMIN_PASSWORD, ANALYST_EMAIL, ANALYST_PASSWORD

pytestmark = pytest.mark.skipif(
    not (redis_ping() and kafka_ping() and s3_ping()), reason="live infra not reachable"
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _login(client: TestClient, email: str, password: str) -> dict:
    r = client.post("/api/v1/admin/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def test_admin_login_issues_role_scoped_token(client):
    body = _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert body["role"] == "admin"
    assert body["token"]


def test_analyst_login_issues_role_scoped_token(client):
    body = _login(client, ANALYST_EMAIL, ANALYST_PASSWORD)
    assert body["role"] == "analyst"


def test_login_rejects_bad_password(client):
    r = client.post(
        "/api/v1/admin/login", json={"email": ADMIN_EMAIL, "password": "wrong-password"}
    )
    assert r.status_code == 401


def test_login_rejects_unknown_email(client):
    r = client.post(
        "/api/v1/admin/login", json={"email": "nobody@cogniguard.dev", "password": "whatever"}
    )
    assert r.status_code == 401


def test_admin_endpoints_require_bearer_auth(client):
    for path in ("/api/v1/admin/events", "/api/v1/admin/policy", "/api/v1/admin/cases"):
        r = client.get(path)
        assert r.status_code in (401, 403), path


def test_analyst_token_can_read_events_but_not_write_policy(client):
    token = _login(client, ANALYST_EMAIL, ANALYST_PASSWORD)["token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/v1/admin/events", headers=headers)
    assert r.status_code == 200

    r2 = client.put("/api/v1/admin/policy", json={}, headers=headers)
    assert r2.status_code == 403


def test_admin_token_can_read_and_write_policy(client):
    token = _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)["token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/v1/admin/policy", headers=headers)
    assert r.status_code == 200

    r2 = client.put("/api/v1/admin/policy", json=r.json()["active_policy"], headers=headers)
    assert r2.status_code == 200


def test_customer_session_token_cannot_access_admin_endpoints(client):
    """A customer-track JWT (no `kind: admin` claim) must never satisfy require_role --
    the two token tracks are deliberately disjoint (Phase 30)."""
    import datetime as dt
    import uuid

    from app.schemas.behavior import (
        ActionBlock,
        BehaviorPayload,
        DeviceInfo,
        KeyEvent,
        KeystrokeBlock,
    )
    from app.services import integrity

    username = f"adminauthtest-{uuid.uuid4().hex[:12]}"
    password = "Passw0rd!1"
    r = client.post("/api/v1/auth/register", json={"username": username, "password": password})
    assert r.status_code == 201
    r2 = client.post(
        "/api/v1/auth/consent",
        json={"username": username, "action": "GRANT", "consent_version": "v1"},
    )
    assert r2.status_code == 200

    nonce = client.get("/api/v1/auth/nonce").json()["nonce"]
    payload = BehaviorPayload(
        channel="web",
        source="web_sdk",
        nonce=nonce,
        seq=1,
        ts=dt.datetime.now(dt.timezone.utc).isoformat(),
        integrity_sig="placeholder",
        device=DeviceInfo(
            fingerprint=f"device-{username}",
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

    r3 = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, "behavior": payload.model_dump()},
    )
    assert r3.status_code == 200
    body = r3.json()
    if body["action"] != "allow":
        pytest.skip("login did not return allow with the current model state")

    headers = {"Authorization": f"Bearer {body['session_token']}"}
    r4 = client.get("/api/v1/admin/events", headers=headers)
    assert r4.status_code == 401
