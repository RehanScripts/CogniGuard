"""Phase 11: the 5 demo fixtures (Implementation.md §5.2) must be genuinely valid,
correctly-signed payloads, and the replay fixture must actually demonstrate
anti-replay rejection on a second use.
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from app.kafka_client import ping as kafka_ping
from app.main import app
from app.redis_client import ping as redis_ping
from app.s3_client import ping as s3_ping
from app.schemas.behavior import BehaviorPayload
from app.schemas.payment import PaymentScoreRequest
from app.services import integrity
from scripts import generate_fraud_scenarios as gfs
from scripts import seed_demo

pytestmark = pytest.mark.skipif(
    not (redis_ping() and kafka_ping() and s3_ping()), reason="live infra not reachable"
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize(
    "builder",
    [gfs.login_genuine, gfs.login_impostor, gfs.ingest_hijack, gfs.replay_login],
)
def test_behavior_fixture_is_valid_and_correctly_signed(builder):
    body = builder()
    payload = BehaviorPayload.model_validate(body)
    assert payload.integrity_sig == integrity.compute_signature(payload)


def test_txn_app_fraud_fixture_is_valid_and_correctly_signed():
    body = gfs.txn_app_fraud()
    req = PaymentScoreRequest.model_validate(body)
    assert req.amount == 50000
    assert req.beneficiary_vpa == seed_demo.SCAMMER_VPA
    assert req.behavior.integrity_sig == integrity.compute_signature(req.behavior)


def test_main_writes_all_five_fixtures():
    written = gfs.main()
    assert set(written) == {
        "login_genuine.json",
        "login_impostor.json",
        "ingest_hijack.json",
        "txn_app_fraud.json",
        "replay_login.json",
    }
    for path in written.values():
        assert os.path.isfile(path)


def test_replaying_the_same_login_payload_is_rejected(client):
    # A fresh, unique device fingerprint -- not one of the fixed fixture fingerprints --
    # so this test's seq/nonce state can never collide with another test or a previous
    # run against the same shared live Redis (the committed fixtures use fixed
    # fingerprints by design, for a single live demo session; that's a different
    # context than a repeatable automated test).
    behavior = gfs._build_signed_payload(
        device_fp=f"replay-test-{uuid.uuid4().hex}",
        action_type="LOGIN",
        seq=1,
        events=gfs._steady_keystrokes(),
        field_id="username",
    ).model_dump()

    seed_demo.main()  # ensure the `genuine` user exists to log in as
    r1 = client.post(
        "/api/v1/auth/login",
        json={
            "username": seed_demo.GENUINE_USERNAME,
            "password": seed_demo.GENUINE_PASSWORD,
            "behavior": behavior,
        },
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/api/v1/auth/login",
        json={
            "username": seed_demo.GENUINE_USERNAME,
            "password": seed_demo.GENUINE_PASSWORD,
            "behavior": behavior,
        },
    )
    assert r2.status_code == 400
    assert r2.json().get("integrity") == "INTEGRITY_REJECT"
