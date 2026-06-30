# CogniGuard

**Real-Time Risk Orchestration Platform for Digital Banking**  
Central Bank of India demo — CBI hackathon prototype.

CogniGuard sits in front of a bank's authentication and payment rails, continuously scores every login session and transaction using behavioral biometrics + ML, and drives **allow / verify / block** decisions inside tight latency budgets (login p95 < 300 ms, payment p95 < 500 ms).

> **Prototype only.** Do not connect to production banking infrastructure.

---

## Quick Start

```bash
git clone https://github.com/xemorph64/Cogni_Guard.git
cd Cogni_Guard
cp .env.example .env          # edit SMTP_* and GROQ_API_KEY if needed (both optional)
docker compose up --build -d  # ~5–8 min first run
make health                   # {"status":"ok","db":"ok","redis":"ok","kafka":"ok","s3":"ok"}
docker compose --profile ui up -d  # start web app + SOC dashboard
```

| Service | URL |
|---------|-----|
| API (Swagger docs) | http://localhost:8000/docs |
| Web banking app | http://localhost:5173 |
| SOC / Fraud-ops dashboard | http://localhost:5174 |
| Flink Web UI | http://localhost:8081 |
| MinIO console | http://localhost:9001 |

> The gateway auto-runs migrations, seeds demo personas + policy, trains models if absent, and submits the Flink feature-engine job — no manual steps required.

---

## Common Commands

```bash
make up          # start core stack
make up-ui       # start core stack + frontend services
make test        # run all backend tests
make lint        # ruff + black + eslint
make seed        # re-seed demo data
make train       # train / retrain all ML models
make help        # full command reference
```

---

## Documentation

| Doc | Contents |
|-----|----------|
| [docs/test-credentials.md](docs/test-credentials.md) | All login credentials, API tokens, OTP code |
| [docs/architecture.md](docs/architecture.md) | Pipeline diagram, invariants, risk bands, Kafka topics |
| [docs/api-reference.md](docs/api-reference.md) | All API endpoints with request / response shapes |
| [docs/demo-scenarios.md](docs/demo-scenarios.md) | 5 reproducible demo scenarios with curl commands |
| [docs/android-setup.md](docs/android-setup.md) | Android build, TFLite model copy, ADB tunnel setup |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Branching, commit format, coding standards, PR process |
| [SECURITY.md](SECURITY.md) | Security controls, known limitations, vulnerability reporting |

---

## Repository Layout

```
Cogni_Guard/
├── gateway/                    # FastAPI API gateway + scoring + decision engine
│   ├── app/
│   │   ├── routers/            # Thin HTTP handlers (auth, payment, behavior, admin, ws, banking)
│   │   ├── services/           # Business logic (integrity, auth_flow, decision_engine, ...)
│   │   ├── scoring/            # ML stack (autoencoder, isolation_forest, xgboost, calibration, ...)
│   │   ├── models/             # SQLAlchemy ORM (17 tables)
│   │   └── schemas/            # Pydantic v2 contracts (BehaviorPayload, DecisionResponse, ...)
│   ├── scripts/                # seed_demo, generate_fraud_scenarios, load_datasets, ...
│   └── tests/                  # pytest suite (200+ tests) + signed fixtures
│
├── flink-jobs/                 # PyFlink feature engine (Kafka → Redis online features + S3)
├── training/                   # Offline ML training + model registry + drift monitoring
├── behavior-sdk/               # TypeScript behavioral capture SDK (HMAC-signed payloads)
├── web-app/                    # Central Bank of India Internet Banking (React + Vite)
├── bank-dashboard/             # Fraud-ops / SOC dashboard (React + Vite + Recharts)
├── android/                    # Native Kotlin app + on-device TFLite capture SDK
├── central-bank-of-india/      # Web portal simulator (AI Studio / standalone)
├── central-bank-android-simulator/ # Android UI simulator (AI Studio / standalone)
├── SAMPLE_DATA/                # Reference datasets (CMU, HMOG, INB_REQ_LOG, TXN_HISTORY_UPI_FIN)
├── models/                     # Local mirror of S3 model artifacts (gitignored binaries)
├── docs/                       # Extended documentation
├── docker-compose.yml
├── Makefile
├── .env.example
├── CONTRIBUTING.md
├── SECURITY.md
└── LICENSE
```

---

## Architecture (summary)

```
Mobile/Web → API Gateway → Kafka → Flink Feature Engine → Redis Feature Store
           → LSTM Autoencoder (ONNX) + XGBoost (stacked) → Decision Engine
           → PostgreSQL (audit) + SOC Dashboard (WebSocket)
```

Inference reads **Redis only** on the hot path — never PostgreSQL.  
Full details: [docs/architecture.md](docs/architecture.md)

---

## Tech Stack

| Layer | Stack |
|-------|-------|
| API gateway | Python 3.11, FastAPI, Pydantic v2, Uvicorn |
| Streaming | Apache Kafka (KRaft), Apache Flink (PyFlink) |
| Feature store | Redis 7 |
| OLTP | PostgreSQL 16, SQLAlchemy 2.x, Alembic |
| Data lake | MinIO (S3-compatible) |
| ML — behavioral | LSTM Autoencoder (Keras → ONNX + TFLite) + Isolation Forest |
| ML — transaction | XGBoost (stacked with `Behavior_Score`) |
| ML — explainability | SHAP + optional Groq LLM narratives |
| Frontend | React 18, TypeScript, Vite, Tailwind, Recharts |
| Mobile | Kotlin, TensorFlow Lite (on-device AE inference) |
| Auth | Argon2id passwords, PyJWT sessions, HMAC-SHA256 payload signing |

---

## License

MIT — see [LICENSE](LICENSE).
