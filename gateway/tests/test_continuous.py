"""Phase 9 acceptance check (Implementation.md lines 559-567): `/behavior/ingest`
continuous re-scoring + the SOC WebSocket feed. Same structural-correctness approach
as `test_auth_flow.py`/`test_payment_flow.py` -- the `very_high` branch is forced via
monkeypatching `stack.score` (mirrors `test_auth_flow.py`'s step-up-state-seeding
trick) rather than depending on the real model producing a specific verdict.
"""

from __future__ import annotations

import datetime as dt
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.kafka_client import ping as kafka_ping
from app.main import app
from app.models.session import Session as SessionModel
from app.redis_client import ping as redis_ping
from app.s3_client import ping as s3_ping
from app.schemas.behavior import ActionBlock, BehaviorPayload, DeviceInfo, KeyEvent, KeystrokeBlock
from app.schemas.scoring import ScoreResult
from app.services import behavior_flow, integrity
from app.utils import security

pytestmark = pytest.mark.skipif(
    not (redis_ping() and kafka_ping() and s3_ping()), reason="live infra not reachable"
)

PASSWORD = "Passw0rd!1"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _signed_behavior(
    client: TestClient, *, seq: int, device_fp: str, action_type: str = "VIEW_BALANCE"
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


def _logged_in(client: TestClient, username: str, device_fp: str) -> tuple[str, str] | None:
    """Returns (session_token, session_id) on `allow`, else None."""
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
    if body["action"] != "allow":
        return None
    claims = security.decode_jwt(body["session_token"])
    return body["session_token"], claims["session_id"]


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def username():
    return f"continuous-{uuid.uuid4().hex[:12]}"


def test_ingest_returns_well_formed_allow_or_verify(client, username):
    device_fp = f"device-{username}"
    logged_in = _logged_in(client, username, device_fp)
    if logged_in is None:
        pytest.skip(
            "login did not return allow with the current model state -- can't get a session"
        )
    token, _session_id = logged_in

    behavior = _signed_behavior(client, seq=2, device_fp=device_fp)
    r = client.post(
        "/api/v1/behavior/ingest",
        json=behavior,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["action"] in ("allow", "verify")
    assert isinstance(body["reauth"], bool)


def test_nonce_reuse_returns_409(client, username):
    device_fp = f"device-{username}"
    logged_in = _logged_in(client, username, device_fp)
    if logged_in is None:
        pytest.skip(
            "login did not return allow with the current model state -- can't get a session"
        )
    token, _session_id = logged_in

    behavior = _signed_behavior(client, seq=2, device_fp=device_fp)
    r1 = client.post(
        "/api/v1/behavior/ingest", json=behavior, headers={"Authorization": f"Bearer {token}"}
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/api/v1/behavior/ingest", json=behavior, headers={"Authorization": f"Bearer {token}"}
    )
    assert r2.status_code == 409


def test_very_high_terminates_session_and_denylists_jwt(client, username, monkeypatch):
    device_fp = f"device-{username}"
    logged_in = _logged_in(client, username, device_fp)
    if logged_in is None:
        pytest.skip(
            "login did not return allow with the current model state -- can't get a session"
        )
    token, session_id = logged_in

    def _forced_very_high(bundle, *, policy, registry, txn_context=None, redis=None):
        return ScoreResult(
            behavior_score=0.95,
            transaction_score=0.95,
            final_risk_score=95.0,
            base_score=95.0,
            risk_band="very_high",
            model_version="forced-test",
        )

    monkeypatch.setattr(behavior_flow.stack, "score", _forced_very_high)

    behavior = _signed_behavior(client, seq=2, device_fp=device_fp)
    r = client.post(
        "/api/v1/behavior/ingest", json=behavior, headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["action"] == "verify"
    assert body["reauth"] is True

    db = SessionLocal()
    try:
        session = db.get(SessionModel, uuid.UUID(session_id))
        assert session is not None
        assert session.status == "terminated"
        assert security.is_revoked(session.jwt_id)
    finally:
        db.close()

    behavior2 = _signed_behavior(client, seq=3, device_fp=device_fp)
    r2 = client.post(
        "/api/v1/behavior/ingest", json=behavior2, headers={"Authorization": f"Bearer {token}"}
    )
    assert r2.status_code == 401


def test_soc_feed_receives_a_message_after_a_login(client, username):
    device_fp = f"device-{username}"
    with client.websocket_connect("/ws/soc-feed") as ws:
        # The broadcaster's Kafka consumer reads from "latest" (a live tail, not a
        # backlog replay -- see services/broadcaster.py) and needs a brief moment to
        # complete partition assignment after the app's lifespan starts it; without
        # this grace period a login fired immediately after connecting can race ahead
        # of that assignment and never be seen.
        time.sleep(1.5)
        _logged_in(client, username, device_fp)

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(ws.receive_text)
            try:
                message = future.result(timeout=10)
            except FutureTimeoutError:
                pytest.fail("no message arrived on /ws/soc-feed within 10s of a login")
        assert message
