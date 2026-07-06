<p align="center">
  <img src="docs/assets/icon.png" alt="CogniGuard Logo" width="440" />
</p>

<h1 align="center">CogniGuard</h1>
<p align="center"><b>Real-Time Risk Orchestration for Digital Banking</b></p>
<p align="center">
  Continuous behavioral biometrics · ML-powered fraud detection · Adaptive step-up auth
</p>

<p align="center">
  <a href="https://github.com/xemorph64/Cogni_Guard/actions/workflows/ci.yml">
    <img src="https://github.com/xemorph64/Cogni_Guard/actions/workflows/ci.yml/badge.svg" alt="CI" />
  </a>
  <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT" />
  <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/TypeScript-strict-blue.svg" alt="TypeScript" />
  <img src="https://img.shields.io/badge/stage-Business%20MVP-brightgreen.svg" alt="Stage: Business MVP" />
  <img src="https://img.shields.io/badge/domain-FinTech%20%7C%20Fraud%20Prevention-orange.svg" alt="Domain" />
</p>

<p align="center">
  <a href="#-problem">Problem</a> ·
  <a href="#-solution">Solution</a> ·
  <a href="#user-flow">User Flow</a> ·
  <a href="#-core-capabilities">Capabilities</a> ·
  <a href="#%EF%B8%8F-architecture">Architecture</a> ·
  <a href="#-quick-start">Quick Start</a> ·
  <a href="#-demo-scenarios">Demos</a> ·
  <a href="#-documentation">Docs</a>
</p>

---

> **CogniGuard is a business-ready MVP prototype** built for the Central Bank of India Hackathon — demonstrating a commercially viable continuous risk-orchestration platform for digital banking fraud prevention. The system is production-architected and designed for direct integration into existing banking infrastructure.

---

## Screenshots

<p align="center">
  <img src="docs/assets/screenshot-mobile-banking.png" alt="Mobile Banking App" width="320"/><br/>
  <sub><b>Customer-Facing Mobile Banking</b></sub>
</p>

<p align="center">
  <img src="docs/assets/screenshot-soc-dashboard.png" alt="SOC Dashboard" width="320"/><br/>
  <sub><b>SOC Fraud-Ops Dashboard</b></sub>
</p>

---

## Problem

Digital banking fraud in India has surged with the rise of UPI and mobile-first banking. Existing defences share a critical blind spot: they **verify identity once at login, then trust the session completely**. This leaves three high-value attack vectors undetected:

| Threat | Why existing solutions miss it |
|--------|-------------------------------|
| **Account Takeover (ATO)** | Attacker has valid stolen credentials — anomaly is only visible in *behaviour*: wrong device, wrong city, wrong typing rhythm. |
| **Mid-session hijack (RAT/MITM)** | Malware takes over an already-authenticated session. Identity check already passed; re-auth is never triggered. |
| **APP fraud / "Digital Arrest" scams** | The *genuine* customer is coerced into pressing Send. Biometric identity is correct — the danger is in the *transaction context*, not the person. |

These three account for the majority of high-value banking fraud losses in India and are **invisible to identity-only, point-in-time verification**.

---

## Solution

CogniGuard is a **continuous risk-orchestration layer** that sits transparently between users and a bank's existing rails. Rather than checking identity once, it:

1. **Scores every login and every transaction** using a fusion of behavioral biometrics, device signals, transaction context, and historical patterns.
2. **Re-scores continuously throughout the session** — a low-risk login can escalate if behaviour deviates mid-session.
3. **Drives adaptive decisions in real time** — `allow`, `verify` (step-up MFA), or `block` — inside tight latency budgets (**login p95 < 300 ms, payment p95 < 500 ms**).

The single output is a calibrated **Risk Score (0–100)** that feeds a policy-driven decision engine. Every `verify`/`block` carries machine-readable **reason codes** and a SHAP-powered explanation so analysts understand exactly why a decision was made.

### What Makes This Different

