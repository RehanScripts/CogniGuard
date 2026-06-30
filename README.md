# CogniGuard

**Real-Time Risk Orchestration Platform for Digital Banking**

Central Bank of India demo skin of CogniGuard — a continuous behavioral-biometric fraud detection and adaptive step-up authentication system built for the Central Bank of India hackathon. It sits in front of a bank's existing authentication and payment rails, continuously scores every login session and transaction, and drives **allow / verify / block** decisions inside tight latency budgets (login p95 < 300 ms, payment p95 < 500 ms).

> **This is a prototype.** Do not connect it to production banking infrastructure.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Prerequisites](#prerequisites)
3. [Quick Start](#quick-start)
4. [Service URLs](#service-urls)
5. [Test Credentials](#test-credentials)
6. [Environment Variables](#environment-variables)
7. [Repository Layout](#repository-layout)
8. [Component Details](#component-details)
9. [Running Tests](#running-tests)
10. [Android Setup](#android-setup)
11. [Demo Scenarios](#demo-scenarios)
12. [ML Model Artifacts](#ml-model-artifacts)
13. [Build Status](#build-status)
14. [License](#license)

---

## Architecture

```
Mobile/Web (Central Bank of India UI)
    │
    ▼  Keystroke / Touch / Motion (HMAC-signed, nonce-bound, sequence-checked)
┌─────────────────────────────────────────────────────────┐
│  FastAPI Gateway (port 8000)                            │
│  • Integrity: nonce/HMAC verification, seq monotonicity │
│  • Auth: Argon2id passwords, JWT sessions               │
│  • Payment: amplifier overlay, txn-fraud controls       │
│  • Behavior: continuous re-scoring, session escalation  │
└──────────┬──────────────────────────┬───────────────────┘
           │ Kafka topics              │ Decisions / events
           ▼                          ▼
  ┌─────────────────┐        ┌────────────────────┐
  │ Apache Flink    │        │ WebSocket SOC Feed  │
  │ Feature Engine  │        │ (bank-dashboard)    │
  │ (windowed stat) │        └────────────────────┘
  └───────┬─────────┘
          │ Online features
          ▼
  ┌─────────────────┐   ┌─────────────────────────────────────┐
  │  Redis 7        │──▶│  Risk Scoring Stack                 │
  │  Feature Store  │   │  LSTM Autoencoder (ONNX) → calibrate│
  │  (hot path only)│   │  → Behavior_Score                   │
  └─────────────────┘   │  Isolation Forest (shadow/fallback) │
                        │  XGBoost (stacked fraud prob)        │
                        │  Decision Engine (policy thresholds) │
                        │  Dynamic Risk Amplifiers             │
                        └─────────────────────────────────────┘
          │
          ▼
  ┌─────────────────┐   ┌─────────────────────────────────────┐
  │ PostgreSQL 16   │   │ MinIO (S3)                          │
  │ OLTP record     │   │ Data lake · model artifacts         │
  │ (off-path write)│   │ Training sets · feature snapshots   │
  └─────────────────┘   └─────────────────────────────────────┘
```

**Key design invariants:**
- Inference reads **Redis only** on the hot path — never PostgreSQL, never recomputing Flink windows.
- **LSTM Autoencoder** (ONNX) is the primary behavioral model; **Isolation Forest** runs in shadow and is the cold-start / degraded-mode fallback.
- A single `Behavior_Score` feeds **XGBoost** → one calibrated fraud probability → one policy threshold.
- Every `verify`/`block` decision carries **machine-readable reason codes**; 100% coverage.
- **Nonce+HMAC payload binding** defeats replay / RAT / MITM — captured telemetry is single-use.
- **No graph database** anywhere — out of scope by design.

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Docker | 24+ | Engine + CLI |
| Docker Compose | v2 (plugin) | `docker compose` (no dash) |
| Git | any | for clone |
| **Android only** | | |
| Android Studio | Hedgehog+ | for the native Kotlin app |
| Android SDK | compileSdk 34, minSdk 26 | set `ANDROID_HOME` |
| ADB | any | for physical-device tunnel |
| **Local dev only** | | |
| Python | 3.11+ | for running scripts outside containers |
| Node.js | 20+ | for running frontend tooling outside containers |

Everything else (Python, Node, PyFlink, Redis, Kafka, etc.) runs inside Docker — you do **not** need them installed locally to run the system.

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/xemorph64/Cogni_Guard.git
cd Cogni_Guard

# 2. Configure environment
cp .env.example .env
#    Edit .env to set optional SMTP / Groq keys (both optional for basic demo)

# 3. Build and start the core stack
#    First run takes ~5–8 min (downloads images, builds gateway + Flink images)
docker compose up --build -d

# 4. Verify health
curl -s http://localhost:8000/health | python -m json.tool
#    Expected: {"status":"ok","db":"ok","redis":"ok","kafka":"ok","s3":"ok"}

# 5. Start the UI services (web app + SOC dashboard)
docker compose --profile ui up --build -d

# 6. Open the demo
#    Web banking app:  http://localhost:5173
#    SOC dashboard:    http://localhost:5174
#    API docs (Swagger): http://localhost:8000/docs
```

> The gateway automatically runs Alembic migrations, seeds demo personas + policy, trains models if no artifacts exist, and submits the Flink feature-engine job — no manual steps required.

---

## Service URLs

| Service | URL | Notes |
|---------|-----|-------|
| Gateway API | http://localhost:8000 | FastAPI backend |
| API Swagger docs | http://localhost:8000/docs | Interactive API explorer |
| Web banking app | http://localhost:5173 | Central Bank of India UI |
| SOC / Fraud-ops dashboard | http://localhost:5174 | Analyst & admin tool |
| Flink Web UI | http://localhost:8081 | Job monitoring |
| MinIO console | http://localhost:9001 | S3 / data lake UI |
| PostgreSQL | localhost:5432 | DB: `cogniguard` |
| Redis | localhost:6379 | Online feature store |
| Kafka | localhost:9092 | Event streaming (KRaft mode) |

---

## Test Credentials

All credentials are seeded automatically when the gateway starts (`RUN_SEED_ON_START=true`).

### Banking App (web-app at :5173 / Android app)

| Role | Username | Password | Notes |
|------|----------|----------|-------|
| Demo customer | `genuine` | `Passw0rd!` | Known Mumbai device, seeded behavioral baseline — logs in as **low** risk |
| Demo impostor | `genuine` | `Passw0rd!` | Use the Tallinn fixture (`login_impostor.json`) against this account — fires `NEW_DEVICE` + `GEO_CHANGE` |

### SOC Dashboard (bank-dashboard at :5174)

| Role | Email | Password | Access |
|------|-------|----------|--------|
| Admin | `admin@cogniguard.dev` | `Passw0rd!` | Full access: policy write, model promote/rollback, case management |
| Analyst | `analyst@cogniguard.dev` | `Passw0rd!` | Read + case actions; cannot modify policy or models |

### Infrastructure

| Service | Username | Password |
|---------|----------|----------|
| MinIO console (:9001) | `minioadmin` | `minioadmin` |
| PostgreSQL | `cogniguard` | `cogniguard_dev_pw` |

### OTP (step-up auth)

The development OTP is always **`123456`** (hardcoded dev shortcut — see `adaptive_auth.py`). Configure real SMTP in `.env` to receive actual email OTPs.

### API Key usage

All customer-facing API endpoints require a JWT Bearer token obtained from `POST /api/v1/auth/login`. Admin endpoints require a separate JWT from `POST /api/v1/admin/login`.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in values before running:

```bash
cp .env.example .env
```

| Variable | Default (example) | Required | Description |
|----------|-------------------|----------|-------------|
| `POSTGRES_USER` | `cogniguard` | Yes | PostgreSQL username |
| `POSTGRES_PASSWORD` | `cogniguard_dev_pw` | Yes | PostgreSQL password |
| `POSTGRES_DB` | `cogniguard` | Yes | Database name |
| `DATABASE_URL` | `postgresql+psycopg://...` | Yes | Full SQLAlchemy DSN |
| `REDIS_URL` | `redis://redis:6379/0` | Yes | Redis connection URL |
| `KAFKA_BOOTSTRAP` | `kafka:9092` | Yes | Kafka bootstrap server |
| `S3_ENDPOINT` | `http://minio:9000` | Yes | MinIO/S3 endpoint |
| `S3_BUCKET` | `cogniguard` | Yes | S3 bucket name |
| `AWS_ACCESS_KEY_ID` | `minioadmin` | Yes | MinIO access key |
| `AWS_SECRET_ACCESS_KEY` | `minioadmin` | Yes | MinIO secret key |
| `JWT_SECRET` | `change_me_dev_only_super_secret` | **Change** | JWT signing secret |
| `JWT_ALG` | `HS256` | Yes | JWT algorithm |
| `JWT_TTL_MINUTES` | `30` | Yes | JWT expiry in minutes |
| `MODEL_DIR` | `/models` | Yes | Local model artifact directory |
| `APP_ENV` | `dev` | Yes | `dev` or `production` |
| `LOG_LEVEL` | `INFO` | Yes | Python log level |
| `RUN_MIGRATIONS_ON_START` | `true` | Yes | Auto-apply Alembic migrations |
| `RUN_SEED_ON_START` | `true` | Yes | Auto-seed demo data |
| `LOGIN_LATENCY_BUDGET_MS` | `300` | Yes | Login p95 target (ms) |
| `PAYMENT_LATENCY_BUDGET_MS` | `500` | Yes | Payment p95 target (ms) |
| `SMTP_HOST` | `smtp.gmail.com` | Optional | SMTP server for OTP email |
| `SMTP_PORT` | `587` | Optional | SMTP port |
| `SMTP_USERNAME` | — | Optional | SMTP login email |
| `SMTP_PASSWORD` | — | Optional | SMTP password / app password |
| `SMTP_FROM_EMAIL` | — | Optional | From address for OTP emails |
| `GROQ_API_KEY` | — | Optional | Groq API key for LLM case explanations |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Optional | Groq model ID |
| `VITE_API_BASE` | `http://localhost:8000` | Yes | Frontend → Gateway URL |
| `VITE_WS_BASE` | `ws://localhost:8000` | Yes | Frontend WebSocket URL |
| `VITE_SIGNING_SECRET` | `change_me_dev_only_super_secret` | **Change** | Dev-only SDK signing key (mirrors JWT_SECRET) |
| `VITE_ADMIN_TOKEN` | — | Optional | Legacy admin token (replaced by admin JWT) |

> **Security note:** `JWT_SECRET` and `VITE_SIGNING_SECRET` must be changed for any non-local deployment. Never commit `.env` to git.

---

## Repository Layout

```
Cogni_Guard/
├── docker-compose.yml          # Full stack orchestration
├── .env.example                # Environment variable template
├── .gitignore / .dockerignore
├── setup-demo.ps1              # Android demo prep script (Windows)
│
├── gateway/                    # FastAPI API gateway + scoring + decision (hot path)
│   ├── Dockerfile / entrypoint.sh / pyproject.toml
│   ├── alembic/ alembic.ini    # Database migrations (17 tables)
│   └── app/
│       ├── main.py             # App factory, lifespan, router mounting
│       ├── config.py           # Settings (env vars, Pydantic Settings)
│       ├── db.py / redis_client.py / kafka_client.py / s3_client.py / deps.py
│       ├── models/             # SQLAlchemy 2.x ORM models (17 tables)
│       ├── schemas/            # Pydantic v2 contracts (BehaviorPayload, ScoreResult, ...)
│       ├── routers/            # Thin HTTP handlers (auth, payment, behavior, risk, admin, ws, banking)
│       ├── services/           # Business logic (integrity, feature_reader, decision_engine,
│       │                       #   adaptive_auth, txn_fraud_layer, hardening, consent,
│       │                       #   audit, case_mgmt, broadcaster, identity, policy, ...)
│       ├── scoring/            # ML scoring (autoencoder, isolation_forest, calibration,
│       │                       #   xgboost_model, stack, shadow, explain, registry)
│       ├── jobs/               # Background jobs (quarantine, rtbf)
│       └── utils/              # Geo, fingerprint, security helpers
│   ├── scripts/                # seed_demo, generate_fraud_scenarios, load_datasets,
│   │                           #   seed_calibration, create_topics, demo_scenarios
│   └── tests/                  # pytest suite (200+ tests)
│       └── fixtures/           # Signed BehaviorPayload fixtures for all demo scenarios
│
├── flink-jobs/                 # PyFlink feature-engine (Kafka → Redis + S3 mirror)
│   ├── feature_engine.py       # Windowed velocity/sum, geo-distance, z-scores
│   ├── windows.py / sinks.py   # Pure-logic helpers (unit-testable without a cluster)
│   ├── Dockerfile              # Custom Flink 1.18 + PyFlink + dependencies
│   └── tests/                  # Window and sink unit tests
│
├── training/                   # Offline training + model registry + drift monitoring
│   ├── train_isolation_forest.py
│   ├── train_lstm_autoencoder.py  # Keras → ONNX + TFLite + calibration export
│   ├── train_xgboost.py
│   ├── train_transformer.py    # Experimental transformer model
│   ├── promote.py              # Champion/challenger promotion + rollback
│   ├── drift_monitor.py        # PSI/KS drift detection + challenger registration
│   ├── registry.py             # Model registry client (PostgreSQL + S3)
│   ├── s3_io.py                # S3/MinIO I/O helpers
│   ├── datasets/               # CMU, HMOG, INB, TXN dataset adapters
│   └── tests/                  # Drift monitor + registry tests
│
├── behavior-sdk/               # TypeScript behavioral capture SDK
│   ├── src/
│   │   ├── events.ts           # KeystrokeCapture, MouseCapture, TouchCapture
│   │   ├── fingerprint.ts      # Device fingerprint builder
│   │   ├── edge.ts             # Mobile edge feature extraction
│   │   ├── payload.ts          # Nonce fetch + HMAC-SHA256 signing
│   │   └── index.ts            # Public CogniGuard.init/attach/collect/startContinuous API
│   └── package.json / tsconfig.json / vitest.config.ts
│
├── web-app/                    # Central Bank of India Internet Banking (React + Vite)
│   ├── src/
│   │   ├── pages/              # Login, Dashboard, Transfer, Transactions, Security, StepUp
│   │   ├── components/         # UI components (Header, TransferForm, StepUpModal, ...)
│   │   └── api.ts              # Centralized API client
│   └── Dockerfile / package.json / tailwind.config.js
│
├── bank-dashboard/             # Fraud-ops / SOC dashboard (React + Vite + Recharts)
│   ├── src/
│   │   ├── pages/              # Live feed, UserDetail, Policy, Cases, Governance, DriftPanel
│   │   ├── components/         # RiskBadge, ScoreChart, CaseCard, ShapExplainer, ...
│   │   ├── ws.ts               # WebSocket client (SOC live feed)
│   │   └── api.ts              # Admin API client
│   └── Dockerfile / package.json / tailwind.config.js
│
├── android/                    # Native Kotlin Android app (Central Bank of India)
│   ├── app/                    # Demo Internet Banking app (Login, Dashboard, Transfer)
│   │   └── src/main/
│   │       ├── java/.../       # LoginActivity, DashboardActivity, TransferActivity, ...
│   │       └── res/            # Layouts, themes, network_security_config.xml
│   ├── capture-sdk/            # Kotlin behavioral capture SDK (on-device TFLite AE)
│   │   └── src/main/
│   │       ├── java/.../       # KeystrokeCapture, TouchCapture, AutoencoderTFLite,
│   │       │                   #   CogniGuardClient, Signer (HMAC-SHA256 matching TS/Python)
│   │       └── assets/         # model.tflite (copy from models/; gitignored)
│   ├── build.gradle.kts / settings.gradle.kts / gradle.properties
│   └── README.md               # Android setup instructions
│
├── models/                     # Local mirror of S3 model artifacts (gitignored binary files)
│   ├── isolation_forest/
│   ├── lstm_autoencoder/       # model.onnx
│   ├── lstm_autoencoder_tflite/# model.tflite (copy to android/capture-sdk/src/main/assets/)
│   └── xgboost_txn/
│
├── SAMPLE_DATA/                # Reference datasets (committed)
│   ├── DSL-StrongPasswordData.csv   # CMU keystroke dynamics
│   ├── hmog_features.csv            # HMOG touch/motion features
│   ├── INB_REQ_LOG.csv              # Internet banking request log
│   ├── TXN_HISTORY_UPI_FIN.csv      # UPI transaction history
│   └── eda_report.md
│
├── PRD.md                      # Product requirements (authoritative — what & why)
├── System Architecture.md      # Component contracts, schemas, flows (authoritative)
├── Implementation.md           # Phase-by-phase build plan (authoritative)
├── CLAUDE.md                   # Coding conventions + architecture invariants
└── PROGRESS.md                 # Living build tracker + team guide
```

---

## Component Details

### Gateway (FastAPI, Python 3.11+)

The API gateway is the only entry point. It handles:

- **Auth:** `POST /api/v1/auth/register`, `/auth/login`, `/auth/consent`, `/auth/logout`
- **Banking:** `GET /api/v1/banking/profile`, `/banking/accounts`, `/banking/transactions`, `/banking/beneficiaries`, `/banking/security-settings`
- **Behavior:** `POST /api/v1/behavior/ingest` (continuous re-scoring)
- **Payment:** `POST /api/v1/payment/score` (transaction risk + controls)
- **Risk:** `GET /api/v1/risk/session/{session_id}`
- **Admin:** `POST /api/v1/admin/login`, `GET/POST /api/v1/admin/cases`, `/admin/events`, `/admin/users`, `/admin/policy`, `/admin/models`, `/admin/drift`
- **WebSocket:** `WS /ws/soc-feed` (live risk_scores/decisions fan-out)

```bash
# Run gateway locally (outside Docker)
cd gateway
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

### Flink Feature Engine (PyFlink 1.18)

Consumes raw events from Kafka, computes windowed features, and writes them to Redis (hot path) and S3 (cold archive). Topics consumed: `behavior_events`, `device_events`, `login_events`, `transaction_events`.

The job is submitted automatically by the `flink-job-submit` compose service on startup. To resubmit manually after changing `feature_engine.py`:

```bash
# Cancel the running job via Flink UI at :8081, then:
docker compose up -d flink-job-submit
```

### Training (Offline ML)

```bash
# Load reference datasets into MinIO
docker compose exec gateway python -m scripts.load_datasets

# Train models (outputs to MinIO + registers in PostgreSQL model_registry)
docker compose exec gateway python -m training.train_isolation_forest
docker compose exec gateway python -m training.train_lstm_autoencoder
docker compose exec gateway python -m training.train_xgboost

# Check drift (PSI/KS)
docker compose exec gateway python -m training.drift_monitor

# Promote a challenger to production
docker compose exec gateway python -m training.promote --model xgboost_txn --version <ver> --to production
```

### behavior-sdk (TypeScript)

Framework-agnostic capture library used by the web app. Mirrors the gateway's HMAC signing scheme exactly.

```bash
cd behavior-sdk
npm install
npm run build    # compiles to dist/
npm test         # vitest (23 tests)
```

### web-app (React + Vite)

Central Bank of India Internet Banking demo. Login → Dashboard → Transfer + risk step-up flow.

```bash
cd web-app
npm install
npm run dev      # dev server at :5173
npm test         # vitest
npm run build    # production build
```

### bank-dashboard (React + Vite + Recharts)

Fraud-ops / SOC dashboard with live WebSocket feed, policy editor, case management, model governance (champion/challenger), and SHAP explainer.

```bash
cd bank-dashboard
npm install
npm run dev      # dev server at :5174
npm test         # vitest
npm run build    # production build
```

---

## Running Tests

### Backend (pytest)

```bash
# All gateway tests (200+ tests)
docker compose exec gateway python -m pytest -q

# Specific test file
docker compose exec gateway python -m pytest tests/test_auth_flow.py -v

# Flink feature-engine unit tests
docker compose exec -e PYTHONPATH=/flink-jobs gateway python -m pytest /flink-jobs/tests -q

# Training tests
docker compose exec gateway python -m pytest training/tests -q
```

### Frontend (Vitest)

```bash
cd behavior-sdk && npm test   # 23 tests
cd web-app && npm test        # 15 tests
cd bank-dashboard && npm test # 15 tests
```

### Android (instrumented)

```bash
cd android
# Copy TFLite model first (see Android Setup section)
./gradlew :capture-sdk:connectedAndroidTest   # requires connected device/emulator
./gradlew :app:assembleDebug
```

### Linting / type checking

```bash
# Python (from gateway/)
pip install ruff black
ruff check . && black --check .

# TypeScript (in each frontend package)
npm run lint     # ESLint
npx tsc --noEmit # type check
```

---

## Android Setup

The native Kotlin Android app (Central Bank of India) runs the **LSTM Autoencoder on-device** via TensorFlow Lite — only the reconstruction error leaves the device, never raw biometric streams.

### Prerequisites

1. Android SDK with `compileSdk 34` / `minSdk 26` installed
2. `ANDROID_HOME` environment variable set
3. Android Studio (Hedgehog+) or Gradle 8.4+

### Steps

```bash
cd android

# 1. Copy the TFLite model artifact
#    (generated by training/train_lstm_autoencoder.py → models/lstm_autoencoder_tflite/)
cp ../models/lstm_autoencoder_tflite/lstm_autoencoder@<version>/model.tflite \
   capture-sdk/src/main/assets/model.tflite

# 2. Build the debug APK
./gradlew :app:assembleDebug
#    APK output: android/app/build/outputs/apk/debug/app-debug.apk

# 3. Install on device/emulator
adb install app/build/outputs/apk/debug/app-debug.apk
```

### Physical device setup (ADB tunnel)

The app connects to the gateway at `http://127.0.0.1:8000`. On a physical device, set up a reverse tunnel so the phone's loopback reaches your host:

```powershell
# Windows — run setup-demo.ps1 (update the $device serial first)
.\setup-demo.ps1

# or manually:
adb -s <device-serial> reverse tcp:8000 tcp:8000
adb -s <device-serial> reverse tcp:5174 tcp:5174
```

For an emulator, use `http://10.0.2.2:8000` (standard host-loopback alias).

---

## Demo Scenarios

All scenarios use the seeded `genuine` user and pre-generated fixtures under `gateway/tests/fixtures/`.

### Scenario 1 — Happy Path (Low Risk → Allow)

```bash
# Web app: log in as genuine/Passw0rd! with a normal typing rhythm
# Expected: risk band=low, decision=allow, no step-up
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d @gateway/tests/fixtures/login_genuine.json | python -m json.tool
```

### Scenario 2 — ATO Impostor (High Risk → Verify)

```bash
# New device fingerprint (Tallinn) + erratic keystroke rhythm against genuine's account
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d @gateway/tests/fixtures/login_impostor.json | python -m json.tool
# Expected: NEW_DEVICE + GEO_CHANGE reason codes, decision=verify
```

### Scenario 3 — APP Fraud / Coercion (Amplifiers → Verify + Controls)

```bash
# After login, attempt a high-value transfer to scammer@upi (new beneficiary, <1h old)
curl -s -X POST http://localhost:8000/api/v1/payment/score \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <jwt>" \
  -d @gateway/tests/fixtures/txn_app_fraud.json | python -m json.tool
# Expected: NEW_BENEF_HIGHVAL ×1.5 amplifier, cooling period, manual amount entry
```

### Scenario 4 — Replay Attack (Rejected)

```bash
# Re-submit a previously accepted nonce — rejected immediately
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d @gateway/tests/fixtures/replay_login.json | python -m json.tool
# Expected: 401 NONCE_REUSED
```

### Scenario 5 — Mid-Session Hijack (Continuous Re-scoring)

```bash
# After a low-risk login, ingest behavior matching the hijack fixture
curl -s -X POST http://localhost:8000/api/v1/behavior/ingest \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <jwt>" \
  -d @gateway/tests/fixtures/ingest_hijack.json | python -m json.tool
# Expected: risk band escalates → session terminated + case opened
```

### Demo script (full end-to-end)

```bash
docker compose exec gateway python -m scripts.demo_scenarios
```

---

## ML Model Artifacts

Binary model files are **gitignored** (tracked in S3/MinIO, not in the repository). On a fresh clone, models are generated automatically on first startup if `RUN_SEED_ON_START=true` (the gateway calls the training scripts). You can also train them manually:

```bash
# Load reference datasets into MinIO first
docker compose exec gateway python -m scripts.load_datasets

# Train all three models
docker compose exec gateway python -m training.train_isolation_forest  # ~10 s
docker compose exec gateway python -m training.train_xgboost           # ~15 s
docker compose exec gateway python -m training.train_lstm_autoencoder  # ~2–5 min (TF)
```

Trained artifacts land in `models/` (bind-mounted from the host) and are registered in the `model_registry` PostgreSQL table. The gateway picks up the `production` model from the registry at startup.

### LSTM Autoencoder specifics

Architecture: `Input(16,9) → Masking → LSTM(32) → LSTM(16) → RepeatVector → LSTM(16,seq) → LSTM(32,seq) → TimeDistributed(Dense(9))`

- **Server-side (gateway):** served via ONNX Runtime from `models/lstm_autoencoder/`
- **Android (on-device):** TFLite flatbuffer from `models/lstm_autoencoder_tflite/` — copy to `android/capture-sdk/src/main/assets/model.tflite`
- **Calibration:** robust-z → logistic, per-user when enrolled else population fallback

---

## Build Status

All 30 implementation phases complete on `main`.

| Phase | Scope | Status |
|------:|-------|:------:|
| 0 | Scaffold, Docker Compose topology, gateway skeleton + `/health` | ✅ |
| 1 | PostgreSQL OLTP schema (17 tables) + Alembic | ✅ |
| 2 | Pydantic v2 canonical contracts | ✅ |
| 3 | Kafka topics + event production (6 topics) | ✅ |
| 4 | Flink feature engine (Kafka → Redis + S3) | ✅ |
| 5 | Feature reader (Redis-only) + dataset loaders + offline training | ✅ |
| 6 | Scoring service (IF → XGBoost stacked) + explainer + registry | ✅ |
| 7 | Decision engine + adaptive auth + risk×action matrix + txn-fraud layer | ✅ |
| 8 | Gateway flows: integrity, login, step-up, payment, JWT, hardening, consent, audit | ✅ |
| 9 | Continuous re-scoring + SOC WS broadcaster + case mgmt + RTBF/quarantine | ✅ |
| 10 | behavior-sdk (TypeScript) — HMAC-signed capture | ✅ |
| 11 | web-app + bank-dashboard (React + Vite) | ✅ |
| 12 | Model governance: registry, champion/challenger, drift, feedback loop | ✅ |
| 13 | Calibration layer + LSTM Autoencoder scoring module (ONNX) | ✅ |
| 14 | Schema + sequence buffer + feature-reader extensions for AE | ✅ |
| 15 | AE-primary / IF-shadow / fallback routing in the scoring stack | ✅ |
| 16 | LSTM Autoencoder training (ONNX + TFLite + calibration export) | ✅ |
| 17 | Cross-platform HMAC canonicalization (mobile AE fields) | ✅ |
| 18 | Native Android app + capture SDK (on-device TFLite) | ✅ |
| 19 | Docs realignment (PRD, CLAUDE.md, System Architecture) | ✅ |
| 20 | Per-user identity scorer (robust-z distance, identity-gated Trust Score) | ✅ |
| 21 | Data-driven enrollment (no seeding — derived from 10+ genuine cycles) | ✅ |
| 22 | Identity + Trust layer wired into `stack.score` | ✅ |
| 23 | `BEHAVIOR_IDENTITY_MISMATCH` reason code + band escalation | ✅ |
| 24 | Front-ends: calibration banner, Trust gauge, real Android BiometricPrompt | ✅ |
| 25 | Demo rehearsal & threshold tuning (two-user identity demo) | ✅ |
| 26 | Boot correctness: Flink auto-submit + AE calibration self-seeding | ✅ |
| 27 | Surface & persist trust signals (`trust_score`, `behavior_match_score`, `behavior_score_source`) | ✅ |
| 28 | Thin read-only banking endpoints (`/api/v1/banking/*`) | ✅ |
| 29 | web-app UI for banking endpoints (Transactions, Security pages) | ✅ |
| 30 | Real RBAC for `/admin/*` — separate `analysts` table + admin-track JWT | ✅ |

---

## License

MIT License — see [LICENSE](LICENSE).

This is a **research prototype** for a hackathon. Not for production use.
