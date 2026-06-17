# System Architecture — **CogniGuard**

## Real-Time Risk Orchestration Platform for Digital Banking

**Companion to:** `PRD.md`
**Audience:** Implementers (Claude Code) & reviewers
**Version:** 3.0 · 2026-06-17 · **aligned to PRD v2.0 (orchestration rewrite)**

> **v3.0 changelog (Rakshak → CogniGuard):** Re-platformed from a single FastAPI service to a **streaming-ML** topology — `Mobile/Web → API Gateway → Kafka → Flink → Redis Feature Store → Risk Models → Decision Engine → Dashboard`. Model stack is now **XGBoost (primary, supervised)** stacked on **Isolation Forest (anomaly safety net)**; **LSTM/Transformer** is Phase 2. Decisions are **`allow` / `verify` / `block`** over four bands (`low`/`medium`/`high`/`very_high`). **All graph-database and graph-based mule-network detection is removed from every phase.** Latency budgets: **login p95 < 300 ms, payment p95 < 500 ms**. Polyglot persistence: PostgreSQL (OLTP record) · Kafka (event log) · Redis (online feature store, the only inference-time read store) · S3 (data lake).

---

## 1. Architectural Goals

- **Real-time:** login decision **p95 < 300 ms**, payment decision **p95 < 500 ms** (server-side, gateway-in to decision-out).
- **Continuous risk:** score the **whole session over time** — login *and* every transaction — not a one-shot gate. A Low login can escalate (new device, unusual transfer, abnormal rhythm, remote-control signature, coercion) or de-escalate (silent re-auth).
- **Streaming, not batch:** Flink computes features continuously from the Kafka log into Redis; inference reads **only Redis** + the inline payload, never PostgreSQL, never Flink, on the hot path.
- **Stacked scoring:** Isolation Forest → `Behavior_Score` → XGBoost → one calibrated fraud probability → one threshold.
- **Risk × Action aware:** friction is a function of *both* measured risk and the sensitivity of the attempted action.
- **Explainable:** every `verify`/`block` carries machine- and human-readable **reason codes** (deterministic feature-delta explainer, not SHAP/LIME on the hot path).
- **Edge-private:** raw touch/sensor streams stay on the handset; only derived features cross the network.
- **Degradable:** XGBoost down → Isolation Forest + rules; Redis degraded → bias to `verify`; timeout → safe action per policy.
- **Governed:** model registry + champion/challenger + drift monitors + analyst feedback loop.
- **No graph database, no graph-based mule detection** — out of scope for all phases.

---

## 2. High-Level Architecture

```
                       ┌──────────────────── Bank / Fraud-Ops Analysts ────────────────────┐
                       │                        Bank Dashboard                              │
                       └─────────────▲────────────────────────────────────▲────────────────┘
                                     │ decisions / risk_scores (WS feed)    │ cases, audit (PG read)
 ┌───────────┐  HTTPS   ┌──────────┐ │  produce events  ┌───────────────┐   │
 │ Mobile App├─────────►│   API    ├─┼─────────────────►│     Kafka     │   │
 │  (edge    │ signed   │ Gateway  │ │  (immutable log) │ behavior_/    │   │
 │  features)│ payload  │(FastAPI) │ │                  │ device_/login_│   │
 ├───────────┤          │          │ │                  │ /transaction_ │   │
 │  Web SDK  ├─────────►│  authn + │ │                  │  + risk_scores│   │
 │ (raw      │          │ integrity│ │                  │  + decisions  │   │
 │  timings) │          │ (nonce/  │ │                  └──────┬────────┘   │
 └───────────┘          │  HMAC)   │ │                         │ consume    │
                        └────┬─────┘ │                         ▼            │
                             │       │                 ┌───────────────┐    │
                             │       │                 │ Flink Feature │    │
                             │       │                 │    Engine     │    │
                             │       │                 │ (windowed     │    │
                             │       │                 │  velocity/sum,│    │
                             │       │                 │  geo-dist, z, │    │
                             │       │                 │  baseline dev)│    │
                             │       │                 └──┬────────┬───┘    │
                             │       │      write features│        │ mirror │
                             │       │                    ▼        ▼ raw    │
                             │  online read (ONLY)┌───────────────┐ ┌──────┐│
                             │  ◄─────────────────┤ Redis Feature │ │  S3  ││
                             ▼                    │     Store     │ │ lake ││
                    ┌─────────────────┐           └───────────────┘ └──┬───┘│
                    │  Risk Models    │  IsolationForest ─► Behavior_Score  │
                    │ (scoring svc)   │  XGBoost(stacked) ─► fraud prob.    │
                    └────────┬────────┘                       ▲ offline     │
                             │ score + reason_codes           │ training    │
                             ▼                          ┌─────┴──────────┐  │
                    ┌─────────────────┐  allow/verify/  │ Training &      │  │
                    │ Decision Engine │  block          │ Model Registry  │◄─┘
                    │ + Adaptive Auth │  + txn-fraud     │ (champion/      │
                    │ + Risk×Action   │  layer           │  challenger,    │
                    └────────┬────────┘                  │  drift, feedback)│
                             │ durable write (record) + emit topics        │
                             ▼                                             │
                    ┌─────────────────┐                                    │
                    │  PostgreSQL     │  users, devices, sessions, txns,    │
                    │  (OLTP record)  │  risk_scores, decisions, cases,     │
                    └─────────────────┘  auth_challenges, audit_logs        │
```

**Pipeline (canonical):** `Mobile App / Web SDK → API Gateway → Kafka → Flink Feature Engine → Redis Feature Store → Risk Models → Decision Engine → Bank Dashboard.`

