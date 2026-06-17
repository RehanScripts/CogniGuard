# CogniGuard

**Real-Time Risk Orchestration Platform for Digital Banking** (Central Bank of India hackathon prototype).

CogniGuard is a real-time risk-orchestration layer in front of a bank's authentication and payment
rails. It continuously scores both the login session and every transaction, fuses behavioral,
device, network, transaction, and historical signals into one calibrated risk score (0–100), and
drives a decision — **allow**, **verify** (adaptive step-up), or **block** — inside tight latency
budgets (login p95 < 300 ms, payment p95 < 500 ms).

## Documentation (source of truth)

| Doc | Purpose |
|-----|---------|
| [`PROGRESS.md`](PROGRESS.md) | **Start here** — build status, new-laptop setup, team workflow, phase tracker. |
| [`PRD.md`](PRD.md) | The *what* & *why* — requirements, goals, demo scenarios. **Authoritative.** |
| [`System Architecture.md`](System%20Architecture.md) | The *how it fits together* — components, schema, topic/payload contracts, flows. |
| [`Implementation.md`](Implementation.md) | The *step-by-step build order* — phases 0–12, file-by-file. |
| [`CLAUDE.md`](CLAUDE.md) | Working conventions & architecture invariants. |

## Architecture (streaming ML)

```
Mobile/Web → API Gateway → Kafka → Flink Feature Engine → Redis Feature Store
           → Risk Models (Isolation Forest → XGBoost, stacked) → Decision Engine + Adaptive Auth
           → Bank Dashboard ; PostgreSQL (OLTP record) ; S3 (data lake)
```
Inference reads **only Redis** + the inline payload on the hot path. **No graph database / no
graph-based mule-network detection** (out of scope, all phases).

## Quick start

```bash
cp .env.example .env
docker compose up --build            # infra (postgres, redis, kafka, flink, minio) + gateway
curl -s http://localhost:8000/health | jq .

# Phase 1+: schema
docker compose exec gateway alembic upgrade head

# Phase 4: submit the Flink feature-engine job (Kafka → Redis + S3)
docker compose exec flink-jobmanager flink run -d -py /jobs/feature_engine.py

# UI services (Phase 11):
docker compose --profile ui up --build
```

| Service | URL |
|---------|-----|
| Gateway API + Swagger | http://localhost:8000/docs |
| Flink UI | http://localhost:8081 |
| MinIO console | http://localhost:9001 |
| Web banking demo (Phase 11) | http://localhost:5173 |
| Bank / SOC dashboard (Phase 11) | http://localhost:5174 |

## Repository layout

```
gateway/        FastAPI API gateway + scoring + decision (hot path)
flink-jobs/     PyFlink feature-engine jobs (Kafka → Redis + S3)
training/       offline training + model registry + drift (S3 → registry)
behavior-sdk/   TypeScript capture SDK (Phase 10)
web-app/        Internet Banking demo (Phase 11)
bank-dashboard/ Fraud-ops / SOC dashboard (Phase 11)
SAMPLE_DATA/    CMU, HMOG, INB_REQ_LOG, TXN_HISTORY_UPI_FIN datasets
models/         local mirror of S3 model artifacts
```

## Build status

- [x] Phase 0 — scaffold, Docker Compose topology, gateway skeleton + `/health`
- [x] Phase 1 — PostgreSQL OLTP schema (16 tables) + Alembic
- [x] Phase 2 — Pydantic canonical contracts (payloads, scoring, decision, topics)
- [x] Phase 3 — Kafka topics + event production (6 topics, fire-and-forget producers)
- [x] Phase 4 — Flink feature engine (Kafka → Redis online features + S3 raw mirror)
- [ ] Phases 5–12 — see [`Implementation.md`](Implementation.md)
