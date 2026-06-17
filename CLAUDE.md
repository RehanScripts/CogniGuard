# CLAUDE.md — CogniGuard Working Guide

Repo guide & conventions for Claude Code while building **CogniGuard — Real-Time Risk Orchestration Platform for Digital Banking** (Central Bank of India hackathon prototype).

---

## 1. Project Summary

CogniGuard is a **real-time risk-orchestration layer** that sits in front of a bank's existing authentication and payment rails. It does not merely score a transaction in isolation — it **continuously scores both the login session and every transaction**, fuses behavioral, device, network, transaction, and historical signals into a single calibrated **risk score (0–100)**, and then **drives a decision**: `allow`, `verify` (adaptive step-up), or `block`. Risk is a property of the *whole session over time*, not a one-shot gate: a login that scored Low can still escalate later because of a new device, an unusual transfer, an abnormal interaction rhythm, remote-control signatures, or coercion indicators.

The core threat is not only **Account Takeover (ATO)** with stolen credentials, but **authorized-push-payment (APP) fraud and social-engineering / "digital arrest" scams**, where the *genuine* customer is coerced into pressing *send* — identity-only checks wave these through. CogniGuard decides on **risk and intent**, in real time, inside tight latency budgets.

> **Project codename:** the repo/codebase keeps the `cogniguard/` root and `cogniguard-*` package names. The product name is **CogniGuard**.

**Source of truth — consult these, do not re-derive:**
- **`PRD.md`** = the *what* and *why* (requirements, goals, demo scenarios, success criteria). **Authoritative.**
- **`System Architecture.md`** = the *how it fits together* (components, schema, topic/payload contracts, sequence flows, repo map).
- **`Implementation.md`** = the *step-by-step build order* (phases, tasks, file-by-file). Follow its phase order.

When a detail (schema, topic, endpoint, contract name) is in those docs, use it verbatim. Do not invent alternatives.

**Authoritative scope note (from PRD v2.0):** there is **no graph database and no graph-based mule-network detection** in any phase — removed by design. The model stack is **XGBoost (primary, supervised)** + **Isolation Forest (unsupervised anomaly safety net)** for the MVP, with an **LSTM/Transformer** sequence model as a **Phase 2** enhancement only.

---

## 2. Tech Stack & Versions

| Area | Stack |
|------|-------|
| API gateway / services | Python 3.11+, FastAPI (async), Pydantic v2, Uvicorn |
| Event log (streaming) | **Apache Kafka** (KRaft mode) — `behavior_events`, `device_events`, `login_events`, `transaction_events`, `risk_scores`, `decisions` |
| Stream processing | **Apache Flink** (PyFlink) — stateful windowed feature computation |
| Online feature store | **Redis 7** — the **only** store models read at inference time (features, counters, TTLs); also nonces, locks, pub/sub |
| System of record (OLTP) | **PostgreSQL 16**, SQLAlchemy 2.x (typed), Alembic |
| Data lake (offline) | **S3** (MinIO locally) — raw event archive, feature snapshots, labeled training sets, model artifacts |
| ML — primary | **XGBoost** (supervised fraud probability; consumes the anomaly score, stacked) |
| ML — anomaly net | **scikit-learn Isolation Forest** (unsupervised, behavioral + context) |
| ML — Phase 2 | LSTM / Transformer sequence model (`Sequence_Risk`) — not in MVP |
| ML tooling | numpy, pandas, scipy, joblib, model registry |
| Auth / security | PyJWT (JWT sessions), Argon2id (argon2-cffi) password hashing; HMAC-SHA256 + single-use nonce payload binding |
| Frontend | React + TypeScript + Vite + Tailwind |
| Dashboard | React + TS + Vite + Tailwind + **Recharts** (bank-dashboard) |
| Capture SDK | TypeScript **behavior-sdk** (framework-agnostic; mobile does edge feature extraction) |
| Packaging | Docker + Docker Compose |
| Testing | pytest + httpx (backend), Vitest (frontend/SDK) |

---

## 3. Repository Map