Flink consumes events **asynchronously** to keep Redis warm for *subsequent* events; the *current* decision uses the features already in Redis plus the inline payload — the hot path never blocks on Flink or PostgreSQL.

---

## 3. Component Responsibilities

### 3.1 Client Tier

#### behavior-sdk (TypeScript, web)
- Attaches listeners to login/transfer fields & document (`keydown`/`keyup`, `mousemove`/`mousedown`/`mouseup`, `touchstart`/`touchmove`/`touchend`).
- Buffers events, computes **timing/motion metadata only** (never the key character of secret fields).
- Builds a **device fingerprint** (UA, screen, timezone, language, canvas/WebGL) and reads `is_rooted`/`is_emulator` where available.
- Fetches a **single-use nonce** (`GET /auth/nonce`) and signs the payload (`integrity_sig`, anti-replay).
- Emits a structured `BehaviorPayload` (`source="web_sdk"`) on submit; in continuous mode posts batches every N seconds.
- Public API: `CogniGuard.init(config)`, `CogniGuard.attach(formEl)`, `CogniGuard.collect(): Promise<BehaviorPayload>`, `CogniGuard.startContinuous(sessionToken)`.

#### Mobile App (edge feature extraction) — NFR-10
- Captures **touch/swipe dynamics + motion-sensor data** via the device APIs and **extracts the derived feature vector on-device**; **raw coordinate/pressure/sensor time-series never leave the device.**
- Sends the **same `BehaviorPayload` contract** with `channel="mobile"`, `source="mobile_edge"`, still nonce+HMAC signed.
- Supports the **strong, phishing-resistant** step-up factors: biometric prompt, passkey, MPIN.
- Degrades to normalized raw touch features if edge extraction is unavailable → server flags `degraded_mode`.

#### Web Banking Demo (React)
- Simulated Internet Banking: login, dashboard, "transfer" page (continuous scoring + amplifier demo), **action-sensitive flows** (add payee, change registered contact, large transfer).
- Integrates `behavior-sdk`; renders **adaptive step-up** (silent re-auth / OTP / MPIN / biometric / passkey / voice-readback) and the **transaction-fraud layer** (cooling, reconfirmation, manual amount entry, coercion check).
- A **channel switcher** (Web / Mobile) for multi-channel demonstration.

#### Bank Dashboard (Fraud-Ops / SOC, React + Recharts)
- Live event/alert feed over **WebSocket** sourced from the `risk_scores` / `decisions` Kafka topics; risk-band distribution charts; per-user history drill-down.
- **Reason-code panel** (top deviation drivers + fired amplifiers + triggers).
- **Case management (analyst actions):** block/unblock, acknowledge/assign alert, flag for investigation, add notes, and **label `confirmed_fraud` / `false_positive`** — feeding the §14 feedback loop. All audited.
- **Policy editor:** weights/thresholds/bands, the assurance ladder, the risk×action matrix, amplifiers, cooling windows.
- **Model governance view:** production vs. challenger metrics, drift dashboards, latency histograms (p95 vs budget).

### 3.2 Application / Streaming Tier

| Component | Responsibility |
|-----------|----------------|
| **API Gateway (FastAPI)** | Terminate TLS, authenticate, **validate payload integrity** (single-use nonce + HMAC + seq + skew), **produce events to Kafka**, call scoring + decision synchronously for the gating decision, return `allow`/`verify`/`block`. Reads online features from **Redis only**. |
| **Kafka (event log)** | Immutable, partitioned, replayable log; decouples ingestion from processing; archive for rebuilds/training. Input topics + `risk_scores` / `decisions` output topics. |
| **Flink Feature Engine** | Stateful stream processing: windowed velocity/sum counters, geo-distance, z-scores, baseline deviation; **writes online features to Redis**; mirrors raw events to S3. **Off the hot path.** |
| **Redis Feature Store** | The **only** store models read at inference time — online features/counters with TTLs; plus nonces, JWT denylist, step-up/cooling state, pub/sub for the SOC feed. |
| **Risk Models (scoring service)** | Run **Isolation Forest** (anomaly → `Behavior_Score`) then **XGBoost** (fraud probability, consuming `Behavior_Score`, stacked); return calibrated score + reason codes; rule-based fallback. |
| **Decision Engine + Adaptive Auth** | Map score band **and action stakes** (risk×action matrix) to `allow`/`verify`/`block`; select the **lightest factor that clears the risk**; apply the **transaction-fraud layer** (cooling / reconfirmation / manual amount / coercion check); emit decision. |
| **Hardening (Track)** | Redis-backed failed-attempt counters, backoff, behavioral CAPTCHA, **IP/device lockout (never account)**, distributed brute-force detection per ASN. |
| **Consent / RTBF** | Consent gating, minor exclusion, retention expiry, cascading right-to-be-forgotten hard-delete. |
| **Audit / Case Mgmt** | Immutable `audit_logs`; `cases` lifecycle + analyst actions + label feedback to S3. |
| **SOC Broadcaster** | Publishes `risk_scores`/`decisions` to WebSocket subscribers (Redis pub/sub bridge from Kafka). |
| **Model Registry** | Resolves the `production` model per name at startup; stamps `model_version`; manages staging/archived artifacts in S3; reloads after promotion. |

### 3.3 Data Tier
- **PostgreSQL (OLTP)** — system of record: users, accounts, devices, sessions, login_events, behavior_samples, beneficiaries, transactions, risk_scores, decisions, auth_challenges, cases, audit_logs, model_registry. Written for the record; read by dashboards/analysts — **never on the scoring hot path**.
- **Kafka** — immutable event stream (4 input topics + 2 output topics); decoupling, replay, durability.
- **Redis** — online feature store (the only inference-time read), counters/TTLs, nonces, JWT denylist, step-up/cooling state, pub/sub.
- **S3 / Data Lake** — raw event archive, historical feature snapshots, labeled training sets, model artifacts. **Redis is rebuildable** from PostgreSQL + Kafka/S3.

