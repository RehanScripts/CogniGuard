#!/usr/bin/env python3
"""CogniGuard Demo Scenario Runner.

Handles the four scenarios that require HMAC-signed BehaviorPayloads or admin API
access.  All other scenarios (happy path, cold-start, brute-force, step-up, factory
reset) are driven via the web app / SOC dashboard — see the printed guide at the top.

Usage (from the project root, with Docker stack running):
    python gateway/scripts/demo_scenarios.py                    # print menu + run all
    python gateway/scripts/demo_scenarios.py --scenario ato
    python gateway/scripts/demo_scenarios.py --scenario replay
    python gateway/scripts/demo_scenarios.py --scenario coercion
    python gateway/scripts/demo_scenarios.py --scenario shap

Requires only stdlib — no extra packages.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac as _hmac
import json
import sys
import urllib.error
import urllib.request
from typing import Any

# ── Config (must match .env / config.py) ─────────────────────────────────────
BASE = "http://localhost:8000/api/v1"
JWT_SECRET = "change_me_dev_only_super_secret"

# Seeded personas (seed_demo.py)
GENUINE_USER = "genuine"
GENUINE_PASS = "Passw0rd!"
GENUINE_FP = "known-mumbai-device-001"

IMPOSTOR_FP = "impostor-tallinn-device-001"

ADMIN_EMAIL = "admin@cogniguard.dev"
ADMIN_PASS = "Passw0rd!"

SCAMMER_VPA = "scammer@upi"


# ── HTTP helpers ──────────────────────────────────────────────────────────────


def _http(method: str, path: str, body: dict | None = None, token: str | None = None) -> dict:
    data = json.dumps(body).encode() if body else None
    headers: dict[str, str] = {}
    if data:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return {"status": r.status, "body": json.loads(r.read().decode())}
    except urllib.error.HTTPError as e:
        try:
            body_text = e.read().decode()
            return {"status": e.code, "body": json.loads(body_text)}
        except Exception:
            return {"status": e.code, "body": {"detail": str(e)}}


def _get_nonce() -> str:
    r = _http("GET", "/auth/nonce")
    return r["body"]["nonce"]


# ── HMAC / signing helpers (mirrors integrity.py exactly) ────────────────────


def _canonical_metrics(
    channel: str,
    source: str,
    action_type: str,
    derived: dict | None,
    ae_err: float | None,
    ae_ver: str | None,
) -> str:
    metrics: dict[str, Any] = {
        "action": {"type": action_type},
        "ae_model_version": ae_ver,
        "ae_recon_error": ae_err,
        "channel": channel,
        "context": {
            "correction_rate": 0.0,
            "page": "",
            "pre_txn_dwell_ms": 0.0,
            "session_age_s": 0.0,
            "submitted_at": "",
        },
        "derived_features": derived,
        "keystroke": None,
        "mouse": None,
        "source": source,
        "touch": None,
    }
    return json.dumps(metrics, sort_keys=True, separators=(",", ":"))


def _sign(nonce: str, canonical: str, fingerprint: str, ts: str) -> str:
    key = hashlib.sha256((JWT_SECRET + nonce).encode()).digest()
    msg = (nonce + canonical + fingerprint + ts).encode()
    return _hmac.new(key, msg, hashlib.sha256).hexdigest()


def _behavior(
    nonce: str,
    seq: int,
    fingerprint: str,
    channel: str = "mobile",
    source: str = "mobile_edge",
    action_type: str = "LOGIN",
    derived: dict | None = None,
    ae_err: float | None = None,
    ae_ver: str | None = "demo-v1",
) -> dict:
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    canonical = _canonical_metrics(channel, source, action_type, derived, ae_err, ae_ver)
    sig = _sign(nonce, canonical, fingerprint, ts)
    return {
        "channel": channel,
        "source": source,
        "nonce": nonce,
        "seq": seq,
        "ts": ts,
        "integrity_sig": sig,
        "device": {
            "fingerprint": fingerprint,
            "ua": "demo-runner/1.0",
            "screen": "1920x1080",
            "timezone": "Asia/Kolkata",
            "language": "en-IN",
            "platform": channel,
            "is_rooted": False,
            "is_emulator": False,
        },
        "action": {"type": action_type},
        "keystroke": None,
        "mouse": None,
        "touch": None,
        "derived_features": derived,
        "ae_recon_error": ae_err,
        "ae_model_version": ae_ver,
        "context": {
            "submitted_at": "",
            "page": "",
            "pre_txn_dwell_ms": 0.0,
            "session_age_s": 0.0,
            "correction_rate": 0.0,
        },
    }


# ── Scenario helpers ──────────────────────────────────────────────────────────


def _genuine_login(seq: int = 1) -> dict:
    """Login as `genuine` with known device + low AE error (genuine behavior)."""
    nonce = _get_nonce()
    return _http(
        "POST",
        "/auth/login",
        {
            "username": GENUINE_USER,
            "password": GENUINE_PASS,
            "behavior": _behavior(
                nonce,
                seq,
                GENUINE_FP,
                ae_err=0.04,  # very low reconstruction error → genuine
                derived={
                    "typing_speed": 4.5,
                    "key_latency_avg": 110.0,
                    "typing_rhythm_std": 12.0,
                    "hold_time_avg": 80.0,
                    "swipe_velocity_norm": 0.6,
                    "mouse_velocity_mean": 0.8,
                },
            ),
        },
    )


def _admin_token() -> str:
    r = _http("POST", "/admin/login", {"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    if r["status"] != 200:
        print(f"  [!] Admin login failed: {r}")
        sys.exit(1)
    return r["body"]["access_token"]


def _banner(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print("=" * 60)


def _show(label: str, r: dict) -> None:
    b = r["body"]
    print(f"\n  HTTP {r['status']}")
    for key in (
        "action",
        "risk_score",
        "risk_band",
        "reason_codes",
        "amplifiers",
        "integrity",
        "degraded_mode",
        "behavior_score_source",
        "model_version",
    ):
        if key in b:
            print(f"  {key}: {b[key]}")
    print(f"\n  Raw body → {json.dumps(b, indent=2)[:800]}")


# ── Scenarios ─────────────────────────────────────────────────────────────────


def scenario_ato() -> None:
    """Account Takeover: impostor uses stolen creds from unrecognised device."""
    _banner("SCENARIO 2 — Account Takeover (ATO)")
    print("""
  Attacker has stolen `genuine`'s password but uses their own device.
  The impostor fingerprint is NOT in `user:*:known_devices` (by design — seed_demo
  deliberately omits it).  The on-device AE reconstruction error is very high (0.92)
  — different typing rhythm / touch cadence.

  Expected:
    → action: block (or verify at very_high band ≥85)
    → reason_codes: NEW_DEVICE, (possibly) BEHAVIOR_ANOMALY / HIGH_AE_ERROR
    → behavior_score_source: ae  (or fallback to if / degraded_mode if no model)
