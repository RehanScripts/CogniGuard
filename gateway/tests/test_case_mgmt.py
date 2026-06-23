"""Phase 9 acceptance check (Implementation.md lines 559-567): cases auto-open on
`block`/`very_high`, analyst resolution writes a labeled row to S3, and `/admin/cases`
GET/PATCH are wired to the same service.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.kafka_client import ping as kafka_ping
from app.main import app
from app.redis_client import ping as redis_ping
from app.s3_client import get_s3
from app.s3_client import ping as s3_ping
from app.schemas.admin import CaseUpdate
from app.services import case_mgmt
from app.utils import security
from app.models.user import User
from scripts.seed_demo import ADMIN_EMAIL, ADMIN_PASSWORD

pytestmark = pytest.mark.skipif(
    not (redis_ping() and kafka_ping() and s3_ping()), reason="live infra not reachable"
)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def _make_user(db) -> User:
    user = User(
        customer_ref=f"case-{uuid.uuid4().hex[:12]}", password_hash=security.hash_password("x")
    )
    db.add(user)
    db.commit()
    return user


def test_maybe_open_case_is_noop_on_allow(db):
    user = _make_user(db)
    case = case_mgmt.maybe_open_case(
        db, user_id=user.user_id, transaction_id=None, risk_band="low", action="allow"
    )
    assert case is None


def test_maybe_open_case_opens_on_very_high(db):
    user = _make_user(db)
    case = case_mgmt.maybe_open_case(
        db, user_id=user.user_id, transaction_id=None, risk_band="very_high", action="block"
    )
    assert case is not None
    assert case.status == "open"
    assert case.severity == "critical"


def test_update_case_to_confirmed_fraud_writes_label_to_s3(db):
    user = _make_user(db)
    case = case_mgmt.maybe_open_case(
        db, user_id=user.user_id, transaction_id=None, risk_band="very_high", action="block"
    )
    updated = case_mgmt.update_case(
        db, case.case_id, CaseUpdate(status="confirmed_fraud", assigned_to="analyst1")
    )
    assert updated.status == "confirmed_fraud"
    assert updated.resolved_at is not None

    key = f"labels/confirmed_fraud/{case.case_id}.json"
    obj = get_s3().get_object(Bucket=settings.s3_bucket, Key=key)
    body = json.loads(obj["Body"].read())
    assert body["label"] == "confirmed_fraud"
    assert body["user_id"] == str(user.user_id)


def test_admin_cases_endpoint_list_and_patch(db):
    user = _make_user(db)
    case = case_mgmt.maybe_open_case(
        db, user_id=user.user_id, transaction_id=None, risk_band="very_high", action="block"
    )

    with TestClient(app) as client:
        login = client.post(
            "/api/v1/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['token']}"}
        r = client.get("/api/v1/admin/cases", headers=headers, params={"status": "open"})
        assert r.status_code == 200
        assert any(c["case_id"] == str(case.case_id) for c in r.json())

        r2 = client.patch(
            f"/api/v1/admin/cases/{case.case_id}",
            headers=headers,
            json={"status": "false_positive"},
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "false_positive"

        r3 = client.get("/api/v1/admin/cases", params={"status": "open"})
        assert r3.status_code == 401