---

## 4. Data Model (PostgreSQL — OLTP System of Record)

Authoritative DDL is PRD §17.1; summarized here. UUID PKs; `TIMESTAMPTZ` everywhere; PII columns tokenized at rest.

| Table | Purpose / key columns |
|-------|----------------------|
| `users` | `user_id`, `customer_ref`, contact (tokenized), `account_status`, `kyc_level`, `baseline_risk_tier`; **consent**: `consent_status`, `consent_timestamp`, `consent_version`, `is_minor`. |
| `accounts` | `account_id`, `user_id`, `account_number`, `account_type`, `balance`, `currency`, `status`. |
| `devices` | `device_id`, `device_fingerprint` (unique), `os`/`os_version`/`browser`/`app_version`, **`is_rooted`**, **`is_emulator`**, first/last seen. |
| `user_devices` | M:N binding + **`trust_score` (0..100)**, `is_trusted`, `binding_status`. |
| `sessions` | `session_id`, `user_id`, `device_id`, `ip_address`, `asn`, `is_vpn`, geo lat/lon/city/country, `login_risk_score`, `auth_method_used`, `status` (active/ended/terminated). |
| `login_events` | `event_id`, `session_id`, `user_id`, `device_id`, `event_type` (attempt/success/failure/step_up), `behavior_anomaly_score`, `risk_score`, `decision`. |
| `behavior_samples` | raw biometric captures (also archived to S3): `typing_speed`, `typing_rhythm` (inter-key vector), `key_latency_avg`, `swipe_angle`, `touch_pressure`, `mouse_velocity`; quarantine/retention lifecycle. |
| `beneficiaries` | `beneficiary_id`, `account_number`, `bank_code` (IFSC), `name`, `beneficiary_type`. |
| `user_beneficiaries` | M:N + **`cooling_until`**, `is_verified`, `transfer_count`, `total_amount_sent`, `added_at`. |
| `transactions` | `transaction_id`, `user_id`, `account_id`, `session_id`, `device_id`, `beneficiary_id`, `amount`, `transfer_type` (IMPS/NEFT/RTGS/UPI), `channel`, `is_new_payee`, `status` (initiated/pending/allowed/verified/blocked/reversed), `transaction_risk_score`, `decision`, **`decision_reason` JSONB**. |
| `risk_scores` | **one row per scoring event** (login or txn): `entity_type` (login/transaction), `entity_id`, `behavior_score` (IF), `device_score`, `transaction_score` (XGBoost), `final_risk_score`, `risk_band` (low/medium/high/very_high), **`model_version`**, **`latency_ms`**, `scored_at`. |
| `decisions` | `decision_id`, `risk_score_id`, `entity_type`, `entity_id`, `action` (allow/verify/block), **`required_factors` JSONB**, **`reason_codes` JSONB**. |
| `auth_challenges` | `challenge_id`, `session_id`, `decision_id`, `challenge_type` (OTP/MPIN/FINGERPRINT/PASSKEY/VOICE_READBACK), `status` (issued/passed/failed/expired), `attempts`. |
| `cases` | fraud-ops alerts/investigations: `alert_type`, `severity`, `status` (open/investigating/**confirmed_fraud**/**false_positive**/closed), `assigned_to`. |
| `audit_logs` | immutable: `actor_type` (system/user/analyst), `actor_id`, `action`, `entity_type`, `entity_id`, `metadata` JSONB. |
| `model_registry` | `model_name` (xgboost_txn/isolation_forest/lstm_seq), `model_type`, `version`, `stage` (staging/production/archived), `artifact_uri` (S3), `metrics` JSONB. |

**ER cardinalities (PRD §17.4):** `users 1—N accounts/sessions/cases`; `users N—M devices` (via `user_devices.trust_score`); `users N—M beneficiaries` (via `user_beneficiaries`, carrying cooling/history); `sessions 1—N login_events/behavior_samples/transactions`; `transactions 1—1 beneficiary`; `risk_scores 1—1 decisions`; `decisions 1—N auth_challenges`; `transactions 0..1—N cases`; every state change writes `1—N audit_logs`; `model_registry` stamps `risk_scores.model_version`.

### 4.1 Redis online feature store (the only inference-time read store — PRD §17.2)
```
user:{user_id}:profile          HASH   last_login_ts, last_device_id, avg_amount_30d,
                                        std_amount_30d, txn_count_30d, baseline_geohash
user:{user_id}:known_devices    SET    device_ids
user:{user_id}:known_beneficiaries SET beneficiary_ids
user:{user_id}:known_geos       SET    geohashes
user:{user_id}:velocity:1h      STRING counter, TTL 1h
user:{user_id}:velocity:24h     STRING counter, TTL 24h
user:{user_id}:amount_sum:24h   STRING running sum, TTL 24h
device:{device_id}:trust        STRING 0..100
behavior:{user_id}:baseline     STRING serialized biometric profile for the IF behavior anomaly check
# operational (not features):
nonce:{nonce}                   single-use {user_id,seq} (TTL); DEL on consume (anti-replay)
jwt:denylist:{jwt_id}           1 (TTL≈token life) — terminated/hijacked session revocation
stepup:{challenge_id}           {user_id,type,assurance,exp}
cooloff:txn:{txn_id}            1 (TTL hold window) — new-beneficiary cooling
fail:ip:{ip} / fail:device:{fp} int (TTL window) — Track-A brute-force; lock:ip / lock:device (NEVER account)
bruteforce:asn:{asn}            int (TTL) — distributed detection
soc-feed                        pub/sub channel — dashboard
```
> Flink computes and writes the feature keys; PostgreSQL is the durable backstop used to rebuild Redis on cold start.

