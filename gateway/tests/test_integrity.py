"""Phase 8 acceptance check: nonce/HMAC/seq/skew anti-replay (Implementation.md line 499)."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app.redis_client import ping, redis_client
from app.schemas.behavior import ActionBlock, BehaviorPayload, DeviceInfo, KeyEvent, KeystrokeBlock
from app.services import integrity

pytestmark = pytest.mark.skipif(not ping(), reason="Redis not reachable")


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _signed_payload(
    nonce: str, seq: int, *, ts: str | None = None, device_fp: str = "fp-default"
) -> BehaviorPayload:
    payload = BehaviorPayload(
        channel="web",
        source="web_sdk",
        nonce=nonce,
        seq=seq,
        ts=ts or _now_iso(),
        integrity_sig="placeholder",
        device=DeviceInfo(fingerprint=device_fp),
        action=ActionBlock(type="LOGIN"),
        keystroke=KeystrokeBlock(events=[KeyEvent(key="x", down=10, up=90)], field_id="username"),
    )
    payload.integrity_sig = integrity.compute_signature(payload)
    return payload


@pytest.fixture
def binding() -> str:
    return f"test-binding-{uuid.uuid4().hex}"


def test_valid_signed_payload_passes(binding):
    nonce, _ = integrity.issue_nonce(redis=redis_client)
    payload = _signed_payload(nonce, 1, device_fp=binding)
    ok, reason = integrity.verify(payload, seq_binding=binding, redis=redis_client)
    assert ok is True
    assert reason is None


def test_tampered_metrics_fails_hmac(binding):
    nonce, _ = integrity.issue_nonce(redis=redis_client)
    payload = _signed_payload(nonce, 1, device_fp=binding)
    payload.keystroke.field_id = "tampered"  # change metrics after signing
    ok, reason = integrity.verify(payload, seq_binding=binding, redis=redis_client)
    assert ok is False
    assert reason == "HMAC_MISMATCH"


def test_tampered_fingerprint_fails_hmac(binding):
    nonce, _ = integrity.issue_nonce(redis=redis_client)
    payload = _signed_payload(nonce, 1, device_fp=binding)
    payload.device.fingerprint = "someone-elses-device"
    ok, reason = integrity.verify(payload, seq_binding=binding, redis=redis_client)
    assert ok is False
    assert reason == "HMAC_MISMATCH"


def test_unknown_nonce_rejected(binding):
    payload = _signed_payload("never-issued-nonce", 1, device_fp=binding)
    ok, reason = integrity.verify(payload, seq_binding=binding, redis=redis_client)
    assert ok is False
    assert reason == "NONCE_INVALID"


def test_consumed_nonce_rejected_on_replay(binding):
    nonce, _ = integrity.issue_nonce(redis=redis_client)
    payload = _signed_payload(nonce, 1, device_fp=binding)

    ok1, _ = integrity.verify(payload, seq_binding=binding, redis=redis_client)
    assert ok1 is True

    ok2, reason2 = integrity.verify(payload, seq_binding=binding, redis=redis_client)
    assert ok2 is False
    assert reason2 == "NONCE_INVALID"


def test_stale_timestamp_rejected(binding):
    stale_ts = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10)).isoformat()
    nonce, _ = integrity.issue_nonce(redis=redis_client)
    payload = _signed_payload(nonce, 1, ts=stale_ts, device_fp=binding)
    ok, reason = integrity.verify(payload, seq_binding=binding, redis=redis_client)
    assert ok is False
    assert reason == "TIMESTAMP_SKEW"


def test_non_increasing_seq_rejected(binding):
    nonce1, _ = integrity.issue_nonce(redis=redis_client)
    payload1 = _signed_payload(nonce1, 5, device_fp=binding)
    ok1, _ = integrity.verify(payload1, seq_binding=binding, redis=redis_client)
    assert ok1 is True

    nonce2, _ = integrity.issue_nonce(redis=redis_client)
    payload2 = _signed_payload(nonce2, 5, device_fp=binding)  # same seq, not increasing
    ok2, reason2 = integrity.verify(payload2, seq_binding=binding, redis=redis_client)
    assert ok2 is False
    assert reason2 == "SEQ_REPLAY"


def test_successful_verify_advances_seq_floor(binding):
    nonce, _ = integrity.issue_nonce(redis=redis_client)
    payload = _signed_payload(nonce, 7, device_fp=binding)
    ok, _ = integrity.verify(payload, seq_binding=binding, redis=redis_client)
    assert ok is True
    assert int(redis_client.get(f"seq:{binding}")) == 7
