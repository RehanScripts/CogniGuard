# Demo Scenarios

All scenarios use the `genuine` user seeded on startup. Signed fixtures live in
`gateway/tests/fixtures/`. Run `docker compose up` before these commands.

---

## 1 — Happy Path (Low Risk → Allow)

Steady typing rhythm, known Mumbai device → `low` band → `allow`, no step-up.

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d @gateway/tests/fixtures/login_genuine.json | python -m json.tool
```

**Expected:** `"action": "allow"`, `"band": "low"`

---

## 2 — Account Takeover Impostor (High Risk → Verify)

New device fingerprint (Tallinn) + erratic keystroke rhythm against `genuine`'s account.
Fires `NEW_DEVICE` and `GEO_CHANGE` reason codes.

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d @gateway/tests/fixtures/login_impostor.json | python -m json.tool
```

**Expected:** `"action": "verify"`, reason codes include `NEW_DEVICE`, `GEO_CHANGE`

---

## 3 — APP Fraud / Coercion (Amplifiers → Verify + Controls)

High-value UPI transfer to `scammer@upi` (new beneficiary < 1 h old).
`NEW_BENEF_HIGHVAL ×1.5` amplifier fires; cooling period + manual amount entry activated.

```bash
# First get a session token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d @gateway/tests/fixtures/login_genuine.json | python -m json.tool | grep access_token | cut -d'"' -f4)

curl -s -X POST http://localhost:8000/api/v1/payment/score \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d @gateway/tests/fixtures/txn_app_fraud.json | python -m json.tool
```

**Expected:** `NEW_BENEF_HIGHVAL` in `reason_codes`, `txn_controls.cooling_required: true`

---

## 4 — Replay Attack (Rejected)

Re-submitting a previously accepted payload with the same nonce.

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d @gateway/tests/fixtures/replay_login.json | python -m json.tool
```

**Expected:** `HTTP 401`, `"code": "NONCE_REUSED"`

---

## 5 — Mid-Session Hijack (Continuous Re-scoring → Session Terminated)

After a low-risk login, ingest a behavioral event with hijack signatures.
Session escalates to `very_high` → JWT denylisted, case opened automatically.

```bash
# Requires a valid session token from scenario 1
curl -s -X POST http://localhost:8000/api/v1/behavior/ingest \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d @gateway/tests/fixtures/ingest_hijack.json | python -m json.tool
```

**Expected:** `"action": "block"`, `"band": "very_high"`, session terminated

---

## Full Automated Demo Script

Runs all scenarios end-to-end against the live stack:

```bash
docker compose exec gateway python -m scripts.demo_scenarios
```

---

## SOC Dashboard Walkthrough

1. Open http://localhost:5174 and log in as `admin@cogniguard.dev` / `Passw0rd!`
2. Run scenario 2 (impostor) — the **Live Feed** tab shows the event in real time
3. Open the **Cases** tab — a case is auto-opened for `very_high` events
4. Click the case → add a note → resolve as `confirmed_fraud`
5. Open **Policy** tab → adjust the `medium` threshold → re-run scenario 1

---

## Android Demo

See [docs/android-setup.md](android-setup.md) for device setup.

Risk matrix displayed in the app:

| Risk | Score | Outcome |
|------|-------|---------|
| Low | 0–30 | Direct allow — lands on Dashboard |
| Medium | 30–60 | OTP screen (enter `123456`) |
| High | 60–85 | OTP → BiometricPrompt (2-step) |
| Very High | ≥85 | Block screen |
