"""Phase 8 acceptance check: Track A IP/device brute-force escalation, never the account."""

from __future__ import annotations

import uuid

import pytest

from app.db import SessionLocal
from app.redis_client import ping, redis_client
from app.services import hardening

pytestmark = pytest.mark.skipif(not ping(), reason="Redis not reachable")

POLICY = {"hardening": {"delay_after": 3, "captcha_after": 4, "lock_after": 5, "lock_minutes": 15}}


@pytest.fixture
def ip_device():
    ip = f"10.0.0.{uuid.uuid4().int % 250}"
    device_fp = f"hardening-test-{uuid.uuid4().hex}"
    yield ip, device_fp
    redis_client.delete(
        f"fail:ip:{ip}",
        f"fail:device:{device_fp}",
        f"lock:ip:{ip}",
        f"lock:device:{device_fp}",
    )


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_no_hardening_below_delay_after(db, ip_device):
    ip, device_fp = ip_device
    for _ in range(2):  # below delay_after=3
        result = hardening.register_failure(db, ip, device_fp, None, POLICY, redis=redis_client)
    assert result is None


def test_delay_escalation(db, ip_device):
    ip, device_fp = ip_device
    for _ in range(2):
        hardening.register_failure(db, ip, device_fp, None, POLICY, redis=redis_client)
    result = hardening.register_failure(
        db, ip, device_fp, None, POLICY, redis=redis_client
    )  # 3rd failure
    assert result is not None
    assert result.action == "DELAY"


def test_captcha_escalation(db, ip_device):
    ip, device_fp = ip_device
    for _ in range(3):
        hardening.register_failure(db, ip, device_fp, None, POLICY, redis=redis_client)
    result = hardening.register_failure(
        db, ip, device_fp, None, POLICY, redis=redis_client
    )  # 4th failure
    assert result.action == "CAPTCHA"


def test_lockout_after_threshold_locks_ip_and_device_never_account(db, ip_device):
    ip, device_fp = ip_device
    for _ in range(4):
        hardening.register_failure(db, ip, device_fp, None, POLICY, redis=redis_client)
    result = hardening.register_failure(
        db, ip, device_fp, None, POLICY, redis=redis_client
    )  # 5th failure
    assert result.action == "LOCKOUT"

    lock = hardening.is_locked(ip, device_fp, redis=redis_client)
    assert lock is not None
    assert lock.action == "LOCKOUT"
    assert lock.scope in ("ip", "device")

    # Never an account-scoped lock -- only ip/device keys exist in Redis.
    assert redis_client.exists(f"lock:user:{device_fp}") == 0


def test_reset_clears_counters(db, ip_device):
    ip, device_fp = ip_device
    for _ in range(3):
        hardening.register_failure(db, ip, device_fp, None, POLICY, redis=redis_client)
    hardening.reset(ip, device_fp, redis=redis_client)
    result = hardening.register_failure(db, ip, device_fp, None, POLICY, redis=redis_client)
    assert result is None  # back below delay_after after reset


def test_clean_different_ip_device_not_locked(db, ip_device):
    ip, device_fp = ip_device
    for _ in range(5):
        hardening.register_failure(db, ip, device_fp, None, POLICY, redis=redis_client)
    assert hardening.is_locked(ip, device_fp, redis=redis_client) is not None
    assert hardening.is_locked("192.168.1.1", "clean-device", redis=redis_client) is None