| Capability | Typical bank solution | CogniGuard |
|------------|----------------------|------------|
| Risk evaluation timing | Once at login | Continuously throughout session |
| Behavioral biometrics | Absent | LSTM Autoencoder on keystroke / touch / motion |
| On-device ML | Absent | TFLite autoencoder on Android — only reconstruction error leaves the device |
| APP fraud / coercion detection | Absent | Dynamic Risk Amplifiers + transaction-fraud controls |
| Step-up friction | Fixed OTP for all risk | Assurance-ordered: lightest factor that clears measured risk |
| Explainability | Black box | SHAP feature attribution + LLM case narratives for analysts |
| Telemetry integrity | None | HMAC-SHA256 + single-use nonce — replay and RAT attacks rejected |
| Cold-start handling | Often blocks new users | Isolation Forest + rules; always biases to `verify`, never `block` |

---

## User Flow

<p align="center">
  <img src="docs/assets/user-flow.png" alt="CogniGuard user login and transaction journey" width="720" />
</p>

Login risk is scored from behavioral biometrics alone and routes to zero-friction `allow`, a light or strong step-up `verify`, or an outright `block` + SOC alert. The session keeps re-scoring afterward, so a hijack that surfaces only after login still forces re-authentication. At transaction time, the same risk stack layers on Dynamic Risk Amplifiers (new payee, high value, odd hour, coercion signals) — so a transfer can still be held for a coercion-confirm / cooling-off / out-of-band check even when the login itself looked genuine.

---

## Core Capabilities

<details>
<summary><b>Behavioral Biometrics</b></summary>

- Captures keystroke dynamics (dwell time, flight time, inter-key latency), mouse movement, and touch/swipe patterns via the `behavior-sdk` (TypeScript) and native Android `capture-sdk` (Kotlin).
- On Android, an **LSTM Autoencoder runs on-device via TensorFlow Lite** — raw biometric streams never leave the phone. Only the reconstruction error is transmitted.
- Per-user behavioral baseline is built from genuine sessions and updated continuously (anti-poisoning quarantine prevents compromised sessions from polluting the baseline).

</details>

<details>
<summary><b>Stacked ML Scoring Pipeline</b></summary>

```
Raw events → Flink (windowed features) → Redis
                                          │
                        LSTM Autoencoder (ONNX) ──┐
                                                   ├→ Behavior_Score → XGBoost → Fraud Probability
                        Isolation Forest (shadow) ─┘       │
                                                      Decision Engine
                                                      (policy thresholds)
```

- **LSTM Autoencoder** (primary): reconstruction error over a 16-step, 9-dimensional behavioral window → calibration layer → `Behavior_Score`.
- **Isolation Forest** (shadow / fallback): runs in parallel, promoted to live score only on cold-start or AE failure.
- **XGBoost** (transaction): stacks `Behavior_Score` with transaction and device features → single calibrated fraud probability.

</details>

<details>
<summary><b>APP Fraud & Coercion Detection</b></summary>

When a genuine customer is coerced into transferring money, their biometrics pass — the threat is in the transaction, not the identity. CogniGuard catches this via **Dynamic Risk Amplifiers** applied at payment time:

| Amplifier | Trigger | Effect |
|-----------|---------|--------|
| `NEW_BENEF_HIGHVAL` | New beneficiary + high amount | ×1.5 score multiplier |
| `RAPID_FAN_OUT` | Multiple new beneficiaries rapidly | ×1.4 |
| `DRAIN_MAX_OUT` | Transfer approaches account limit | ×1.3 |
| `COERCION_TIME` | Active call detected during transfer | ×1.2 |

Triggered controls: **Cooling Period**, **Reconfirmation** (out-of-band "was this you?"), **Manual Amount Entry**, and **Coercion Check**.

</details>

<details>
<summary><b>Identity Verification Layer</b></summary>

Per-user identity scoring using robust-z distance from the enrolled behavioral baseline. After ≥10 genuine cycles, the system builds a per-user profile; subsequent sessions are compared against it. `BEHAVIOR_IDENTITY_MISMATCH` fires as a reason code and escalates the risk band when a session deviates significantly from the enrolled owner.