### 4.2 Kafka topic contracts (PRD §17.3)
**Input** | key → payload
- `behavior_events` `user_id` → `{ session_id, typing_speed, typing_rhythm, key_latency, swipe_angle, touch_pressure, mouse_velocity, ts }`
- `device_events` `device_id` → `{ device_fingerprint, os, app_version, is_rooted, is_emulator, ts }`
- `login_events` `user_id` → `{ session_id, device_id, ip, asn, is_vpn, geo_lat, geo_lon, ts }`
- `transaction_events` `user_id` → `{ transaction_id, amount, beneficiary_id, transfer_type, is_new_payee, ts }`

**Output**
- `risk_scores` → `{ entity_type, entity_id, behavior_score, device_score, transaction_score, final_risk_score, risk_band, model_version, ts }`
- `decisions` → `{ entity_type, entity_id, action, required_factors, reason_codes, ts }`

---

## 5. Canonical Payload Contracts

### 5.1 BehaviorPayload (client → gateway)
```jsonc
{
  "channel": "web",                       // web | mobile
  "source": "web_sdk",                    // web_sdk | mobile_edge
  "nonce": "server-issued-uuid",          // single-use (from GET /auth/nonce)
  "seq": 1,                                // monotonic per-session counter
  "ts": "ISO8601",                         // client timestamp (skew-checked)
  "integrity_sig": "hmac_sha256(nonce ‖ canonical(metrics) ‖ fingerprint ‖ ts)",
  "device": {
    "fingerprint": "sha256hash", "ua": "...", "screen": "1920x1080",
    "timezone": "Asia/Kolkata", "language": "en-IN", "platform": "web",
    "is_rooted": false, "is_emulator": false
  },
  "action": { "type": "LOGIN" },           // LOGIN | VIEW_BALANCE | ADD_PAYEE | TRANSFER | CHANGE_CONTACT | RAISE_LIMIT
  // --- web_sdk: raw timing/motion features ---
  "keystroke": { "events": [ {"key":"x","down":12.0,"up":98.0}, ... ], "field_id": "username" },
  "mouse": { "moves": [{"x":1,"y":2,"t":5}, ...], "clicks": [{"t":120,"dur":40}, ...] },
  "touch": { "swipes": [{"len":220,"dur":140,"vx":1.5,"vy":0.2}, ...] },
  // --- mobile_edge: pre-computed features only (raw streams stay on device) ---
  "derived_features": { "swipe_velocity_norm": 1.4, "swipe_angle_dev": 0.2,
                        "touch_pressure_avg": 0.5, "acceleration_variance": 0.03 },
  "context": { "submitted_at": "ISO8601", "page": "login",
               "pre_txn_dwell_ms": 0, "session_age_s": 0, "correction_rate": 0.0 }
}
```
> The gateway accepts **either** raw modality blocks (web) **or** `derived_features` (mobile) via the same contract; missing modalities are handled gracefully. Never the key character of a secret field.

### 5.2 FeatureBundle (read from Redis + inline payload, internal model input)
```jsonc
{
  "behavior":  { "typing_speed":, "key_latency_avg":, "typing_rhythm_std":, "hold_time_avg":,
                 "swipe_velocity_norm":, "swipe_angle_dev":, "touch_pressure_avg":,
                 "acceleration_variance":, "mouse_velocity_mean": },   // → Isolation Forest
  "device":    { "device_trust":, "is_new_device":bool, "is_rooted":bool },
  "network":   { "geo_distance_km":, "geo_change":bool, "vpn":bool, "asn": },
  "txn":       { "amount":, "amount_zscore":, "velocity_1h":, "velocity_24h":,
                 "amount_sum_24h":, "is_new_payee":bool, "beneficiary_risk":,
                 "odd_time":bool, "high_velocity":bool },
  "context":   { "hour":, "dow":, "session_age_s":, "pre_txn_dwell_ms":,
                 "correction_rate":, "behavior_score": }                // IF output, fed to XGBoost
}
```

### 5.3 ScoreResult (scoring service, internal)
```jsonc
{
  "behavior_score": 0.12,        // Isolation Forest [0,1]  ⇒ Behavior_Score (stacked into XGBoost)
  "device_score": 0.00,
  "transaction_score": 0.27,     // XGBoost fraud probability [0,1] (stacked single score)
  "final_risk_score": 27.0,      // round(100 * final_p)  OR weighted-ensemble alternative
  "risk_band": "low",            // low | medium | high | very_high
  "model_version": "xgboost_txn@2026.06.17",
  "amplifiers": [],              // fired Dynamic Risk Amplifiers (txn path)
  "reason_codes": [ {"code":"GEO_CHANGE","detail":"new city, plausible travel","sigma":1.1} ],
  "degraded_mode": false,
  "latency_ms": 41
}
```

