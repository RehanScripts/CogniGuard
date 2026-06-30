# API Reference

Base URL: `http://localhost:8000`  
Interactive docs: **http://localhost:8000/docs** (Swagger UI)

All protected endpoints require `Authorization: Bearer <token>`.

---

## Authentication

### Register
```
POST /api/v1/auth/register
Content-Type: application/json

{ "username": "alice", "password": "Str0ng!Pass" }
```

### Login
```
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "genuine",
  "password": "Passw0rd!",
  "channel": "web",
  "source": "web_sdk",
  "nonce": "<server-issued>",
  "seq": 1234567890,
  "ts": "2026-06-30T10:00:00Z",
  "integrity_sig": "<hmac-sha256>",
  "device": { "fingerprint": "...", "ua": "...", "platform": "web" },
  "keystroke": { "events": [...], "field_id": "username" }
}
```
Returns `DecisionResponse` with `action`, `risk_score`, `band`, `reason_codes`, `session_token`.

### Step-Up Verification
```
POST /api/v1/auth/step-up
Authorization: Bearer <token>

{ "challenge_type": "OTP", "challenge_response": "123456" }
```

### Consent
```
POST /api/v1/auth/consent
{ "username": "genuine", "action": "GRANT", "consent_version": "v1" }
```

### Logout
```
POST /api/v1/auth/logout
Authorization: Bearer <token>
```

---

## Behavior (Continuous Re-scoring)

### Ingest behavioral event
```
POST /api/v1/behavior/ingest
Authorization: Bearer <token>
Content-Type: application/json

{
  "channel": "web",
  "nonce": "<server-issued>",
  "seq": 1234567891,
  "ts": "...",
  "integrity_sig": "...",
  "device": { ... },
  "action": { "type": "PAGE_VIEW" },
  "mouse": { "events": [...] }
}
```
Returns updated `DecisionResponse`. A `very_high` band terminates the session immediately.

### Get nonce (for SDK payload signing)
```
GET /api/v1/behavior/nonce
Authorization: Bearer <token>
```
Returns `{ "nonce": "<single-use-token>" }`.

---

## Payment

### Score a transaction
```
POST /api/v1/payment/score
Authorization: Bearer <token>
Content-Type: application/json

{
  "channel": "web",
  "amount": 50000,
  "beneficiary_vpa": "scammer@upi",
  "transfer_type": "UPI",
  "nonce": "<server-issued>",
  "seq": ...,
  "ts": "...",
  "integrity_sig": "...",
  "device": { ... },
  "action": { "type": "PAYMENT" }
}
```
Returns `DecisionResponse` with optional `txn_controls` (cooling period, manual amount entry, coercion check).

---

## Banking (Read-only account data)

```
GET /api/v1/banking/profile
GET /api/v1/banking/accounts
GET /api/v1/banking/transactions?limit=10
GET /api/v1/banking/beneficiaries
GET /api/v1/banking/security-settings
```
All require `Authorization: Bearer <customer-token>`.

---

## Risk

```
GET /api/v1/risk/session/{session_id}
Authorization: Bearer <token>
```

---

## Admin (requires admin/analyst JWT)

```
POST /api/v1/admin/login
{ "email": "admin@cogniguard.dev", "password": "Passw0rd!" }

GET  /api/v1/admin/events          # recent risk_scores + decisions
GET  /api/v1/admin/users/{id}      # user risk history
GET  /api/v1/admin/cases           # fraud case queue
POST /api/v1/admin/cases           # open a case
PATCH /api/v1/admin/cases/{id}     # update case (note / resolve)

GET  /api/v1/admin/policy          # read active policy
POST /api/v1/admin/policy          # update policy (admin only)

GET  /api/v1/admin/models          # list model registry
POST /api/v1/admin/models/promote  # promote challenger (admin only)
POST /api/v1/admin/models/rollback # rollback to previous (admin only)

GET  /api/v1/admin/drift           # PSI/KS drift report
```

---

## WebSocket — SOC Live Feed

```
WS /ws/soc-feed
```
Streams `risk_scores` and `decisions` Kafka events in real time to connected SOC dashboard clients.

---

## Health

```
GET /health
```
Returns `{ "status": "ok", "db": "ok", "redis": "ok", "kafka": "ok", "s3": "ok" }`.