```
cogniguard/
├── docker-compose.yml          # full stack: postgres, redis, kafka, flink(jobmanager+taskmanager),
│                               #   minio(s3), gateway, web-app, bank-dashboard
├── README.md / PRD.md / System Architecture.md / Implementation.md / CLAUDE.md
│
├── gateway/                    # FastAPI API Gateway + scoring + decision (hot path)
│   ├── pyproject.toml · Dockerfile · alembic/
│   └── app/
│       ├── main.py             # app factory, router mounting
│       ├── config.py           # settings (env)
│       ├── db.py · redis_client.py · kafka_client.py · s3_client.py · deps.py
│       ├── models/             # SQLAlchemy models (OLTP system of record)
│       ├── schemas/            # Pydantic v2 contracts (BehaviorPayload, ScoreResult, DecisionResponse, ...)
│       ├── routers/            # auth.py, payment.py, behavior.py, risk.py, admin.py, ws.py — THIN
│       ├── services/           # integrity, feature_reader, decision_engine, adaptive_auth,
│       │                       #   txn_fraud_layer, hardening, consent, audit, case_mgmt, broadcaster — LOGIC
│       ├── scoring/            # isolation_forest.py, xgboost_model.py, stack.py, explain.py, registry.py
│       └── utils/              # geo, fingerprint, security helpers
│   ├── scripts/                # seed_demo.py, generate_fraud_scenarios.py, load_datasets.py
│   └── tests/                  # pytest
│
├── flink-jobs/                 # PyFlink feature-engine jobs (Kafka → Redis + S3 mirror)
│   └── feature_engine.py       # windowed velocity/sum, geo-distance, z-scores, baseline deviation
│
├── training/                   # offline training, registry promotion, drift monitors (S3 → model_registry)
│   ├── train_xgboost.py · train_isolation_forest.py · datasets/ (CMU/HMOG/INB/TXN adapters)
│
├── behavior-sdk/               # shared TS capture lib (events, fingerprint, edge-extract, payload, index)
├── web-app/                    # Internet Banking demo (React+Vite) — pages/, components/, api.ts
├── bank-dashboard/             # Fraud-ops / SOC dashboard (React+Vite+Recharts) — pages/, components/, ws.ts, api.ts
└── models/                     # local mirror of S3 model artifacts (joblib / xgb)
```

Ports: postgres 5432 · redis 6379 · kafka 9092 · flink-jobmanager 8081 · minio 9000/9001 · gateway 8000 · web-app 5173 · bank-dashboard 5174.

**There is no graph database in this version.**

---

## 4. Commands / Workflows

| Task | Command |
|------|---------|
| Bring up full stack | `docker compose up --build` |
| Run gateway (dev) | `uvicorn app.main:app --reload --port 8000` (from `gateway/`) |
| Create migration | `alembic revision --autogenerate -m "msg"` |
| Apply migrations | `alembic upgrade head` |
| Submit Flink job | `docker compose exec flink-jobmanager flink run -py /jobs/feature_engine.py` |
| Seed demo personas | `python -m scripts.seed_demo` (from `gateway/`) |
| Load reference datasets | `python -m scripts.load_datasets` (CMU/HMOG/INB_REQ_LOG/TXN_HISTORY_UPI_FIN → S3) |
| Generate fraud scenarios | `python -m scripts.generate_fraud_scenarios` |
| Train models (offline) | `python -m training.train_xgboost` / `python -m training.train_isolation_forest` |
| Backend tests | `pytest` (from `gateway/`) |
| Frontend / SDK tests | `npm run test` / `vitest` (in `web-app/`, `bank-dashboard/`, `behavior-sdk/`) |
| Python lint / format | `ruff check .` · `black . && ruff check --fix .` |
| TS lint / format | `npm run lint` (eslint) · `npm run format` (prettier) |
| Frontend dev server | `npm run dev` |

Gateway runs Alembic migrations + `seed_demo.py` on startup in dev; the Flink feature job and model registry load on startup. `models/` mirrors the S3 model store.

---

## 5. Coding Conventions

### Python
- **Type hints everywhere.** Pydantic **v2** for all IO schemas (request/response/topic payloads).
- **SQLAlchemy 2.x** style (typed `Mapped[...]` / `mapped_column`, `select()`); no legacy Query API.
- **Async** FastAPI routes. Routers stay **thin** — validate + delegate; all logic lives in `services/` and `scoring/`.
- `snake_case` for functions/vars, `PascalCase` for classes. `ruff` + `black` clean.
- **No secrets in code** — config via env only (`config.py` reads env / `.env`).
- **Structured logging** (JSON) with request id, entity type, decision, model version, latency. No PII in logs.

### TypeScript
- **`strict` mode on.** **No `any`** — model types explicitly.
- **Functional React** components + hooks only.
- **Tailwind** for styling (no ad-hoc CSS files for layout).
- **All API calls centralized in `api.ts`** (and WebSocket in `ws.ts`); components never call `fetch` directly.