### 5.4 DecisionResponse (gateway → client)
```jsonc
{
  "action": "allow",                       // allow | verify | block
  "entity_type": "login",                  // login | transaction
  "risk_score": 27.0,
  "risk_band": "low",
  "required_factors": [],                  // e.g. ["OTP"] or ["FINGERPRINT","VOICE_READBACK"]
  "reason_codes": [                        // 100% coverage on verify/block; top deviation drivers + amplifiers
    {"code":"KEYSTROKE_MATCH","detail":"matches baseline"},
    {"code":"KNOWN_DEVICE","detail":"recognized device"}
  ],
  "amplifiers": [],                        // e.g. [{"code":"NEW_BENEF_HIGHVAL","multiplier":1.5}]
  "action_sensitivity": "low",             // resolved stakes for the attempted action (risk×action)
  "step_up": null,                         // or {"challenge_type":"FINGERPRINT","assurance":"strong","challenge_id":"..."}
  "txn_controls": null,                    // or {"cooling_until":"ISO8601","manual_amount":true,"coercion_check":true,"reconfirm":"APP_PUSH"}
  "session_token": "jwt or null",
  "hardening": null,                       // {"action":"DELAY"|"CAPTCHA"|"LOCKOUT","scope":"ip|device","retry_after_s":30}
  "integrity": "OK",                       // or "INTEGRITY_REJECT" on replay/tamper
  "degraded_mode": false,
  "model_version": "xgboost_txn@2026.06.17"
}
```

---

## 6. Key Sequence Flows

### 6.1 Login scoring (budget p95 < 300 ms — PRD §5.2, §12.1)
```
Client            Gateway            Kafka       Redis        Models        Decision
  │ login + signed payload + action                                              │
  ├─────────────────►│                                                           │
  │   (1) authn + integrity verify (nonce/HMAC/seq/skew) ≤30ms                    │
  │                  ├─ produce login_event (async, non-blocking) ≤5ms ──► Kafka  │
  │                  ├──── read online features (profile/known_*/counters) ≤40ms ►│
  │                  │◄──── feature bundle ──────────────────────────────────────┤
  │                  ├──── IsolationForest → Behavior_Score ≤60ms ──────► Models  │
  │                  ├──── XGBoost(features, Behavior_Score) → fraud_p ≤80ms ────►│
  │                  │◄──── score + reason_codes ────────────────────────────────┤
  │                  ├──── decide(band, action stakes) ≤30ms ──────────► Decision │
  │                  │◄──── allow | verify(factors) | block ──────────────────────┤
  │◄── decision (+ challenge if verify; +JWT if allow) ≤25ms ─────────────────────┘
  │                  └─ async: write risk_scores/decisions to PG + emit topics
```
> Track B (risk scoring) runs on **every** attempt and can return `verify`/`block` on the **first try with zero password failures** — catching ATO with valid stolen creds. The integrity check runs **before** the password check; failure → `INTEGRITY_REJECT` + fail-counter bump. Brute-force throttling (Track A) is evaluated separately and only ever locks the **IP/device**, never the account.

### 6.2 Payment scoring (budget p95 < 500 ms — PRD §5.3, §12.2)
```
Client            Gateway            Kafka       Redis        Models        Decision
  │ initiate payment + signed payload + action stakes                            │
  ├─────────────────►│                                                           │
  │   (1) authn + integrity verify + load session context ≤40ms                   │
  │                  ├─ produce transaction_event (async) ≤5ms ──────► Kafka      │
  │                  ├──── read: amount_z, velocity, amount_sum, geo,             │
  │                  │        beneficiary_risk, behavior baseline ≤70ms ─────────►│
  │                  │◄──── feature bundle ──────────────────────────────────────┤
  │                  ├──── IF anomaly ≤70ms ; XGBoost + amplifiers ≤110ms ───────►│
  │                  │◄──── base score + amplifiers + reason_codes ──────────────┤
  │                  │   final = clamp(base × Π amplifiers, 0, 100)               │
  │                  ├──── decide(band, action stakes) + txn-fraud layer ≤60ms ──►│
  │                  │◄──── allow | verify(cooling/reconfirm/manual/coercion) |   │
  │                  │      block + alert bank ───────────────────────────────────┤
  │◄── decision (+ step-up / cooling / coercion screen) ≤35ms ────────────────────┘
  │                  └─ async: persist txn, risk_score, decision; emit topics
```

### 6.3 Enrollment / baseline bootstrap (PRD §8.2)
```
new user → cold-start: global IF prior (CMU typing / HMOG touch) covers the gap → bias to verify, never block.
accumulate ≥10 LOW-risk, no-step-up sessions → per-user behavior baseline replaces the global prior for that user.
first use of a NEW channel → cold-start for that channel → verify, seed a fresh baseline.
```

### 6.4 Continuous / mid-session re-scoring + hijack (PRD §4, §10.4)
```
client (every N s) → POST /behavior/ingest (batch + session_token, signed)
   → integrity verify → read features → IF → XGBoost → update session risk
   → if score jumps to very_high (RAT / behavioral discontinuity / replayed telemetry):
        mark session TERMINATED, push jwt_id → jwt:denylist (token dies immediately),
        emit decisions topic + SOC alert, respond {action:"verify"/REAUTH} → client re-auths.
   → if behavior re-converges to baseline: de-escalate (silent re-auth).
```

### 6.5 Nonce issuance (precedes every login/txn)
```
page load → GET /auth/nonce → server generates single-use nonce, stores nonce:{n} in Redis (TTL)
          → SDK/app signs the BehaviorPayload (integrity_sig) using the nonce.
```

### 6.6 Transaction-fraud layer — amplifiers + coercion (the signature case, PRD §10.3)
```
POST /payment/score (amount, beneficiary, action, session_token + signed behavior)
  → base score from Models (behavior may be LOW — genuine, coerced user)
  → evaluate decision-layer triggers + amplifiers vs txn/beneficiary context:
       new payee <2h AND amount >80% daily-avg → ×1.5 ; rapid fan-out ×1.4 ; drain ×1.3 ; coercion-time ×1.2
  → final = clamp(base × Π, 0, 100); each fired amplifier/trigger → reason_codes
  → risk×action matrix: high-stakes (new payee / large / change contact) raises required friction regardless of clean login
  → genuine-but-dangerous → verify + controls:
       Cooling Period (hold new-payee high-value), Reconfirmation (OOB "was this you?"),
       Manual Amount Entry (type, don't tap — captures a fresh high-value sample),
       Coercion Check ("someone instructing you to send ₹X to a payee added 40 min ago?")
  → very_high → block + alert bank + open case
  → persist transactions + risk_scores + decisions; emit topics; broadcast SOC
```

