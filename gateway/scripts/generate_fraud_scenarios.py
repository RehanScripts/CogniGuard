"""Generate signed fixture files for the Implementation.md §5.2/§7.1 demo script.
Runnable standalone:

    python -m scripts.generate_fraud_scenarios

Nonces are single-use and TTL'd in Redis, and `ts` is skew-checked against wall-clock
time (`settings.integrity_skew_s`, default 30s) -- so a fixture file is only valid for
~30 seconds after it's written, not just "until its nonce expires." `entrypoint.sh`
regenerates these on every container start so a demo beginning right after `docker
compose up` has fresh ones, but if more than ~30s elapses before a fixture is actually
used (build time, manual delay, a long docker-compose-up wait), re-run this script
immediately before curling/replaying a fixture: `python -m scripts.generate_fraud_scenarios`.
These are not meant to be permanently-valid committed artifacts.

`BehaviorPayload` carries no geo field (geo enters scoring server-side via
`FeatureReadContext`, never the client payload) -- the genuine/impostor distinction
below is carried entirely by `device.fingerprint` + keystroke rhythm, not lat/lon.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import random
import time

from app.redis_client import redis_client
from app.schemas.behavior import ActionBlock, BehaviorPayload, DeviceInfo, KeyEvent, KeystrokeBlock
from app.services import integrity
from scripts.seed_demo import GENUINE_DEVICE_FP, IMPOSTOR_DEVICE_FP, SCAMMER_VPA

logger = logging.getLogger("cogniguard.generate_fraud_scenarios")

FIXTURES_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures"))
REPLAY_DEVICE_FP = "replay-demo-device"

_RNG = random.Random(1337)


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _login_seq() -> int:
    """The login path binds `seq` to the device fingerprint (auth_flow.login,
    seq_binding=device_fp) -- and the genuine/impostor/replay fingerprints below are
    fixed, reused identities by design (that's the whole point of "known device").
    A small fixed seq would permanently SEQ_REPLAY after the very first successful
    login against that fingerprint, surviving even a fresh regeneration of this file
    (regenerating only mints a new nonce, it can't roll back the seq floor). Wall-clock
    milliseconds are always greater than whatever floor a previous demo/test run left
    behind for that fingerprint."""
    return int(time.time() * 1000)


def _steady_keystrokes() -> list[KeyEvent]:
    """Low-variance dwell/flight -- a steady "genuine" typing rhythm."""
    events: list[KeyEvent] = []
    t = 0.0
    for _ in range(8):
        down = t + _RNG.uniform(-3, 3)
        up = down + 80 + _RNG.uniform(-5, 5)
        events.append(KeyEvent(key="x", down=max(down, 0.0), up=up))
        t = up + 120 + _RNG.uniform(-5, 5)
    return events


def _erratic_keystrokes() -> list[KeyEvent]:
    """High-variance dwell/flight -- an erratic/"impostor" typing rhythm."""
    events: list[KeyEvent] = []
    t = 0.0
    for _ in range(8):
        down = t + _RNG.uniform(-50, 50)
        up = down + _RNG.uniform(40, 400)
        events.append(KeyEvent(key="x", down=max(down, 0.0), up=up))
        t = up + _RNG.uniform(50, 600)
    return events


def _device(device_fp: str) -> DeviceInfo:
    return DeviceInfo(
        fingerprint=device_fp,
        ua="cogniguard-fixture-generator",
        screen="1920x1080",
        timezone="Asia/Kolkata",
        language="en-IN",
        platform="web",
    )


def _build_signed_payload(
    *, device_fp: str, action_type: str, seq: int, events: list[KeyEvent], field_id: str
) -> BehaviorPayload:
    nonce, _ = integrity.issue_nonce(redis=redis_client)
    payload = BehaviorPayload(
        channel="web",
        source="web_sdk",
        nonce=nonce,
        seq=seq,
        ts=_now_iso(),
        integrity_sig="placeholder",
        device=_device(device_fp),
        action=ActionBlock(type=action_type),
        keystroke=KeystrokeBlock(events=events, field_id=field_id),
    )
    payload.integrity_sig = integrity.compute_signature(payload)
    return payload


def login_genuine() -> dict:
    return _build_signed_payload(
        device_fp=GENUINE_DEVICE_FP,
        action_type="LOGIN",
        seq=_login_seq(),
        events=_steady_keystrokes(),
        field_id="username",
    ).model_dump(mode="json")


def login_impostor() -> dict:
    return _build_signed_payload(
        device_fp=IMPOSTOR_DEVICE_FP,
        action_type="LOGIN",
        seq=_login_seq(),
        events=_erratic_keystrokes(),
        field_id="username",
    ).model_dump(mode="json")


def ingest_hijack() -> dict:
    """Mid-session behavior swap for /behavior/ingest -- must be POSTed as the first
    ingest call of a fresh session so its high `seq` clears that session's seq floor."""
    return _build_signed_payload(
        device_fp=IMPOSTOR_DEVICE_FP,
        action_type="VIEW_BALANCE",
        seq=99,
        events=_erratic_keystrokes(),
        field_id="balance",
    ).model_dump(mode="json")


def txn_app_fraud() -> dict:
    """A full PaymentScoreRequest body (not just the inner BehaviorPayload) -- a
    self-contained curl target. Genuine rhythm deliberately: the coercion case is
    "behavior genuine, intent dangerous", not an impostor."""
    behavior = _build_signed_payload(
        device_fp=GENUINE_DEVICE_FP,
        action_type="TRANSFER",
        seq=1,
        events=_steady_keystrokes(),
        field_id="amount",
    )
    return {
        "amount": 50000,
        "beneficiary_vpa": SCAMMER_VPA,
        "transfer_type": "UPI",
        "channel": "web",
        "behavior": behavior.model_dump(mode="json"),
    }


def replay_login() -> dict:
    """A normal valid signed login payload. The "replay" demo is performed live by
    POSTing this file twice in a row -- the second call hits NONCE_INVALID -> 400
    INTEGRITY_REJECT. Own device fingerprint to avoid seq/nonce collisions with
    login_genuine.json if both are used in the same demo session."""
    return _build_signed_payload(
        device_fp=REPLAY_DEVICE_FP,
        action_type="LOGIN",
        seq=_login_seq(),
        events=_steady_keystrokes(),
        field_id="username",
    ).model_dump(mode="json")


def _write(name: str, body: dict) -> str:
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    path = os.path.join(FIXTURES_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(body, f, indent=2)
        f.write("\n")
    return path


def main() -> dict[str, str]:
    written: dict[str, str] = {}
    for name, builder in (
        ("login_genuine.json", login_genuine),
        ("login_impostor.json", login_impostor),
        ("ingest_hijack.json", ingest_hijack),
        ("txn_app_fraud.json", txn_app_fraud),
        ("replay_login.json", replay_login),
    ):
        path = _write(name, builder())
        written[name] = path
        logger.info("wrote %s", path)
    return written


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    for name, path in main().items():
        print(f"{name}: {path}")