""")
    nonce = _get_nonce()
    r = _http(
        "POST",
        "/auth/login",
        {
            "username": GENUINE_USER,
            "password": GENUINE_PASS,
            "behavior": _behavior(
                nonce,
                seq=1,
                fingerprint=IMPOSTOR_FP,
                ae_err=0.92,  # high reconstruction error → anomalous behaviour
                derived={
                    "typing_speed": 9.1,  # 2× faster than genuine baseline (4.5)
                    "key_latency_avg": 44.0,  # erratic — much faster than baseline (110ms)
                    "typing_rhythm_std": 2.1,  # suspiciously machine-like (baseline 12.0)
                    "hold_time_avg": 38.0,  # half the genuine 80ms
                    "swipe_velocity_norm": 1.4,  # aggressive swipes (baseline 0.6)
                    "mouse_velocity_mean": 2.2,  # baseline 0.8
                },
            ),
        },
    )
    _show("ATO login result", r)
    print("""
  SOC Dashboard → Live Events:
    • Row with entity_type=login, risk_band=high/very_high, action=block/verify
    • Reason codes panel shows NEW_DEVICE
    • Behavior score source: ae (high reconstruction error)
    • Open case row → SHAP tab → "Explain Score" for AI analysis
""")


def scenario_replay() -> None:
    """Replay attack: second request re-uses the same nonce — must be rejected."""
    _banner("SCENARIO 6 — Replay Attack (Nonce Reuse)")
    print("""
  Simulate a RAT/MITM that captures a signed telemetry payload and replays it.
  The gateway consumes the nonce on first use; the second request with the same
  nonce must return INTEGRITY_REJECT (NONCE_INVALID).

  Expected:
    • Request 1: HTTP 200 / 403  (scored normally — allow / block / verify)
    • Request 2: HTTP 403, integrity=INTEGRITY_REJECT, action=block