### 6.7 Right-to-be-forgotten (NFR-9)
```
consent withdrawn → consent_status=WITHDRAWN
   → cascade hard-delete job (≤24h): purge behavior_samples (raw vectors) + per-user model artifact
   → retain risk_scores/decisions/audit_logs stripped to score/band/decision (no biometric vectors) for RBI audit
```

---

## 7. Risk Scoring Engine — Internal Design

### 7.1 PRIMARY — Stacked single score (recommended, PRD §9.1)
```
Behavior_Score = IsolationForest(behavioral_vector)        # [0,1]   (Model 2, anomaly safety net)
final_p        = XGBoost(context, txn, device, Behavior_Score)  # [0,1] (Model 1, primary)
final_risk     = round(100 * final_p)                       # 0..100  → one number, one threshold
```
- **Isolation Forest** (unsupervised, no labels): catches **novel fraud** and **covers cold-start**; behavioral-biometric anomaly over typing/touch/swipe/session vs. baseline. Seeded by CMU (typing) + HMOG (touch) global priors; per-user baseline supersedes after ≥10 clean sessions.
- **XGBoost** (supervised): the **final fraud probability the Decision Engine acts on**, consuming `Behavior_Score` as one feature. Trained on labeled history (analyst-confirmed via the feedback loop) joined with historical feature snapshots so training features match online features.

### 7.2 ALTERNATIVE — Weighted ensemble (rebalanced, graph removed, PRD §9.2)
```
final_risk = 100 * clamp( 0.60·Transaction(XGBoost) + 0.25·Behavior(IF) + 0.15·Device , 0, 1 )
```
Use **either** §7.1 (stacked, one threshold) **or** §7.2 (weighted, inspectable sub-scores) — never both. Weights are admin-configurable in policy.

### 7.3 Risk bands (both approaches, PRD §9.3)
`low` 0–30 → allow · `medium` 30–60 → verify (light) · `high` 60–100 → verify (strong) + txn-fraud controls · `very_high` ≥85 (configurable top sub-range of High) → **block + alert bank**. Cutoffs live in the active policy.

### 7.4 Dynamic Risk Amplifiers (transaction path, PRD §10.3)
```
final_score = clamp( base_score × Π amplifierⱼ , 0, 100 )      # multipliers from active policy
```
Triggers → amplifiers: New Payee `is_new_payee` (new-benef high-value ×1.5) · Large Amount `amount_zscore` (drain/max-out ×1.3) · Odd Time `odd_time` (coercion-time ×1.2) · High Velocity (rapid fan-out ×1.4) · New Device / Geo Change (device-trust drop / impossible-travel elevation). Each fired amplifier and trigger is added to `reason_codes`.

### 7.5 Explainability (reason codes, deterministic, NFR-7)
Deterministic feature-delta / top-deviation explainer (**not** SHAP/LIME on the hot path): for each model-input feature compute the standardized deviation from baseline, pick the top drivers, map to plain-English reason codes, and append fired amplifiers/triggers. Runs inside the latency budget.

### 7.6 Cold-start & degradation
- **Cold-start** (no per-user profile/labels): redistribute biometric weight to context features, lean on IF global prior + decision-layer rules, **bias to `verify`, never `block`**.
- **Degradation (NFR-4):** XGBoost unavailable → IF + rules; Redis degraded → bias to `verify`; scoring timeout → safe action per policy; tag `degraded_mode` in response + logs.

### 7.7 Models, datasets & training (PRD §6.6, §8, §14)
- **`INB_REQ_LOG`** (Internet Banking request log) → session/navigation features (`session_duration`, `pre_txn_dwell`, `nav_entropy`, `request_velocity`, **`beneficiary_add_to_pay_gap`** — primary coercion signal, `odd_time`) → IF + XGBoost. Replaced day-one by live `login_events`/`behavior_events`.
- **`TXN_HISTORY_UPI_FIN`** (UPI history) → `amount_zscore`, `velocity_1h/24h`, `amount_sum_24h`, `is_new_payee`, `beneficiary_risk`, odd-time norms → XGBoost supervised target (label column or heuristic `is_new_payee ∧ amount_z>2 ∧ odd_time`). Replaced by live `transaction_events` → Flink → Redis.
- **CMU Keystroke** → global IF prior for typing (`typing_speed`, `key_latency_avg`, `typing_rhythm_std`, `hold_time_avg`); validates **G6 (EER ≤ 10%)**.
- **HMOG** → global IF prior for touch/motion (`swipe_velocity_norm`, `swipe_angle_dev`, `touch_pressure_avg`, `acceleration_variance`).
- **Synthetic generation is for fraud scenarios only** (replay, hijack, UPI scam, brute-force, poisoning) — never to fabricate genuine baselines. Both bank datasets archive to S3 as the initial training-lake partition.

---

## 8. Decision Engine & Adaptive Authentication (PRD §10)

### 8.1 Band → action → factor ladder (assurance-ordered)
| Band | Action | Factor(s) |
|------|--------|-----------|
| `low` 0–30 | **allow** | none — seamless |
| `medium` 30–60 | **verify (light)** | OTP / MPIN — or silent behavioral re-auth if behavior re-converges |
| `high` 60–100 | **verify (strong)** | fingerprint / passkey / OTP / voice-readback (phishing-resistant preferred) |
| `very_high` ≥85 | **block + alert** | out-of-band "was this you?"; case opened for analyst |