</details>

<details>
<summary><b>Adaptive Step-Up Authentication</b></summary>

Picks the **lightest assurance factor that clears the measured risk** — never over-challenges:

| Risk Band | Score | Action | Challenge |
|-----------|-------|--------|-----------|
| Low | 0–30 | `allow` | None |
| Medium | 30–60 | `verify` | OTP / MPIN |
| High | 60–85 | `verify` | Device biometric / passkey |
| Very High | ≥85 | `block` | Session terminated + alert |

</details>

<details>
<summary><b>Anti-Replay & Telemetry Integrity</b></summary>

Every behavioral payload carries a **server-issued single-use nonce**, monotonic sequence number, timestamp, and `HMAC-SHA256(nonce ‖ canonical(metrics) ‖ fingerprint ‖ ts)`. The gateway verifies and consumes the nonce before trusting any payload. Replayed or tampered payloads are rejected with `401 NONCE_REUSED`.

</details>

<details>
<summary><b>Real-Time SOC Dashboard</b></summary>

- Live event feed via WebSocket (`/ws/soc-feed`) streaming every risk score and decision.
- Case management: open, assign, note, and resolve fraud cases (`confirmed_fraud` / `false_positive`).
- Policy editor: adjust risk thresholds and amplifier multipliers without redeployment.
- Model governance: champion/challenger framework — challenger models score in shadow before promotion; drift monitor (PSI/KS) triggers retrain.
- SHAP explainer + optional Groq LLM narrative for each decision.

</details>

<details>
<summary><b>Compliance (DPDP Act 2023 + RBI Guidelines)</b></summary>

- Behavioral capture is **consent-gated** — no processing without recorded consent; minors excluded.
- Raw biometric streams **minimized at source** (mobile edge extraction; only derived features transmitted).
- **Right to be forgotten**: cascading hard-delete of `behavior_samples` + per-user model artifacts, retaining only anonymised audit rows.
- Full **immutable decision audit trail** with `model_version`, latency, and reason codes on every row.
- **In-region data residency** configurable; no cross-border transfer by default.

</details>

---

## Threat Coverage

| Threat | Detection mechanism | Response |
|--------|--------------------|---------:|
| ATO with stolen credentials | New device / geo + behavioral deviation | `verify` / `block` |
| Mid-session RAT hijack | Continuous re-scoring detects rhythm change | Session terminated + case |
| Credential-stuffing | IP/device throttle (never account lockout) | 429 on offending IP |
| Replay / MITM | HMAC-SHA256 + single-use nonce | `401 NONCE_REUSED` |
| APP fraud / coercion | Amplifiers + transaction-fraud controls | Cooling + reconfirmation |
| New-beneficiary high-value drain | `NEW_BENEF_HIGHVAL` amplifier | Manual amount entry |
| Bot / scripted login | Behavioral reconstruction error spike | `block` |
| Model poisoning | Step-up telemetry quarantine | Quarantine → cooling window |

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Client Layer                                   │
│  Web App (React)  ·  Android App (Kotlin)       │
│  behavior-sdk (TS) ·  capture-sdk (Kotlin)      │
│  HMAC-signed payloads, nonce-bound, seq-checked │
└───────────────────┬─────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────┐
│  API Gateway  :8000  (FastAPI · Python 3.11)    │
│  Auth · Integrity · Payment · Behavior · Admin  │
└───────────┬──────────────────────┬──────────────┘
            │ Kafka events         │ Decisions (WS)
            ▼                      ▼
┌──────────────────┐    ┌──────────────────────────┐
│  Apache Flink    │    │  SOC Dashboard  :5174     │
│  Feature Engine  │    │  (React + Recharts)       │
│  windowed stats  │    │  Live feed · Cases · SHAP │
└───────┬──────────┘    └──────────────────────────┘
        │ Online features
        ▼