""")
    nonce = _get_nonce()
    behavior = _behavior(nonce, seq=1, fingerprint=GENUINE_FP, ae_err=0.04)

    print("\n  → Sending first request (nonce is valid)…")
    r1 = _http(
        "POST",
        "/auth/login",
        {
            "username": GENUINE_USER,
            "password": GENUINE_PASS,
            "behavior": behavior,
        },
    )
    _show("Request 1", r1)

    print("\n  → Re-sending SAME nonce (replay attempt)…")
    r2 = _http(
        "POST",
        "/auth/login",
        {
            "username": GENUINE_USER,
            "password": GENUINE_PASS,
            "behavior": behavior,  # identical payload — nonce already consumed
        },
    )
    _show("Request 2 (replay)", r2)

    ok = r2.get("status") in (400, 403) or r2["body"].get("integrity") == "INTEGRITY_REJECT"
    print(f"\n  Replay rejection: {'✅ PASS' if ok else '❌ FAIL'}")
    print("""
  SOC Dashboard → Live Events:
    • Two rows for the same session; second has integrity=INTEGRITY_REJECT
    • Reason codes: NONCE_INVALID on the blocked row
""")


def scenario_coercion() -> None:
    """APP Fraud / coercion: genuine user + new payee + amount 25× avg → amplifiers fire."""
    _banner("SCENARIO 3 — Coercion / APP Fraud (Digital Arrest)")
    print("""
  Genuine user is socially-engineered (\"digital arrest\" scam) into sending ₹50,000
  to `scammer@upi` — a beneficiary added only 40 minutes ago (seeded by seed_demo).

  The behavior is normal (same typing rhythm), so behavior_score is LOW.
  The TRANSACTION CONTEXT triggers amplifiers:
    • NEW_BENEF_HIGHVAL  ×1.5  (new payee AND amount 25× 30-day avg of ₹2,000)
    • DRAIN              ×1.3  (near account limit)

  Expected:
    → login:   action=allow, risk_band=low
    → payment: action=verify (or block), risk_band=high/very_high
    → amplifiers: NEW_BENEF_HIGHVAL, DRAIN
    → txn_controls: manual_amount=true, coercion_check=true
""")

    # Step 1 — normal genuine login
    print("  Step 1: genuine login with known device…")
    r_login = _genuine_login(seq=1)
    _show("Login result", r_login)
    token = r_login["body"].get("session_token")
    if not token:
        print(
            "  [!] Login did not return session_token — action was:", r_login["body"].get("action")
        )
        print("      If action=verify, complete OTP via: POST /auth/step-up/verify")
        print("      Then re-run — or use the web app for this scenario.")
        return

    # Step 2 — payment to scammer with genuine behaviour
    print("\n  Step 2: transfer ₹50,000 to scammer@upi…")
    nonce2 = _get_nonce()
    r_pay = _http(
        "POST",
        "/payment/score",
        {
            "amount": 50000.0,
            "beneficiary_vpa": SCAMMER_VPA,
            "transfer_type": "UPI",
            "channel": "mobile",
            "behavior": _behavior(
                nonce2,
                seq=2,
                fingerprint=GENUINE_FP,
                action_type="TRANSFER",
                ae_err=0.04,  # still genuine behavior
                derived={
                    "typing_speed": 4.5,
                    "key_latency_avg": 110.0,
                    "typing_rhythm_std": 12.0,
                    "hold_time_avg": 80.0,
                    "swipe_velocity_norm": 0.6,
                    "mouse_velocity_mean": 0.8,
                },
            ),
        },
        token=token,
    )
    _show("Payment result", r_pay)
    print("""
  SOC Dashboard → Live Events:
    • Payment row: entity_type=transaction, amplifiers=NEW_BENEF_HIGHVAL/DRAIN
    • Amplifier Badges component lights up
    • Reason codes: NEW_BENEF_HIGHVAL, DRAIN
    • txn_controls.manual_amount + coercion_check = true
    • Trust Panel still shows high — BEHAVIOR is fine; TRANSACTION CONTEXT is the risk
""")


def scenario_shap() -> None:
    """Analyst SHAP + Groq explain — admin fetches the latest scored event."""
    _banner("SCENARIO 8 — SHAP + Groq AI Explain (SOC workflow)")
    print("""
  Admin gets the latest risk_score row and triggers the SHAP + Groq explanation.
  This is the off-hot-path analyst tool (CLAUDE.md invariant 16).

  If GROQ_API_KEY is set in .env, the response includes ai_explanation.
  Otherwise it gracefully returns SHAP values only.
""")
    admin_tok = _admin_token()

    # Get latest event
    r_events = _http("GET", "/admin/events?limit=5", token=admin_tok)
    events = r_events["body"]
    if not events:
        print("  [!] No scored events found. Run another scenario first.")
        return

    latest = events[0]
    score_id = latest.get("score_id")
    print(f"  Using latest score_id: {score_id}")
    print(
        f"  entity_type={latest.get('entity_type')}, action={latest.get('action')}, "
        f"risk_band={latest.get('risk_band')}, score={latest.get('final_risk_score')}"
    )

    print("\n  Triggering SHAP explanation…")
    r_shap = _http("POST", f"/admin/explain/{score_id}", token=admin_tok)
    body = r_shap["body"]
    print(f"\n  HTTP {r_shap['status']}")
    print(f"  model_version: {body.get('model_version')}")
    print(f"  top_features ({len(body.get('top_features', []))} features):")
    for f in body.get("top_features", [])[:5]:
        print(
            f"    {f['feature']:30s}  SHAP={f['shap_value']:+.4f}"
            + (f"  val={f['feature_value']:.3f}" if f.get("feature_value") is not None else "")
        )

    ai = body.get("ai_explanation")
    if ai:
        print(f"\n  AI Analysis (Groq):\n  {'─'*50}")
        for line in ai.split(". "):
            print(f"  {line.strip()}.")
        print(f"  {'─'*50}")
    else:
        print("\n  ai_explanation: (none — set GROQ_API_KEY in .env to enable)")

    print("""
  SOC Dashboard:
    • Open any event row → CaseDrawer → SHAP tab → click "Explain Score"
    • The bar chart shows SHAP values; the AI Analysis block shows the Groq narrative
""")


# ── Entry point ───────────────────────────────────────────────────────────────

SCENARIOS = {
    "ato": scenario_ato,
    "replay": scenario_replay,
    "coercion": scenario_coercion,
    "shap": scenario_shap,
}


def main() -> None:
    print("""
╔══════════════════════════════════════════════════════════════╗
║          CogniGuard — Demo Scenario Runner                   ║
║  Gateway: http://localhost:8000                              ║
║  Web App: http://localhost:5173                              ║
║  SOC Dashboard: http://localhost:5174                        ║
╠══════════════════════════════════════════════════════════════╣
║  UI Scenarios (use web app / Android / SOC dashboard):       ║
║    1. Happy Path         web app → genuine/Passw0rd!         ║
║    4. Cold Start         web app → register new user         ║
║    5. Brute Force        web app → 5× wrong password         ║
║    7. Step-Up OTP        web app → verify challenge          ║
║    9. Factory Reset      SOC dashboard → Governance tab      ║
║   10. Android Flow       Android app → full session          ║
║                                                              ║
║  API Scenarios (this script):                                ║
║    2. ATO Login          --scenario ato                      ║
║    3. Coercion Payment   --scenario coercion                 ║
║    6. Replay Attack      --scenario replay                   ║
║    8. SHAP + Groq Explain --scenario shap                    ║
╚══════════════════════════════════════════════════════════════╝
""")

    ap = argparse.ArgumentParser(description="CogniGuard demo runner")
    ap.add_argument(
        "--scenario",
        default="all",
        choices=[*SCENARIOS, "all"],
        help="Which scenario to run (default: all)",
    )
    ap.add_argument("--base", default=BASE, help="Gateway base URL")
    args = ap.parse_args()

    global BASE
    BASE = args.base

    if args.scenario == "all":
        for name, fn in SCENARIOS.items():
            fn()
            input("\n  [Press Enter to continue to next scenario…]")
    else:
        SCENARIOS[args.scenario]()


if __name__ == "__main__":
    main()