Assurance ordering: knowledge (password/PIN — phishable) < possession (OTP/push — SMS is SIM-swappable) < phishing-resistant (device biometric / passkey / FIDO2). Pick the **lightest factor that clears the risk**; degrade only to **equal-or-higher** assurance, never silently below the band's strength.

### 8.2 Risk × Action matrix (same risk, different friction by stakes — PRD §10.2)
| Risk ↓ / Action → | Low-stakes (view balance) | Medium (add payee, small known-payee transfer) | High (large/new-payee transfer, change contact, raise limit) |
|---|---|---|---|
| `low` | allow | allow | verify (medium) + cooling-off |
| `medium` | allow / silent re-auth | verify (medium) | verify (strong) + out-of-band confirm |
| `high` | verify (medium) | verify (strong) | **block / strong step-up + out-of-band + cooling-off** |

### 8.3 Transaction-fraud layer controls (PRD §10.3)
Fired when txn risk crosses threshold or an amplifier fires: **Cooling Period** (hold large transfers to freshly added payees) · **Reconfirmation** (out-of-band on a separately verified channel) · **Manual Amount Entry** (type the amount — deliberate pause + fresh high-value behavioral sample) · **Coercion Check** (plain-language "is someone instructing you right now?"). This is how CogniGuard catches *"genuine behavior, dangerous intent."*

### 8.4 Orchestration (PRD §10.4)
`event → gateway authn+integrity → read Redis features → IF Behavior_Score → XGBoost fraud_p → band? → allow / verify(light) / verify(strong) / block → {action stakes / amplifiers?} → txn-fraud layer → emit decision + reason_codes → persist PG + emit risk_scores/decisions → dashboard.`

---

## 9. Repository / Module Structure

```
cogniguard/
├── docker-compose.yml
├── README.md · CLAUDE.md · PRD.md · System Architecture.md · Implementation.md
│
├── gateway/                          # FastAPI API Gateway + scoring + decision (hot path)
│   ├── pyproject.toml · Dockerfile · alembic/
│   ├── app/
│   │   ├── main.py · config.py · db.py · redis_client.py · kafka_client.py · s3_client.py · deps.py
│   │   ├── models/                   # SQLAlchemy (16 OLTP tables, §4)
│   │   ├── schemas/                  # Pydantic v2 (BehaviorPayload, FeatureBundle, ScoreResult, DecisionResponse, ...)
│   │   ├── routers/                  # auth, payment, behavior, risk, admin, ws  (THIN)
│   │   ├── services/
│   │   │   ├── integrity.py          # nonce/HMAC/seq/skew (anti-replay)
│   │   │   ├── feature_reader.py     # read online features from Redis (ONLY)
│   │   │   ├── decision_engine.py    # band + risk×action matrix + adaptive auth
│   │   │   ├── adaptive_auth.py      # assurance-ordered factor selection
│   │   │   ├── txn_fraud_layer.py    # cooling / reconfirm / manual-amount / coercion
│   │   │   ├── hardening.py          # Track A: IP/device counters & lockout
│   │   │   ├── consent.py            # consent gating + RTBF cascade
│   │   │   ├── audit.py · case_mgmt.py · broadcaster.py
│   │   ├── scoring/
│   │   │   ├── isolation_forest.py · xgboost_model.py · stack.py
│   │   │   ├── amplifiers.py · explain.py · registry.py
│   │   └── utils/                    # geo, fingerprint, security helpers
│   ├── scripts/                      # seed_demo.py, generate_fraud_scenarios.py, load_datasets.py
│   └── tests/                        # pytest
│
├── flink-jobs/                       # PyFlink feature engine (Kafka → Redis + S3 mirror)
│   └── feature_engine.py
├── training/                         # offline training + registry promotion + drift
│   ├── train_xgboost.py · train_isolation_forest.py · drift_monitor.py
│   └── datasets/                     # CMU/HMOG/INB_REQ_LOG/TXN_HISTORY_UPI_FIN adapters (fetched per license)
│
├── behavior-sdk/                     # shared TS capture lib (events, fingerprint, edge-extract, payload, index)
├── web-app/                          # Internet Banking demo (React+Vite) — pages/, components/, api.ts
├── bank-dashboard/                   # Fraud-ops/SOC dashboard (React+Vite+Recharts) — pages/, components/, ws.ts, api.ts
└── models/                           # local mirror of S3 model artifacts
```

---

## 10. Deployment / Runtime Topology

`docker-compose.yml` services:

| Service | Image / Build | Port | Depends on |
|---------|---------------|------|-----------|
| `postgres` | postgres:16 | 5432 | — |
| `redis` | redis:7 | 6379 | — |
| `kafka` | bitnami/kafka (KRaft) | 9092 | — |
| `flink-jobmanager` | flink:1.18 | 8081 | kafka, redis |
| `flink-taskmanager` | flink:1.18 | — | flink-jobmanager |
| `minio` | minio/minio (S3) | 9000 / 9001 | — |
| `gateway` | build ./gateway | 8000 | postgres, redis, kafka, minio |
| `web-app` | build ./web-app | 5173 | gateway |
| `bank-dashboard` | build ./bank-dashboard | 5174 | gateway |

- Gateway runs Alembic migrations + `seed_demo.py` on startup (dev); resolves the `production` models from `model_registry`.
- The Flink feature job is submitted to the jobmanager on startup; `models/` mirrors the S3 (MinIO) model store.
- Single command for the stack: `docker compose up --build`.

---

## 11. Security & Privacy Architecture