### Canonical naming (must match contracts exactly)
- Schemas: `BehaviorPayload`, `FeatureBundle`, `ScoreResult`, `DecisionResponse`.
- Decisions (lowercase, per PRD): `allow` / `verify` / `block`.
- Risk bands (lowercase): `low` (0–30) / `medium` (30–60) / `high` (60–100) / `very_high` (≥85 → block).
- Entity types: `login` / `transaction`.
- Channels: `web` / `mobile`. Transfer types: `IMPS` / `NEFT` / `RTGS` / `UPI`.
- Challenge types: `OTP` / `MPIN` / `FINGERPRINT` / `PASSKEY` / `VOICE_READBACK`.
- Kafka input topics: `behavior_events` / `device_events` / `login_events` / `transaction_events`. Output: `risk_scores` / `decisions`.
- Model names: `xgboost_txn` / `isolation_forest` / `lstm_seq` (Phase 2). Model stage: `staging` / `production` / `archived`.
- Case status: `open` / `investigating` / `confirmed_fraud` / `false_positive` / `closed`.

---

## 6. Architecture Invariants (do NOT violate)

1. **Streaming, not batch.** `Mobile/Web → API Gateway → Kafka → Flink → Redis Feature Store → Risk Models → Decision Engine → Dashboard`. Features are computed by Flink from the Kafka log and written to Redis as they change.
2. **Inference reads Redis ONLY.** Models never query PostgreSQL on the hot path; the gateway reads pre-computed online features from Redis plus the inline payload. PostgreSQL is written for the record and read by dashboards/analysts — never on the scoring request path.
3. **Redis is rebuildable** from PostgreSQL (durable backstop) + Kafka/S3 (replay). It is a derived cache, not a source of truth.
4. **Routers thin, logic in services/scoring.** No business logic, DB queries, or model inference in router functions.
5. **Stacked single score (default).** Run **Isolation Forest first → `Behavior_Score`**, feed it as **one input feature** to **XGBoost**, which emits **one fraud probability → one threshold**. The weighted-ensemble (60% txn / 25% behavior / 15% device) is the configurable alternative — never run both at once.
6. **Bands & thresholds come from the active policy** — never hardcode. `low 0–30`, `medium 30–60`, `high 60–100`, `very_high ≥85` are defaults that live in policy; admin-configurable.
7. **Every decision persists immutably** (`risk_scores` + `decisions` + `audit_logs`) with `model_version`, `latency_ms`, and machine- + human-readable **reason codes** — 100% of `verify`/`block` decisions carry them.
8. **Continuous re-scoring.** A Low login can escalate later (new device, unusual transfer, abnormal rhythm, remote-control signature, coercion). A `very_high` continuous score → downgrade/terminate session + alert + `verify`/re-auth.
9. **Cold-start (new user / new channel, no profile)** redistributes biometric weight to context features, leans on Isolation Forest + decision-layer rules, and **biases to `verify`, never `block`**.
10. **Graceful degradation (NFR-4).** If XGBoost is unavailable → fall back to Isolation Forest + decision-layer rules; if Redis is degraded → bias to `verify` (never silent allow); if scoring times out → fail to the safe action per policy; tag `degraded_mode`.
11. **Telemetry integrity (NFR-5):** every behavioral payload carries a server-issued single-use `nonce`, `seq`, `ts`, and `integrity_sig = HMAC-SHA256(nonce ‖ canonical(metrics) ‖ fingerprint ‖ ts)`. Verify and **consume** the nonce; reject unknown/expired/reused nonce, HMAC mismatch, or non-increasing `seq` — defeats capture-and-replay (RAT/MITM).
12. **Dynamic Risk Amplifiers (§10.3):** apply **multiplicative** transaction-context overrides (`final = clamp(base × Π multipliers, 0, 100)`) read from the active policy — new-payee high-value ×1.5, rapid fan-out ×1.4, drain/max-out ×1.3, coercion-time ×1.2. Each fired amplifier is added to `reason_codes`. **Never** hardcode multipliers.
13. **Transaction-fraud layer (§10.3):** when txn risk crosses threshold or an amplifier fires, apply **Cooling Period**, **Reconfirmation** (out-of-band "was this you?"), **Manual Amount Entry**, and **Coercion Check** — the APP-fraud / coercion defense for genuine-behavior-but-dangerous-intent cases.
14. **Risk × Action matrix (§10.2):** the same score demands different friction by the action's stakes; sensitive actions (large/new-payee transfer, change contact, raise limit) are always scrutinized.
15. **Assurance-ordered adaptive auth (§10.1):** pick the **lightest factor that clears the measured risk** — knowledge < possession (OTP/push; SMS is SIM-swappable) < phishing-resistant (device biometric / passkey / FIDO2). Degrade only to an equal-or-higher factor, never silently below the band's required strength.
16. **Explainability (NFR-7):** reason codes are a deterministic feature-delta / top-deviation explainer (**not** SHAP/LIME on the hot path), inside the latency budget.
17. **Anti model-poisoning.** Step-up-passed telemetry is **quarantined**, never fed straight into the baseline; promoted only after a clean cooling window (no fraud complaint, chargeback, anomalous device/geo, or subsequent high-risk event). Only LOW + no-step-up sessions update the per-user baseline.
18. **Model governance.** The scoring service resolves the `production` model from `model_registry` at startup and stamps `model_version` on every `risk_scores` row; new models run as **challengers** in shadow before promotion; drift monitors (PSI/KS) trigger retrain.
19. **DPDP / RBI compliance (NFR-9):** behavioral capture is consent-gated; minors excluded; raw biometric series minimized at the source (mobile edge extraction); retention expiry + right-to-be-forgotten hard-delete; full immutable decision audit; in-region data residency.
20. **All secrets via env / managed vault** — never committed, never in source. PII tokenized (card/account/contact).