┌──────────────┐   ┌────────────────────────────────┐
│  Redis 7     │──▶│  Scoring Stack                 │
│  Feature     │   │  LSTM AE (ONNX) → Behavior_Score│
│  Store       │   │  Isolation Forest (shadow/fb)  │
└──────────────┘   │  XGBoost (stacked)             │
                   │  Identity Scorer               │
                   │  Decision Engine + Amplifiers  │
                   └────────────────────────────────┘
        │
        ├──▶ PostgreSQL 16  (audit · OLTP · off hot-path)
        └──▶ MinIO / S3     (data lake · model artifacts)
```

> Inference reads **Redis only** — PostgreSQL is never on the hot path. Full invariant list: [docs/architecture.md](docs/architecture.md).

---

## Quick Start

**Prerequisites:** Docker 24+, Docker Compose v2, Git.

```bash
git clone https://github.com/xemorph64/Cogni_Guard.git
cd Cogni_Guard
cp .env.example .env          # SMTP_* and GROQ_API_KEY are optional
docker compose up --build -d  # first run ~5–8 min
make health                   # expect: {"status":"ok","db":"ok","redis":"ok","kafka":"ok","s3":"ok"}
docker compose --profile ui up -d  # start web app + SOC dashboard
```

| Service | URL | Purpose |
|---------|-----|---------|
| API + Swagger | http://localhost:8000/docs | Explore all endpoints interactively |
| Web banking app | http://localhost:5173 | Customer-facing demo (login, transfer, step-up) |
| SOC dashboard | http://localhost:5174 | Analyst/admin fraud-ops tool |
| Flink UI | http://localhost:8081 | Feature-engine job monitoring |
| MinIO console | http://localhost:9001 | Data lake / model artifact browser |

> The gateway automatically applies migrations, seeds demo data, trains models if no artifacts are found, and submits the Flink feature-engine job. No manual steps needed beyond `docker compose up`.

---

## Test Credentials

Full credentials reference: **[docs/test-credentials.md](docs/test-credentials.md)**

| Role | Login | Password |
|------|-------|----------|
| Bank customer | `genuine` | `Passw0rd!` |
| SOC Admin | `admin@cogniguard.dev` | `Passw0rd!` |
| SOC Analyst | `analyst@cogniguard.dev` | `Passw0rd!` |
| MinIO console | `minioadmin` | `minioadmin` |

Step-up OTP (dev): **`123456`**

---

## Demo Scenarios

Five reproducible scenarios — full curl commands in **[docs/demo-scenarios.md](docs/demo-scenarios.md)**.

| # | Scenario | Expected Outcome |
|---|----------|-----------------|
| 1 | Genuine customer, normal rhythm | `allow` · band `low` |
| 2 | Impostor — new device (Tallinn) + erratic typing | `verify` · `NEW_DEVICE` + `GEO_CHANGE` |
| 3 | High-value transfer to new beneficiary (coercion) | `verify` · `NEW_BENEF_HIGHVAL ×1.5` · cooling |
| 4 | Replay attack (reused nonce) | `401 NONCE_REUSED` |
| 5 | Mid-session hijack (continuous re-scoring) | `block` · session terminated · case opened |

---

## Repository Layout

```
Cogni_Guard/
├── gateway/                    # FastAPI API gateway + scoring + decision engine
│   ├── app/
│   │   ├── routers/            # Thin HTTP handlers
│   │   ├── services/           # Business logic (auth, payment, decision, identity, …)
│   │   ├── scoring/            # ML stack (AE, IF, XGBoost, calibration, SHAP, …)
│   │   ├── models/             # SQLAlchemy ORM (17 tables)
│   │   └── schemas/            # Pydantic v2 contracts
│   ├── scripts/                # Seed, fixture generation, dataset loading
│   └── tests/                  # 200+ pytest tests + signed demo fixtures
│
├── flink-jobs/                 # PyFlink feature engine (Kafka → Redis + S3)
├── training/                   # Offline ML training, model registry, drift monitor
├── behavior-sdk/               # TypeScript capture SDK (HMAC-signed behavioral payloads)
├── web-app/                    # CBI Internet Banking frontend (React + Vite + Tailwind)
├── bank-dashboard/             # SOC / Fraud-ops dashboard (React + Recharts)
├── android/                    # Native Kotlin app + on-device TFLite capture SDK
├── central-bank-of-india/      # Standalone web portal simulator
├── central-bank-android-simulator/ # Standalone Android UI simulator
├── SAMPLE_DATA/                # CMU keystroke, HMOG touch, INB_REQ_LOG, TXN_HISTORY_UPI_FIN
├── models/                     # Local model artifact mirror (binaries gitignored)
└── docs/                       # Extended documentation
    ├── test-credentials.md
    ├── architecture.md
    ├── api-reference.md
    ├── demo-scenarios.md
    └── android-setup.md