- **Transport:** TLS in production; HTTP for local demo only.
- **Passwords:** Argon2id; raw password keystroke **content** never transmitted (only timings). **PII tokenized** at rest (card/account/contact).
- **Telemetry integrity / anti-replay (NFR-5):** single-use `nonce` + `HMAC-SHA256(nonce ‖ canonical(metrics) ‖ fingerprint ‖ ts)` + monotonic `seq` + timestamp-skew; nonce consumed on use (Redis `DEL`); any violation → `INTEGRITY_REJECT` + fail-counter bump.
- **Sessions & revocation:** short-lived JWT with `jwt_id` tracked in `sessions`; a Redis `jwt:denylist` check on every request kills a terminated/hijacked session's token immediately.
- **Two-track lockout:** brute-force throttling targets the **offending IP/device, never the account** (no account-lockout DoS); sensitive actions ringfenced.
- **Assurance-ordered MFA:** high-risk / high-stakes require a **phishing-resistant** factor (device biometric / passkey), not just SMS-OTP; pick the lightest factor that clears the risk.
- **Out-of-band verification:** suspicious activity triggers a "was this you?" confirmation on a separately verified channel.
- **Edge data minimization (NFR-10):** mobile transmits only derived features; raw touch/sensor series never leave the device.
- **Anti model-poisoning:** step-up-passed telemetry quarantined; promoted only after a clean cooling window.
- **DPDP / RBI compliance (NFR-9):** consent logging, minor exclusion, retention expiry, ≤24h right-to-be-forgotten cascading hard-delete; in-region residency (NFR-8); anonymized `risk_scores`/`decisions`/`audit_logs` retained for RBI DPSC audit.
- **Input validation:** Pydantic v2 on every endpoint and topic payload; parameterized SQL via SQLAlchemy 2.x.
- **Least exposure:** admin/analyst endpoints behind role-scoped JWT; secrets via env/vault; least-privilege service accounts.

---

## 12. Model Governance & Observability

- **Model registry:** every model (`xgboost_txn`, `isolation_forest`, `lstm_seq` in Phase 2) registered with version, type, stage (`staging|production|archived`), S3 artifact URI, metrics. Scoring resolves `production` at startup; stamps `model_version` on every `risk_scores` row. A decision is reproducible from `(model_version, policy_version, feature_set)`.
- **Champion/Challenger:** new models score in **shadow** against live traffic (scoring without acting); promoted only when they beat the incumbent on fraud-value-caught at the bounded FP/step-up budget. Any production model rolls back to a prior registry version without redeploy.
- **Drift monitoring:** feature drift (PSI/KS), score drift, outcome drift (precision/recall on confirmed labels) → alert + on-demand retrain.
- **Feedback loop:** analyst `cases.status` of `confirmed_fraud` / `false_positive` flow to S3 as labeled training data; weekly XGBoost retrain consumes them; IF baselines update incrementally from LOW-risk, no-step-up sessions only; step-up telemetry quarantined.
- **Health:** `GET /health` (DB + Redis + Kafka + Flink + S3 + model registry status, incl. active policy id and production model versions).
- **Metrics:** decision latency histograms (p95 vs 300/500 ms budgets), band distribution, amplifier/trigger fire rates, IP/device lockouts, quarantine counts, throughput (events/sec), RED/USE per stage — surfaced on the dashboard. `degraded_mode` propagated in responses & logs.

---

## 13. Mapping Architecture ↔ PRD Requirements

| Architecture element | Satisfies |
|----------------------|-----------|
| Streaming pipeline (Kafka → Flink → Redis) + Redis-only inference | §5, §11, §12, NFR-1/2 |
| API Gateway (authn + integrity + produce + sync score/decide) | §5.1, NFR-5 |
| behavior-sdk + mobile edge feature extraction + `source` field | §6.1, NFR-10 |
| Nonce + HMAC integrity binding | §6 collection rule, NFR-5, §16.2 (replay/RAT) |
| Isolation Forest (anomaly, cold-start, novel fraud) | §8.2, G6 |
| XGBoost primary (stacked, drives decision) | §8.1, §9.1, G1 |
| Weighted-ensemble alternative (60/25/15) | §9.2 |
| Risk bands low/medium/high/very_high | §9.3 |
| Dynamic Risk Amplifiers (multiplicative) | §10.3 (APP/coercion) |
| Transaction-fraud layer (cooling/reconfirm/manual/coercion) | §10.3 |
| Decision Engine + adaptive auth + risk×action matrix | §10.1, §10.2 |
| Continuous re-scoring + session termination + JWT denylist | §4, §10.4 |
| Two-track lockout (IP/device, never account) | §16.2 (lockout DoS) |
| Polyglot persistence (PG / Kafka / Redis / S3) | §11, §17 |
| 16-table OLTP schema + Redis keys + Kafka topics | §17.1–17.3 |
| Reason-code explainer (deterministic, no SHAP/LIME) | NFR-7, G7 |
| Model registry + champion/challenger + drift + feedback | §14 |
| Quarantine (anti-poisoning) | §8.2, §14, §16.2 |
| Datasets (INB_REQ_LOG / TXN_HISTORY_UPI_FIN / CMU / HMOG) + synthetic *fraud* generator | §6.6, §7 |
| Bank Dashboard + case actions + WS feed | §3, §5.1 |
| Consent + RTBF + residency + audit | NFR-8, NFR-9, §13 |
| Rule-based / IF fallback (`degraded_mode`) | NFR-4 |
| Latency budgets (login 300ms / payment 500ms) | NFR-1, §12 |
| Docker Compose topology | NFR-12 |
| **No graph database / mule-network model** | §2.2, §4, §11, §15 (out of scope, all phases) |
```