---

## 7. Domain Glossary

| Term | Meaning |
|------|---------|
| **Risk orchestration** | Scoring login + every transaction continuously, fusing all signal domains into one number, and driving `allow`/`verify`/`block`. |
| **Continuous risk** | Risk re-evaluated throughout the session, not just at the login gate; a Low login can escalate or de-escalate later. |
| **Behavior_Score** | Isolation Forest anomaly output in [0,1] over typing/touch/swipe/session vs. the user's baseline; fed into XGBoost as one feature. |
| **Stacking** | IF → `Behavior_Score` → XGBoost → single calibrated fraud probability (one threshold to tune). |
| **Keystroke dynamics** | Typing rhythm: dwell (key down→up), flight (up→next down), inter-key latency vector, hold time. |
| **Touch / motion dynamics** | Swipe angle/velocity/curvature, touch pressure/area, accelerometer variance (mobile, edge-extracted). |
| **Device fingerprint** | Stable hash of UA, screen, timezone, language, canvas/WebGL; plus `is_rooted` / `is_emulator`. |
| **Risk band** | `low` 0–30 (allow) / `medium` 30–60 (verify light) / `high` 60–100 (verify strong) / `very_high` ≥85 (block + alert). |
| **Adaptive / step-up auth** | The `verify` action — the lightest assurance-ordered factor that clears the risk (OTP/MPIN → biometric/passkey/voice-readback). |
| **Dynamic Risk Amplifier** | Multiplicative transaction-context override that raises the band when intent is dangerous despite genuine behavior. |
| **Transaction-fraud layer** | Cooling Period / Reconfirmation / Manual Amount Entry / Coercion Check controls fired by decision-layer triggers. |
| **APP fraud / coercion** | Authorized Push Payment / "digital arrest" scams — the genuine customer is socially engineered into sending their own money; behavior is genuine, so caught via transaction context + duress indicators. |
| **ATO** | Account Takeover — attacker uses stolen/phished/SIM-swapped credentials from a different device/geo/behavior, with zero failed passwords. |
| **RAT / replay** | Remote-control / man-in-the-middle that drives the genuine device or replays captured telemetry — defeated by nonce+HMAC binding + continuous re-scoring. |
| **Cold-start** | No per-user profile/labels yet; lean on the global IF prior + rules, bias to `verify`. |
| **Quarantine** | Holding store for step-up-passed telemetry; promoted to training only after a clean cooling window (anti-poisoning). |
| **Champion / Challenger** | New models score in shadow (without acting) and are promoted only when they beat the incumbent at the bounded FP/step-up budget. |
| **Drift** | Feature drift (PSI/KS), score drift, outcome drift (precision/recall on confirmed labels) → alert + on-demand retrain. |
| **EER / FAR / FRR** | Equal Error Rate / False Accept / False Reject — biometric accuracy metrics (target G6: EER ≤ 10%). |
| **DPDP / RBI DPSC** | DPDP Act 2023 (consent, minor exclusion, RTBF); RBI Master Direction on Digital Payment Security Controls (auditability, residency). |

---

## 8. Security & Privacy Rules