```

---

## Common Commands

```bash
make up             # start core stack (detached)
make up-ui          # + web app and SOC dashboard
make test           # pytest + flink unit tests
make test-frontend  # vitest (behavior-sdk, web-app, bank-dashboard)
make lint           # ruff + black + eslint
make seed           # re-seed demo personas and policy
make train          # load datasets + train all ML models
make help           # full command reference
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API gateway | Python 3.11 · FastAPI · Pydantic v2 · Uvicorn |
| Event streaming | Apache Kafka 3.7 (KRaft, no ZooKeeper) |
| Stream processing | Apache Flink 1.18 (PyFlink) |
| Online feature store | Redis 7 |
| OLTP database | PostgreSQL 16 · SQLAlchemy 2.x · Alembic |
| Data lake / model store | MinIO (S3-compatible) |
| ML — behavioral (server) | LSTM Autoencoder (Keras → ONNX Runtime) |
| ML — behavioral (mobile) | LSTM Autoencoder (TensorFlow Lite, on-device) |
| ML — shadow / fallback | scikit-learn Isolation Forest |
| ML — transaction | XGBoost (stacked with `Behavior_Score`) |
| ML — explainability | SHAP · Groq LLM (optional) |
| Web frontend | React 18 · TypeScript · Vite · Tailwind · Recharts |
| Mobile | Kotlin · Android SDK 34 · TensorFlow Lite |
| Auth & integrity | Argon2id · PyJWT · HMAC-SHA256 + nonce binding |
| Containerisation | Docker · Docker Compose |
| CI | GitHub Actions (pytest · vitest · tsc · ruff · black) |

---

## Roadmap

These capabilities are architecturally planned and ready for the next development phase:

- [ ] **Real-time model retraining pipeline** — automated drift-triggered retrain via MLflow + Airflow
- [ ] **Graph-based mule network detection** — Neo4j relationship graph over beneficiary transfers
- [ ] **Federated behavioral model** — privacy-preserving cross-bank baseline without data sharing
- [ ] **Voice/video deepfake detection** — liveness signal for call-centre and video KYC flows
- [ ] **Native iOS SDK** — equivalent of the Android `capture-sdk` for CoreML
- [ ] **Multi-tenant SaaS API** — white-label risk-as-a-service for smaller banks and fintechs
- [ ] **RBI sandbox integration** — test against the RBI regulatory sandbox environment

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/test-credentials.md](docs/test-credentials.md) | All login credentials, API tokens, OTP |
| [docs/architecture.md](docs/architecture.md) | Pipeline diagram, invariants, risk bands, Kafka topics |
| [docs/api-reference.md](docs/api-reference.md) | Full REST + WebSocket endpoint reference |
| [docs/demo-scenarios.md](docs/demo-scenarios.md) | 5 reproducible scenarios with curl commands |
| [docs/android-setup.md](docs/android-setup.md) | TFLite model copy, build, ADB tunnel |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development workflow, standards, PR process |
| [SECURITY.md](SECURITY.md) | Security controls, known limitations |

---

## Contributing

Contributions, issues, and feature requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on the development workflow, coding standards, and PR process.

---

## License

MIT — see [LICENSE](LICENSE).

---

<p align="center">
  Built for the <b>Central Bank of India Hackathon</b> · Business MVP prototype demonstrating commercially viable fraud prevention for India's digital banking ecosystem.
</p>