- Passwords hashed with **Argon2id**; raw password keystroke **content** never captured/transmitted — only inter-key timings.
- **JWT** sessions (PyJWT), short-lived, `jwt_id`/`session_id` tracked; terminated/hijacked sessions revoked immediately (Redis denylist).
- **No PII in logs** — structured logs carry ids/decisions/model-version/latency, not personal data. **PII tokenized** at rest (card/account/contact).
- **Telemetry integrity (NFR-5):** single-use `nonce` + `HMAC-SHA256` + monotonic `seq` + timestamp-skew check; consume nonce on use; reject replays/tampering and bump fail counters.
- **Data minimization (NFR-10):** raw touch/sensor time-series extracted **on-device** (mobile); only derived features transmitted/stored.
- **Two-track lockout:** brute-force throttling targets the **offending IP/device, never the account** (no account-lockout DoS); sensitive actions are ringfenced, not the whole account.
- **Inference reads Redis only**; PostgreSQL parameterized queries (SQLAlchemy 2.x) — no string-built SQL.
- **Anti-poisoning:** quarantine step-up telemetry before any training use.
- **Consent-gated capture (DPDP, NFR-9):** no behavioral processing without recorded consent; minors excluded; retention expiry; right-to-be-forgotten cascading hard-delete (raw samples + per-user model), retaining only anonymized audit rows.
- **Data residency (NFR-8):** PII/behavioral data in-region; cross-border transfer disabled by config.
- Admin/analyst endpoints behind role-scoped JWT; secrets via env/vault; least-privilege service accounts.

---

## 9. Definition of Done / Quality Bar

- The current **phase runs end-to-end** and is independently demonstrable (vertical slice through the streaming pipeline).
- **Tests pass** (`pytest` + `vitest`); new logic has tests.
- **Demo scenarios from the PRD are reproducible**: genuine happy path, ATO at login, coercion at payment (the signature case), mid-session hijack, brute-force IP/device throttle, replay-reject, amplifier-driven step-up, quarantine anti-poisoning, right-to-be-forgotten, reason-code explanation, analyst case action.
- **Latency budgets met:** login decision **p95 < 300 ms**, payment decision **p95 < 500 ms** (server-side, gateway-in to decision-out).
- **Quality targets tracked (G1–G8):** ≥80% fraud-value caught, ≤1% genuine high-value blocked, ≤5% genuine step-up rate, EER ≤ 10%, 100% reason-code coverage, ≥2,000 events/sec/region.
- Code **formatted & typed**: `ruff`/`black` clean, TS `strict` no `any`, `eslint`/`prettier` clean.
- Every `verify`/`block` decision returns reason codes; `degraded_mode` surfaced when a model falls back.

---

## 10. Do / Don't

**Do**
- Keep slices **vertical and runnable** through the streaming path at each phase.
- Reuse canonical schemas (`BehaviorPayload`, `FeatureBundle`, `ScoreResult`, `DecisionResponse`) and exact enum names.
- Put logic in `services/` and `scoring/`, keep routers thin.
- Read online features from **Redis only** at inference; write the record to PostgreSQL **async, off the hot path**.
- Stack IF → XGBoost (one threshold) by default; read bands/thresholds/amplifiers from the active policy.
- Persist `risk_scores` + `decisions` + `audit_logs` with `model_version` and reason codes; emit to Kafka output topics for the dashboard.
- Bias cold-start and Medium to `verify`; apply amplifiers + transaction-fraud controls at payment time.
- Quarantine step-up telemetry; run challengers in shadow before promotion.

**Don't**
- **Query PostgreSQL on the scoring hot path**, or recompute Flink windows on the request path.
- Build a **graph database / mule-network model** — out of scope for all phases.
- Hardcode bands, thresholds, weights, or **amplifier multipliers** — all from the active policy.
- Run stacking **and** the weighted ensemble at once.
- Commit models, secrets, or `.env`; capture raw password keystroke content or raw mobile sensor series.
- **Block** genuine users on cold-start — `verify` instead.
- Crash on model failure — fall back (IF + rules) and flag `degraded_mode`.
- Trust an unsigned or replayed telemetry payload — verify & consume the nonce first.
- Auto-train on step-up-passed sessions — quarantine them.
- Lock the **account** on brute force — throttle the offending **IP/device**; ringfence sensitive actions.
- Process behavioral data **without recorded consent**, or skip the right-to-be-forgotten purge.
- Wave through a **genuine-behavior transfer to a brand-new high-value beneficiary** — let amplifiers + the transaction-fraud layer force `verify`/cooling.
