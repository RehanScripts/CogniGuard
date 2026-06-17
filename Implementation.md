# Implementation Plan — **CogniGuard**

## Real-Time Risk Orchestration Platform for Digital Banking

**Companion to:** `PRD.md`, `System Architecture.md`
**Audience:** Claude Code (the implementing agent)
**Version:** 3.0 · 2026-06-17 — aligned with PRD v2.0 (orchestration rewrite) / Architecture v3.0
**Purpose:** A precise, phase-by-phase BUILD PLAN for the **full production streaming stack** (Kafka · Flink · Redis feature store · S3 · XGBoost + Isolation Forest). Describes **HOW** to build it, file-by-file, in order. It does not re-explain product vision (`PRD.md`) or component theory (`System Architecture.md`). Names, stack, schema, topics, endpoints, repo structure, and the scoring approach here are **canonical and must match the two source docs exactly**.

> **Scope guardrail (PRD v2.0):** **no graph database, no graph-based mule-network detection** in any phase. Model stack is **XGBoost (primary) + Isolation Forest (anomaly net)**, stacked; **LSTM/Transformer is Phase 2 only**. Decisions are `allow` / `verify` / `block`; bands `low`/`medium`/`high`/`very_high`.

---

## 1. Overview & Build Philosophy

### 1.1 Principles
- **Vertical slices over horizontal layers.** Each phase delivers a runnable, testable increment through the streaming path. After Phase 8 you have a working login/payment → decision loop; later phases add continuous scoring, UI, and governance.
- **Streaming-first, Redis-only inference.** Build the event log → feature engine → feature store backbone early; the scoring hot path reads **only Redis** + the inline payload, never PostgreSQL, never Flink.
- **Test as you go.** Every phase ends with an **acceptance check** (`curl`, `pytest`, a Kafka/Redis probe, or a UI action). Do not start phase N+1 until phase N passes.
- **Backend-first, then SDK, then UI.** The scoring brain + decision engine are the differentiator; prove them with `curl`/pytest before any pixels.
- **Deterministic demo.** All randomness in the fraud-scenario generator and seed script is seeded (`numpy.random.default_rng(SEED)`).
- **Graceful degradation is a feature** (NFR-4): a sane decision even when XGBoost is down (→ IF + rules), Redis is degraded (→ bias `verify`), or scoring times out (→ safe action). Tag `degraded_mode`.

### 1.2 How to verify the whole thing runs
```bash
# Infra + gateway (fast inner loop)
docker compose up --build postgres redis kafka flink-jobmanager flink-taskmanager minio gateway
curl -s http://localhost:8000/health | jq .

# Full stack
docker compose up --build
# web-app:        http://localhost:5173
# bank-dashboard: http://localhost:5174
# gateway docs:   http://localhost:8000/docs
# flink ui:       http://localhost:8081
# minio console:  http://localhost:9001
```

### 1.3 Build order (phase map)
| Phase | Slice | Runnable result |
|------|-------|-----------------|
| 0 | Scaffold + Docker Compose (pg, redis, kafka, flink, minio) + gateway skeleton | `/health` returns 200 |
| 1 | PostgreSQL OLTP schema (16 tables) + Alembic + infra clients | `alembic upgrade head`; `/health` pings pg/redis/kafka/s3 |
| 2 | Pydantic schemas (payloads, feature bundle, score, decision, topic contracts) | importable, validate sample payloads |
| 3 | Kafka topics + event production from the gateway | events land on input topics |
| 4 | Flink Feature Engine (Kafka → Redis features + S3 mirror) | Redis feature keys populate from the stream |
| 5 | Feature reader (Redis-only) + dataset loaders + offline training | feature bundle assembled; joblib/xgb artifacts in S3 |
| 6 | Scoring service: IsolationForest → XGBoost (stacked) + explain + registry | score + reason codes for a feature bundle |
| 7 | Decision Engine + adaptive auth + risk×action + amplifiers + txn-fraud layer | band → action → factors |
| 8 | Gateway flows: integrity, login, step-up, payment, JWT, hardening, consent, audit | `/auth/login` + `/payment/score` return `DecisionResponse` |
| 9 | Continuous re-scoring + SOC broadcaster (WS) + case mgmt + RTBF/quarantine jobs | `/behavior/ingest` + `/ws/soc-feed` live |
| 10 | behavior-sdk (TS) | capture + signed payload in browser |
| 11 | web-app + bank-dashboard | full demo, all PRD scenarios |
| 12 | Model governance: registry, champion/challenger, drift, feedback loop | shadow scoring + promotion + drift alerts |

---

## 2. Prerequisites & Environment

### 2.1 Versions
| Tool | Version |
|------|---------|
| Python | 3.11+ |
| Node | 20 LTS |
| PostgreSQL | 16 |
| Redis | 7 |
| Kafka | 3.6+ (KRaft, no ZooKeeper) |
| Flink | 1.18 (PyFlink) |
| MinIO (S3) | latest |
| Docker / Compose | latest |

### 2.2 Gateway Python dependencies (`gateway/pyproject.toml`)
```toml
[project]
name = "cogniguard-gateway"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.110", "uvicorn[standard]>=0.29",
  "sqlalchemy>=2.0", "alembic>=1.13", "psycopg[binary]>=3.1",
  "redis>=5.0", "confluent-kafka>=2.3", "boto3>=1.34",
  "pydantic>=2.6", "pydantic-settings>=2.2",
  "scikit-learn>=1.4", "xgboost>=2.0",
  "numpy>=1.26", "pandas>=2.2", "scipy>=1.12", "joblib>=1.3",
  "pyjwt>=2.8", "argon2-cffi>=23.1", "python-multipart>=0.0.9", "websockets>=12.0",
]
[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "httpx>=0.27"]
```
> `flink-jobs/` and `training/` have their own `requirements.txt` (PyFlink, xgboost, scikit-learn, boto3, redis, confluent-kafka). The Flink job runs in the Flink container, not the gateway image.

### 2.3 `.env` (repo root)
```dotenv
# --- Postgres ---
POSTGRES_USER=cogniguard
POSTGRES_PASSWORD=cogniguard_dev_pw
POSTGRES_DB=cogniguard
DATABASE_URL=postgresql+psycopg://cogniguard:cogniguard_dev_pw@postgres:5432/cogniguard
# --- Redis (online feature store) ---
REDIS_URL=redis://redis:6379/0
# --- Kafka ---
KAFKA_BOOTSTRAP=kafka:9092
# --- S3 / MinIO (data lake + model store) ---
S3_ENDPOINT=http://minio:9000
S3_BUCKET=cogniguard
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
# --- Auth / integrity ---
JWT_SECRET=change_me_dev_only_super_secret
JWT_ALG=HS256
JWT_TTL_MINUTES=30
# --- ML ---
MODEL_DIR=/models
# --- App ---
APP_ENV=dev
LOG_LEVEL=INFO
RUN_MIGRATIONS_ON_START=true
RUN_SEED_ON_START=true
LOGIN_LATENCY_BUDGET_MS=300
PAYMENT_LATENCY_BUDGET_MS=500
# --- Frontend (Vite) ---
VITE_API_BASE=http://localhost:8000
VITE_WS_BASE=ws://localhost:8000
```
> `config.py` reads these via `pydantic-settings`. Inside containers hostnames are service names; host-run dev swaps to `localhost`.

### 2.4 Bring up infra
```bash
docker compose up -d postgres redis kafka flink-jobmanager flink-taskmanager minio
docker compose up --build gateway
```

---

## 3. Phased Plan

> Each phase lists: **Goal**, **Files** (exact paths from Architecture §9), **Contents** (signatures), **Acceptance check**, **Depends on**.

---

### Phase 0 — Repo Scaffold, Docker Compose, Gateway Skeleton

**Goal:** A runnable FastAPI gateway with config + health; full repo tree; one-command compose for the streaming infra + gateway.

**Files:**
```
cogniguard/
├── docker-compose.yml · .env · .gitignore · README.md · models/.gitkeep
├── gateway/
│   ├── pyproject.toml · Dockerfile · .dockerignore
│   └── app/__init__.py · main.py · config.py · db.py · redis_client.py · kafka_client.py · s3_client.py
├── flink-jobs/__init__.py · requirements.txt
└── training/__init__.py · requirements.txt
```

**`gateway/app/config.py`** — `Settings(BaseSettings)` with `database_url, redis_url, kafka_bootstrap, s3_endpoint, s3_bucket, jwt_secret, jwt_alg, jwt_ttl_minutes, model_dir, app_env, run_migrations_on_start, run_seed_on_start, login_latency_budget_ms=300, payment_latency_budget_ms=500`.

**`gateway/app/main.py`** — app factory; CORS for `:5173`/`:5174`; startup hook (optionally) runs migrations + seed + resolves production models + submits the Flink job. `GET /health` returns `{"status":"ok","env":...}` (extended in Phase 1).

**`docker-compose.yml`** — services per Architecture §10: `postgres` (healthcheck), `redis`, `kafka` (KRaft single-node), `flink-jobmanager` + `flink-taskmanager`, `minio` (+ a one-shot `mc` init that creates the bucket), `gateway` (depends on all infra healthy, mounts `./models:/models`, `./flink-jobs:/jobs`), `web-app`, `bank-dashboard`.

**`gateway/app/db.py`** — SQLAlchemy 2.x engine + `SessionLocal` + `Base(DeclarativeBase)` + `get_db()`.
**`redis_client.py`** — shared `redis.Redis.from_url(..., decode_responses=True)`.
**`kafka_client.py`** — lazily-constructed `Producer` (confluent-kafka) + helper `produce(topic, key, value: dict)`; `consumer(group_id, topics)` factory.
**`s3_client.py`** — `boto3` client pointed at `S3_ENDPOINT`; helpers `put_object`, `get_object`, `list`.

**Acceptance check:**
```bash
docker compose up --build gateway
curl -s http://localhost:8000/health     # {"status":"ok","env":"dev"}
curl -s http://localhost:8000/docs       # Swagger UI loads
```
**Depends on:** none.

---

### Phase 1 — PostgreSQL OLTP Schema (Models, Alembic) + Infra Clients

**Goal:** All 16 OLTP tables from Architecture §4 / PRD §17.1 as SQLAlchemy 2.x models; an Alembic migration that builds them; health extended to ping pg + redis + kafka + s3.

**Files:**
```
gateway/app/models/__init__.py
gateway/app/models/user.py          # User, Account
gateway/app/models/device.py        # Device, UserDevice
gateway/app/models/session.py       # Session, LoginEvent
gateway/app/models/behavior.py      # BehaviorSample
gateway/app/models/beneficiary.py   # Beneficiary, UserBeneficiary
gateway/app/models/transaction.py   # Transaction
gateway/app/models/scoring.py       # RiskScore, Decision, AuthChallenge
gateway/app/models/governance.py    # Case, AuditLog, ModelRegistry
gateway/alembic.ini · alembic/env.py · alembic/versions/0001_initial.py
```

**Contents — models map 1:1 to PRD §17.1.** Use `Mapped[...]` / `mapped_column`, UUID PKs with `gen_random_uuid()` (enable `pgcrypto` in 0001: `op.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto')`). Highlights:
- `User`: + DPDP columns `consent_status` (`NONE|GRANTED|WITHDRAWN`), `consent_timestamp`, `consent_version`, `is_minor`; `account_status`, `kyc_level`, `baseline_risk_tier`. Contact fields tokenized.
- `Device`: `device_fingerprint` unique, `is_rooted`, `is_emulator`. `UserDevice`: `trust_score` (0..100), `binding_status`.
- `Session`: `ip_address INET`, `asn`, `is_vpn`, geo, `login_risk_score`, `status`. `LoginEvent`: `event_type` (attempt/success/failure/step_up), `behavior_anomaly_score`, `risk_score`, `decision`.
- `BehaviorSample`: `typing_speed`, `typing_rhythm JSONB`, `key_latency_avg`, `swipe_angle`, `touch_pressure`, `mouse_velocity`; **quarantine lifecycle** `quarantine_until`, `accepted`, **retention** `retention_expires_at`. Indexes on both lifecycle columns.
- `Beneficiary` + `UserBeneficiary` (`cooling_until`, `transfer_count`, `total_amount_sent`).
- `Transaction`: `transfer_type` (IMPS/NEFT/RTGS/UPI), `channel`, `is_new_payee`, `status`, `transaction_risk_score`, `decision`, **`decision_reason JSONB`**.
- `RiskScore`: `entity_type` (login/transaction), `entity_id`, `behavior_score`, `device_score`, `transaction_score`, `final_risk_score`, `risk_band`, **`model_version`**, **`latency_ms`**. Indexes `(user_id, scored_at desc)`, `risk_band`.
- `Decision`: `action` (allow/verify/block), `required_factors JSONB`, `reason_codes JSONB`.
- `AuthChallenge`: `challenge_type`, `status`, `attempts`.
- `Case`: `status` (open/investigating/confirmed_fraud/false_positive/closed), `assigned_to`. `AuditLog` (immutable). `ModelRegistry`: `model_name`, `stage`, `artifact_uri`, `metrics`.

**`alembic/env.py`:** import `Base` + all models; URL from `settings.database_url`.

**Extend `/health`:** `SELECT 1` (pg), `PING` (redis), Kafka metadata fetch, S3 `head_bucket`, model-registry status (`"empty"` until Phase 6). Return `503` if any down.

**Acceptance check:**
```bash
docker compose exec gateway alembic upgrade head
docker compose exec postgres psql -U cogniguard -d cogniguard -c "\dt"
#  users, accounts, devices, user_devices, sessions, login_events, behavior_samples,
#  beneficiaries, user_beneficiaries, transactions, risk_scores, decisions,
#  auth_challenges, cases, audit_logs, model_registry   (16 tables)
curl -s http://localhost:8000/health   # {"status":"ok","db":"ok","redis":"ok","kafka":"ok","s3":"ok",...}
```
**Depends on:** Phase 0.

---

### Phase 2 — Pydantic Schemas (Canonical Contracts)

**Goal:** Typed request/response + topic-payload contracts mirroring Architecture §5 / §4.2 exactly.

**Files:**
```
gateway/app/schemas/__init__.py
gateway/app/schemas/behavior.py     # BehaviorPayload + nested (web raw OR mobile derived)
gateway/app/schemas/features.py     # FeatureBundle + nested
gateway/app/schemas/scoring.py      # ScoreResult, ReasonCode, Amplifier
gateway/app/schemas/decision.py     # DecisionResponse, StepUp, TxnControls, Hardening
gateway/app/schemas/auth.py         # RegisterRequest, LoginRequest, StepUpVerifyRequest, ConsentRequest, NonceResponse
gateway/app/schemas/payment.py      # PaymentScoreRequest, PaymentScoreResponse
gateway/app/schemas/topics.py       # BehaviorEvent, DeviceEvent, LoginEvent, TransactionEvent, RiskScoreEvent, DecisionEvent
gateway/app/schemas/admin.py        # PolicyUpdate, EventOut, UserDetailOut, CaseUpdate
```

**`schemas/behavior.py`** — matches §5.1: `channel: Literal["web","mobile"]`, `source: Literal["web_sdk","mobile_edge"]`, `nonce`, `seq:int`, `ts`, `integrity_sig`, `device: DeviceInfo` (incl. `is_rooted`,`is_emulator`), `action: ActionBlock`, optional `keystroke`/`mouse`/`touch` (web) **or** `derived_features: dict` (mobile), `context: ContextBlock`. Key events use `"x"` placeholder for secret chars.
> **Canonicalization:** `canonical(metrics)` = deterministic JSON (sorted keys, no whitespace) of the `keystroke`/`mouse`/`touch`/`derived_features` blocks; SDK and gateway must produce the **same** form. Signed message = `nonce ‖ canonical(metrics) ‖ device.fingerprint ‖ ts`.

**`schemas/scoring.py`** — `ReasonCode{code:str, detail:str, sigma:float|None}`, `Amplifier{code:str, multiplier:float, detail:str}`, `ScoreResult{behavior_score, device_score, transaction_score, final_risk_score, risk_band: Literal["low","medium","high","very_high"], model_version, amplifiers:list[Amplifier], reason_codes:list[ReasonCode], degraded_mode:bool, latency_ms:int}`.

**`schemas/decision.py`** — `DecisionResponse{action: Literal["allow","verify","block"], entity_type: Literal["login","transaction"], risk_score, risk_band, required_factors:list[str], reason_codes:list[ReasonCode], amplifiers:list[Amplifier], action_sensitivity: Literal["low","medium","high"], step_up: StepUp|None, txn_controls: TxnControls|None, session_token:str|None, hardening: Hardening|None, integrity: Literal["OK","INTEGRITY_REJECT"]="OK", degraded_mode:bool=False, model_version:str}`. `StepUp{challenge_type: Literal["OTP","MPIN","FINGERPRINT","PASSKEY","VOICE_READBACK"], assurance: Literal["light","strong"], challenge_id}`. `TxnControls{cooling_until:str|None, manual_amount:bool, coercion_check:bool, reconfirm: Literal["APP_PUSH","EMAIL"]|None}`. `Hardening{action: Literal["DELAY","CAPTCHA","LOCKOUT"], scope: Literal["ip","device"], retry_after_s:int}`.

**`schemas/payment.py`** — `PaymentScoreRequest{amount, beneficiary_id|beneficiary_vpa, transfer_type, channel, action, behavior: BehaviorPayload}` (Bearer JWT in header). `PaymentScoreResponse` = `DecisionResponse` with `entity_type="transaction"` + `base_score`.

**`schemas/topics.py`** — exact §4.2 payloads for the 4 input + 2 output topics.

**`schemas/auth.py`** — `RegisterRequest{username,password}`, `LoginRequest{username,password,behavior,captcha_token?}`, `StepUpVerifyRequest{challenge_id,otp_or_assertion}`, `ConsentRequest{username,action:Literal["GRANT","WITHDRAW"],consent_version?}`, `NonceResponse{nonce,expires_at}`.

**Acceptance check:**
```bash
docker compose exec gateway python -c "
from app.schemas.behavior import BehaviorPayload
print(BehaviorPayload.model_validate_json(open('tests/fixtures/payload_genuine.json').read()).channel)"  # web
```
**Depends on:** Phase 1.

---

### Phase 3 — Kafka Topics + Event Production

**Goal:** Create the 6 topics; the gateway **produces** input events on every request (so the feature engine has a stream), and a thin output-topic emitter for `risk_scores`/`decisions`.

**Files:**
```
gateway/app/services/event_producer.py   # produce login/behavior/device/transaction events
gateway/scripts/create_topics.py          # idempotent topic creation (AdminClient)
gateway/tests/test_event_producer.py
```

**`create_topics.py`** — `confluent_kafka.admin.AdminClient` creates `behavior_events`, `device_events`, `login_events`, `transaction_events` (input, keyed by `user_id`/`device_id`), `risk_scores`, `decisions` (output), partitions=3, RF=1 (dev). Idempotent. Invoked on gateway startup.

**`event_producer.py`** — `emit_login_event(...)`, `emit_behavior_event(...)`, `emit_device_event(...)`, `emit_transaction_event(...)`, `emit_risk_score(...)`, `emit_decision(...)` → validate against `schemas/topics.py`, `kafka_client.produce(topic, key, value)`. **Fire-and-forget / non-blocking** (≤5 ms enqueue budget) — never block the hot path.

**Acceptance check:**
```bash
docker compose exec gateway python -m scripts.create_topics
docker compose exec kafka kafka-topics.sh --bootstrap-server kafka:9092 --list
# behavior_events device_events login_events transaction_events risk_scores decisions
docker compose exec gateway pytest tests/test_event_producer.py -q   # validates payloads against topic schemas
```
**Depends on:** Phases 1, 2.

---

### Phase 4 — Flink Feature Engine (Kafka → Redis + S3)

**Goal:** Stateful stream processing that turns input events into the online feature keys in Redis (Architecture §4.1) and mirrors raw events to S3. **Off the hot path.**

**Files:**
```
flink-jobs/feature_engine.py
flink-jobs/sinks.py        # Redis sink + S3 mirror sink
flink-jobs/windows.py      # windowed velocity/sum, geo-distance, z-score, baseline deviation
flink-jobs/tests/test_windows.py
```

**`feature_engine.py`** — PyFlink job: Kafka sources for the 4 input topics; keyed by `user_id`. Computes:
- `velocity_1h` / `velocity_24h` (sliding count windows) → `user:{id}:velocity:1h|24h` (TTL).
- `amount_sum_24h` (sliding sum) → `user:{id}:amount_sum:24h` (TTL).
- `avg_amount_30d` / `std_amount_30d` / `txn_count_30d` / `baseline_geohash` → `user:{id}:profile` HASH; `Amount_zscore` is derived at read time from these.
- `geo_distance` (haversine vs `baseline_geohash`) maintained in profile.
- known-sets: `user:{id}:known_devices|known_beneficiaries|known_geos` updated on first-seen.
- `device:{id}:trust` from device history; `behavior:{id}:baseline` serialized biometric profile (updated only from LOW-risk, no-step-up sessions — see Phase 9 quarantine).
- mirror every raw event to S3 (`s3://cogniguard/raw/{topic}/dt=.../...`).

**`windows.py`** holds the pure functions (unit-tested without Flink): `velocity_count`, `rolling_sum`, `zscore(amount, mean, std)`, `haversine`, `baseline_deviation`.

**Acceptance check:**
```bash
docker compose exec flink-jobmanager flink run -py /jobs/feature_engine.py   # job RUNNING in Flink UI :8081
# produce a few transaction_events, then:
docker compose exec redis redis-cli HGETALL user:<uuid>:profile   # avg_amount_30d, baseline_geohash, ...
docker compose exec redis redis-cli GET user:<uuid>:velocity:1h    # counter present, TTL set
docker compose exec gateway pytest -q flink-jobs/tests/test_windows.py  # zscore/haversine/rolling math
docker compose exec minio mc ls local/cogniguard/raw/transaction_events/   # raw mirror present
```
**Depends on:** Phases 1–3.

---

### Phase 5 — Feature Reader (Redis-only) + Dataset Loaders + Offline Training

**Goal:** Assemble the `FeatureBundle` for inference by reading **only Redis** + the inline payload; load the four datasets into S3; train the initial IF global prior + XGBoost.

**Files:**
```
gateway/app/services/feature_reader.py     # Redis-only read → FeatureBundle (NO Postgres on hot path)
gateway/app/utils/geo.py                    # haversine, geohash
gateway/scripts/load_datasets.py            # CMU/HMOG/INB_REQ_LOG/TXN_HISTORY_UPI_FIN → S3 partitions
training/datasets/{cmu,hmog,inb,txn}.py     # adapters → feature frames
training/train_isolation_forest.py          # global IF prior (typing+touch) from CMU/HMOG
training/train_xgboost.py                    # supervised from TXN_HISTORY_UPI_FIN (+ INB features)
gateway/tests/test_feature_reader.py
```

**`feature_reader.py`** — `read_bundle(user_id, payload, *, redis) -> FeatureBundle`: `HGETALL user:{id}:profile`; `GET` velocity/amount-sum counters; `SISMEMBER` for known device/beneficiary/geo; `GET device:{id}:trust`; derive `amount_zscore = (amount - avg_30d)/std_30d`, `geo_distance_km`, `is_new_device/payee`, `odd_time`, `high_velocity`; fold the inline behavioral metrics (web raw or mobile derived). **Never touches PostgreSQL.** Missing keys (cold-start) → defaults that bias to `verify`.

**`load_datasets.py`** — fetch/stage CMU, HMOG, `INB_REQ_LOG`, `TXN_HISTORY_UPI_FIN`; derive the documented features (PRD §6.6 tables — e.g. `beneficiary_add_to_pay_gap`, `nav_entropy`, `amount_zscore`); write parquet to `s3://cogniguard/training/...`. Bank datasets are the initial training-lake partition.

**`training/train_isolation_forest.py`** — fit `IsolationForest(n_estimators=128, contamination="auto", random_state=42)` on the CMU+HMOG behavioral vectors → **global prior**; persist to S3 + register `isolation_forest@<ver>` (stage `production`). Validate **G6 (EER ≤ 10%)** on the CMU benchmark.

**`training/train_xgboost.py`** — assemble labeled rows from `TXN_HISTORY_UPI_FIN` (label column or heuristic `is_new_payee ∧ amount_z>2 ∧ odd_time`) joined with INB-derived features **and the IF `Behavior_Score`** (stacking); fit `XGBClassifier`; calibrate; persist to S3 + register `xgboost_txn@<ver>` (stage `production`).

**Acceptance check:**
```bash
docker compose exec gateway python -m scripts.load_datasets        # parquet partitions in S3
docker compose exec gateway python -m training.train_isolation_forest   # IF prior in S3 + registry
docker compose exec gateway python -m training.train_xgboost            # XGB model in S3 + registry; EER/AUC printed
docker compose exec gateway pytest tests/test_feature_reader.py -q
# - read_bundle hits Redis only (assert no DB session used); cold-start defaults present;
#   amount_zscore derived from profile; known-device SET membership respected
```
**Depends on:** Phase 4 (Redis features), Phase 1 (registry table).

---

### Phase 6 — Scoring Service (Isolation Forest → XGBoost, Stacked)

**Goal:** Implement the **stacked single score** (PRD §9.1) — IF `Behavior_Score` fed into XGBoost → one fraud probability → 0–100. Plus the configurable weighted-ensemble alternative (§9.2), reason-code explainer (§7.5), registry, and graceful fallback. Returns a `ScoreResult`.

**Files:**
```
gateway/app/scoring/isolation_forest.py    # load + anomaly score → Behavior_Score [0,1]
gateway/app/scoring/xgboost_model.py        # load + fraud probability [0,1]
gateway/app/scoring/stack.py                # orchestrate IF → XGBoost; weighted-ensemble alt
gateway/app/scoring/amplifiers.py           # §10.3 Dynamic Risk Amplifiers (multiplicative)
gateway/app/scoring/explain.py              # deterministic reason-code explainer (NO SHAP/LIME)
gateway/app/scoring/registry.py             # resolve production model per name; cache; reload
gateway/tests/test_scoring.py · tests/test_amplifiers.py · tests/test_explain.py
```

**`registry.py`** — `Registry.get(model_name)` resolves the `production` row from `model_registry`, downloads the S3 artifact to `MODEL_DIR`, caches it, and exposes `version`. `reload(model_name)` clears cache (post-promotion). On load failure → caller triggers fallback.

**`isolation_forest.py`** — `behavior_score(vector) -> float`: `decision_function` (higher = more normal) flipped + squashed to `[0,1]`. Uses per-user `behavior:{id}:baseline` when present, else the global prior.

**`xgboost_model.py`** — `fraud_probability(features_incl_behavior_score) -> float` in `[0,1]`.

**`stack.py`:**
```python
def score(bundle, *, policy, registry, txn_context=None) -> ScoreResult:
    degraded = False
    try:
        bscore = isolation_forest.behavior_score(bundle.behavior_vector())   # Behavior_Score
    except Exception:
        bscore, degraded = 0.0, True
    feats = bundle.xgb_features(behavior_score=bscore)
    try:
        final_p = xgboost_model.fraud_probability(feats)                     # stacked single score
        model_version = registry.get("xgboost_txn").version
    except Exception:
        degraded = True
        final_p = fallback_rule_score(bundle, bscore)                       # IF + decision-layer rules (NFR-4)
        model_version = "fallback"
    base = round(100 * _clamp(final_p, 0, 1), 1)
    amps, score = [], base
    if txn_context is not None:                                             # transaction path
        amps = amplifiers.evaluate(txn_context, policy["amplifiers"])
        score = amplifiers.apply(base, amps)                               # clamp(base × Π, 0, 100)
    band = map_band(score, policy["thresholds"])
    reasons = explain.reason_codes(bundle, base_drivers=True) + [a.as_reason() for a in amps]
    return ScoreResult(behavior_score=bscore, transaction_score=final_p, final_risk_score=score,
                       risk_band=band, model_version=model_version, amplifiers=amps,
                       reason_codes=reasons, degraded_mode=degraded, ...)
```
> Weighted-ensemble alternative (`policy["scoring_mode"]=="weighted"`): `100*clamp(0.60*txn + 0.25*behavior + 0.15*device, 0, 1)`. **Never** run both at once.

**`amplifiers.py`** — `evaluate(txn_ctx, policy_amps)` fires `NEW_BENEF_HIGHVAL` (payee <2h ∧ amount >80% daily-avg → ×1.5), `RAPID_FANOUT` (≥N distinct new payees → ×1.4), `DRAIN` (≥90% balance to new VPA → ×1.3), `COERCION_TIME` (odd hour ∧ long pre-txn dwell → ×1.2). `apply(base, fired) = clamp(base × Πmultipliers, 0, 100)`. Multipliers come **only** from policy.

**`explain.py`** — deterministic top-deviation explainer (no SHAP/LIME): standardized deviation per feature vs baseline (`z = (x-mean)/max(std,ε)`), pick top drivers, map to plain-English `ReasonCode` via a fixed phrase dict; append device/geo pseudo-features and fired amplifiers/triggers. Must run inside the latency budget.

**Acceptance check:**
```bash
docker compose exec gateway pytest tests/test_scoring.py tests/test_amplifiers.py tests/test_explain.py -q
# - stacked: genuine bundle → low band; impostor (rhythm + new device + impossible travel) → high/very_high
# - Behavior_Score fed as XGBoost feature (assert presence in feature row)
# - XGBoost load error → degraded_mode True, fallback rule score returned (NFR-4)
# - amplifier: new-payee+high-value fires ×1.5; apply = clamp(base × Π, 0, 100); base 25 → 37.5
# - explain: top-2 drivers by |z|, plain-English, std→ε guard, no div-by-zero
```
**Depends on:** Phase 5.

---

### Phase 7 — Decision Engine, Adaptive Auth, Risk × Action, Transaction-Fraud Layer

**Goal:** Map `ScoreResult` (+ action stakes) → `allow`/`verify`/`block`, select the lightest assurance-ordered factor, resolve the risk×action matrix, and fire the transaction-fraud-layer controls. Policy-driven; cold-start biases to `verify`.

**Files:**
```
gateway/app/services/policy.py             # active policy load/cache; band/threshold/matrix/amplifier/stepup config
gateway/app/services/decision_engine.py    # band + risk×action → action
gateway/app/services/adaptive_auth.py      # assurance-ordered factor selection
gateway/app/services/txn_fraud_layer.py    # cooling / reconfirm / manual-amount / coercion check
gateway/tests/test_decision.py · tests/test_txn_fraud_layer.py
```

**`policy.py`** — `active_policy() -> dict` (DB-backed single active row, else defaults): `scoring_mode` (`stacked`|`weighted`), `weights`, `thresholds` `{low_max:30, medium_max:60, very_high_min:85}`, `action_sensitivity` (risk×action matrix), `amplifiers` `{NEW_BENEF_HIGHVAL:1.5, RAPID_FANOUT:1.4, DRAIN:1.3, COERCION_TIME:1.2}`, `stepup` (assurance ladder), `cooling_off`, `hardening` `{delay_after:3, captcha_after:4, lock_after:5, lock_minutes:15}`. **Never hardcode** these in logic.

**`decision_engine.py`:**
```python
def map_band(score, thresholds) -> str:
    if score <= thresholds["low_max"]:    return "low"      # 0–30
    if score <= thresholds["medium_max"]: return "medium"   # 30–60
    if score >= thresholds["very_high_min"]: return "very_high"  # ≥85
    return "high"                                            # 60–<85

def decide(band, action_type, *, policy, cold_start, degraded) -> Decision:
    sensitivity = policy["action_sensitivity"][action_type]["stakes"]      # low|medium|high
    cell = RISK_ACTION_MATRIX[band][sensitivity]                            # allow|verify(assurance)|block
    if band == "very_high" and not cold_start:
        return block_with_alert()
    if cold_start and cell.action == "block":
        cell = verify(assurance="strong")                                  # NEVER block cold-start
    return cell
```
Risk×Action matrix (PRD §10.2) is data in policy; the engine looks up `[band][sensitivity]`.

**`adaptive_auth.py`** — `select_factor(required_assurance, device_caps, policy.stepup) -> StepUp`: pick the **lightest factor that clears the risk** from the assurance ladder (knowledge < possession < phishing-resistant); degrade only to **equal-or-higher**; high-risk/high-stakes demand a strong, phishing-resistant factor (biometric/passkey/voice-readback), not SMS-OTP alone.

**`txn_fraud_layer.py`** — `resolve_controls(band, amps, txn_ctx, policy) -> TxnControls`: when txn risk crosses threshold or an amplifier fires → **Cooling Period** (set `cooloff:txn:{id}` + `cooling_until`), **Reconfirmation** (OOB "was this you?"), **Manual Amount Entry** (force retype), **Coercion Check** (plain-language confirm). Returns the `TxnControls` block for the `DecisionResponse`.

**Acceptance check:**
```bash
docker compose exec gateway pytest tests/test_decision.py tests/test_txn_fraud_layer.py -q
# - low→allow; medium→verify(light); high→verify(strong); very_high→block
# - risk×action: low risk + high-stakes (new-payee large) → verify + cooling-off
# - cold-start very_high → verify (NEVER block)
# - amplifier-driven medium on a genuine LOW behavioral score → coercion check + manual amount + cooling
# - assurance ladder picks lightest clearing factor; degrades only upward
```
**Depends on:** Phase 6.

---

### Phase 8 — Gateway Flows: Integrity, Login, Step-Up, Payment, JWT, Hardening, Consent, Audit

**Goal:** Wire the synchronous hot paths end-to-end. `/auth/login` (budget <300 ms) and `/payment/score` (budget <500 ms) return a real `DecisionResponse`; integrity verified **before** password; events produced; decisions persisted async + emitted to topics.

**Files:**
```
gateway/app/services/integrity.py     # nonce issue/verify, HMAC, seq/skew (anti-replay)
gateway/app/services/hardening.py      # Track A: IP/device counters + lockout (NEVER account)
gateway/app/services/consent.py        # consent grant/withdraw + RTBF trigger
gateway/app/services/audit.py          # immutable risk_scores + decisions + audit_logs
gateway/app/services/auth_flow.py      # register/login/step-up orchestration (Track A → Track B)
gateway/app/services/payment_flow.py   # §10.3 payment scoring orchestration
gateway/app/utils/security.py          # Argon2id, JWT encode/decode, jwt:denylist
gateway/app/utils/fingerprint.py
gateway/app/deps.py                    # get_current_user (+ denylist check), require_admin
gateway/app/routers/auth.py · payment.py · risk.py · admin.py
gateway/tests/test_integrity.py · test_auth_flow.py · test_payment_flow.py · test_hardening.py
```

**`integrity.py`** — `issue_nonce(user_id=None) -> (nonce, expires_at)` (Redis `nonce:{n}` TTL + audit copy); `verify(payload) -> (ok, reason)`: unknown/expired/consumed nonce → reject; `seq <= last_seq` → reject; HMAC mismatch (`key = sha256(jwt_secret+nonce)`, `msg = nonce ‖ canonical(metrics) ‖ fingerprint ‖ ts`) → reject; `|now - ts| > SKEW_S` → reject. **On success, consume the nonce (DEL)** and advance seq. Any failure → `INTEGRITY_REJECT` + `hardening.register_failure`.

**`security.py`** — Argon2id `hash_password`/`verify_password`; `issue_jwt(user_id) -> (token, jwt_id)`; `revoke(jwt_id)` sets `jwt:denylist:{jwt_id}` (TTL≈token life); `deps.get_current_user` decodes + checks denylist + session not terminated.

**`hardening.py`** — Track A counters `fail:ip:{ip}`, `fail:device:{fp}`, `bruteforce:asn:{asn}` (rolling TTL window); escalate DELAY (exp backoff) → CAPTCHA → **lock `lock:ip`/`lock:device`** (never `lock:user`); `distributed_alert(asn)`. Reset on success.

**`auth_flow.py`** — the §6.1 flow:
1. **Track A gate:** `lock:ip`/`lock:device` set? → `423` + LOCKOUT event for that IP/device (never the account).
2. **Integrity verify BEFORE password.** Fail → `INTEGRITY_REJECT` body (HTTP 400) + fail-counter bump + SOC.
3. `verify_password` (Argon2id). Fail → counters + hardening + `block` body.
4. Success → consume nonce; `event_producer.emit_login_event` + `emit_behavior_event`/`emit_device_event`; `feature_reader.read_bundle` (Redis-only); `stack.score(...)` (login path, `txn_context=None`); `decision_engine.decide`; `adaptive_auth` if `verify`.
5. Persist `risk_scores` + `decisions` (+ `model_version`, `latency_ms`) **async**; `emit_risk_score`/`emit_decision`; broadcast SOC.
6. `allow` → issue JWT + create `Session`; **only LOW + no-step-up** lets the sample update the baseline immediately. `verify` → create challenge (`stepup:{id}`, demo OTP `123456`). `block` → no token.

**`payment_flow.py`** — §10.3 (backs `/payment/score`, Bearer JWT):
1. Resolve active session (denylist check). 2. Integrity verify. 3. `emit_transaction_event`; build `txn_context` (amount, `benef_age_s`, `is_new_payee`, `daily_avg`, `balance_before`, `distinct_new_payees`, `odd_time`, `session_age_s`) from Redis + payload. 4. `stack.score(..., txn_context=...)` → `final = clamp(base × Π amplifiers)`. 5. `decision_engine.decide` (risk×action) + `txn_fraud_layer.resolve_controls`. 6. Persist `transactions` + `risk_scores` + `decisions`; emit topics; broadcast SOC. 7. Return `PaymentScoreResponse`.

**`consent.py`** — `is_capture_allowed(user)` (not minor ∧ `GRANTED`); `grant`/`withdraw` (withdraw enqueues the RTBF cascade, Phase 9).

**Routers** — `auth.py` (`/nonce` GET, `/register`, `/consent`, `/login`, `/step-up/verify`), `payment.py` (`POST /payment/score`), `risk.py` (`GET /risk/session/{id}` from Redis), `admin.py` (`/events`, `/users/{id}`, `/policy` GET/PUT, `/cases`, `/retrain`). Mount in `main.py` under `/api/v1`.

**Acceptance check:**
```bash
curl -s localhost:8000/api/v1/auth/nonce | jq .                       # {nonce, expires_at}
curl -sX POST localhost:8000/api/v1/auth/register -d '{"username":"genuine","password":"Passw0rd!"}'
curl -sX POST localhost:8000/api/v1/auth/consent  -d '{"username":"genuine","action":"GRANT","consent_version":"v1"}'
curl -sX POST localhost:8000/api/v1/auth/login    -d @tests/fixtures/login_genuine.json  | jq '.action,.risk_band'   # allow / low
curl -sX POST localhost:8000/api/v1/auth/login    -d @tests/fixtures/login_impostor.json | jq '.action,.reason_codes' # verify|block
curl -sX POST localhost:8000/api/v1/auth/login    -d @tests/fixtures/replay_login.json   | jq '.integrity'           # INTEGRITY_REJECT (400)
curl -sX POST localhost:8000/api/v1/payment/score -H "Authorization: Bearer $JWT" -d @tests/fixtures/txn_app_fraud.json | jq '.action,.amplifiers,.txn_controls'
docker compose exec gateway pytest tests/test_integrity.py tests/test_auth_flow.py tests/test_payment_flow.py tests/test_hardening.py -q
```
**Depends on:** Phases 2–7.

---

### Phase 9 — Continuous Re-scoring, SOC Broadcaster (WS), Case Mgmt, RTBF & Quarantine Jobs

**Goal:** `/behavior/ingest` re-scores active sessions; `very_high` terminates + revokes the JWT (denylist) + alerts. SOC broadcaster streams `risk_scores`/`decisions` over WebSocket. Analyst case actions + label feedback. RTBF + quarantine jobs.

**Files:**
```
gateway/app/services/broadcaster.py     # Kafka(risk_scores/decisions) → Redis pubsub → WS
gateway/app/services/case_mgmt.py        # cases lifecycle + analyst actions + label feedback → S3
gateway/app/routers/behavior.py · ws.py
gateway/app/jobs/rtbf.py                 # right-to-be-forgotten cascading hard-delete (≤24h)
gateway/app/jobs/quarantine.py           # step-up telemetry promotion after clean window
gateway/tests/test_continuous.py · test_quarantine.py · test_rtbf.py · test_case_mgmt.py
```

**`routers/behavior.py`** — `POST /behavior/ingest` (Bearer): load session (reject TERMINATED); integrity verify (nonce reuse → 409); `emit_behavior_event`; `read_bundle` → `stack.score` (entity `transaction`/continuous); update `session:risk:{id}`; if band `very_high` → `Session.status="TERMINATED"`, `security.revoke(jwt_id)` (denylist), emit `decisions` + SOC alert, respond `{action:"verify","reauth":true}`; else `{action:"allow"}`. Behavior re-converging to baseline → de-escalate.

**`broadcaster.py`** — a consumer bridges the `risk_scores`/`decisions` Kafka topics to Redis pub/sub `soc-feed`; `ws.py` `WS /ws/soc-feed` streams them to the dashboard.

**`case_mgmt.py`** — open a `case` on `block`/`very_high`; analyst actions (assign, note, status); setting `confirmed_fraud`/`false_positive` writes a labeled row to `s3://cogniguard/labels/...` for the weekly XGBoost retrain (Phase 12). All audited.

**`jobs/quarantine.py`** — `run_promotion(db)`: step-up-passed telemetry was written `accepted=False, quarantine_until=now()+7d`; promote to `accepted=True` only after a **clean window** (no `confirmed_fraud`/chargeback/anomalous device-geo/subsequent high-risk event), else discard. Only LOW + no-step-up sessions update the baseline immediately (the Flink job consumes `accepted=True` samples).

**`jobs/rtbf.py`** — `run_rtbf(db)`: for `consent_status=WITHDRAWN`, hard-delete `behavior_samples` (raw vectors) + per-user model artifact; **retain** `risk_scores`/`decisions`/`audit_logs` stripped to score/band/decision. Also enforce `retention_expires_at` purges.

**Acceptance check:**
```bash
wscat -c ws://localhost:8000/ws/soc-feed        # Terminal A
# Terminal B: a login → event appears in A within ~100 ms
curl -sX POST localhost:8000/api/v1/behavior/ingest -H "Authorization: Bearer $JWT" -d @tests/fixtures/ingest_hijack.json | jq '.action,.reauth'  # verify, true; session TERMINATED, JWT denylisted
docker compose exec gateway python -m app.jobs.quarantine    # clean window promotes; HIGH event in window discards
docker compose exec gateway python -m app.jobs.rtbf          # withdrawn user: samples+model purged, audit retained
docker compose exec gateway pytest tests/test_continuous.py tests/test_quarantine.py tests/test_rtbf.py tests/test_case_mgmt.py -q
```
**Depends on:** Phases 3, 8.

---

### Phase 10 — behavior-sdk (TypeScript)

**Goal:** Shared capture library: keystroke/mouse/touch capture, device fingerprint, mobile edge feature extraction, nonce fetch + HMAC signing, `BehaviorPayload` builder, continuous mode. API per Architecture §3.1.

**Files:**
```
behavior-sdk/package.json · tsconfig.json
behavior-sdk/src/index.ts        # CogniGuard.init/attach/collect/startContinuous
behavior-sdk/src/events.ts       # keystroke/mouse/touch buffers (mask secret chars)
behavior-sdk/src/fingerprint.ts  # UA/screen/tz/lang/canvas hash + is_rooted/is_emulator
behavior-sdk/src/edge.ts         # mobile edge feature extraction → derived_features
behavior-sdk/src/payload.ts      # nonce fetch + canonical(metrics) + HMAC-SHA256 + monotonic seq
behavior-sdk/src/types.ts        # mirror schemas/behavior.py
behavior-sdk/src/*.test.ts
```

**`events.ts`** — `KeystrokeCapture` records `{key,down,up}` with `performance.now()`; password fields emit `"x"` (never the real char), Backspace tracked. `MouseCapture`/`TouchCapture` analogous.
**`fingerprint.ts`** — SHA-256 of UA + `${w}x${h}` + timezone + language + canvas/WebGL hash → `fingerprint`.
**`payload.ts`** — `fetchNonce(apiBase)`; `canonical(metrics)` = recursively sorted-key JSON (MUST match backend `_canonical`); `signPayload(p, nonce, secret)` sets `ts`, `seq=++_seq`, `integrity_sig = HMAC-SHA256(sha256(secret+nonce), nonce ‖ canonical(metrics) ‖ fingerprint ‖ ts)` via Web Crypto.
**`index.ts`** — `CogniGuard.init(config)`, `attach(formEl)`, `collect(): Promise<BehaviorPayload>` (drain buffers → fingerprint + context → fetch nonce → sign), `startContinuous(token)` (every N=10 s: fresh nonce, collect, POST `/behavior/ingest`).

**Acceptance check:**
```bash
cd behavior-sdk && npm install && npm run build && npm test
# KeystrokeCapture dwell/flight ordering; password field never emits real chars;
# collect() returns a valid signed BehaviorPayload with nonce/seq/integrity_sig
```
**Depends on:** Phase 2 (payload parity). Can proceed in parallel once schemas are frozen.

---

### Phase 11 — web-app (Banking Demo) + bank-dashboard (Fraud-Ops / SOC)

**Goal:** The two React apps that drive the demo. web-app integrates the SDK (login → dashboard → transfer with adaptive step-up + transaction-fraud layer). bank-dashboard shows the live SOC feed, charts, per-user drilldown, reason-code panel, case management, and the policy editor.

**Files (web-app):**
```
web-app/package.json · vite.config.ts · tailwind.config.js · Dockerfile · src/main.tsx · src/api.ts
src/pages/Login.tsx · StepUp.tsx · Dashboard.tsx · Transfer.tsx · Payment.tsx
src/components/ChannelSwitcher.tsx · ConsentToggle.tsx · RiskBadge.tsx
src/components/CoercionCheck.tsx · ManualAmountEntry.tsx · CoolingNotice.tsx   # txn-fraud layer
```
**Files (bank-dashboard):**
```
bank-dashboard/package.json · vite.config.ts · tailwind.config.js · Dockerfile · src/main.tsx · src/api.ts · src/ws.ts
src/pages/Live.tsx · UserDetail.tsx · Policy.tsx · Cases.tsx · Governance.tsx
src/components/EventTable.tsx · BandDistribution.tsx (Recharts) · ReasonCodePanel.tsx
src/components/AmplifierBadges.tsx · IntegrityFlag.tsx · QuarantineStatus.tsx
src/components/LatencyHistogram.tsx · DriftPanel.tsx · CaseDrawer.tsx · AlertPanel.tsx
```

**Key wiring:**
- web-app `Login.tsx`: `CogniGuard.init/attach`; submit → `await collect()` (signed) → `POST /auth/login`. `verify` → `StepUp.tsx` (factor from `required_factors`); `block` → denial; `allow` → store JWT → `Dashboard`. `ChannelSwitcher` sets `channel` (web/mobile) and suppresses mouse / uses `derived_features`.
- web-app `ConsentToggle.tsx`: grant/withdraw → `POST /auth/consent`; withdraw shows the RTBF notice.
- web-app `Payment.tsx`: amount + beneficiary → `await collect()` + `POST /payment/score`; on `verify` with `txn_controls`, render `CoercionCheck` ("sending ₹X to a payee added 40 min ago — is someone instructing you?"), `ManualAmountEntry`, and `CoolingNotice`.
- web-app `Transfer.tsx`: `CogniGuard.startContinuous(jwt)`; `{action:"verify",reauth:true}` → force logout (hijack demo).
- bank-dashboard `ws.ts`: subscribe `/ws/soc-feed` → store → `EventTable` + `BandDistribution` + `AlertPanel`. `ReasonCodePanel` renders top deviation drivers; `AmplifierBadges` fired amplifiers; `IntegrityFlag` `INTEGRITY_REJECT`; `QuarantineStatus` on `UserDetail`; `Cases.tsx` analyst actions + `confirmed_fraud`/`false_positive` labels; `Governance.tsx` production-vs-challenger + `LatencyHistogram` (p95 vs 300/500 ms) + `DriftPanel`; `Policy.tsx` `PUT /admin/policy` live-updates weights/thresholds/amplifiers.

**Acceptance check:**
```bash
docker compose up --build
# http://localhost:5173 → login as genuine → seamless dashboard
# http://localhost:5174 → live event with score, band, reason codes, latency
cd web-app && npm test ; cd ../bank-dashboard && npm test
```
**Depends on:** Phases 8–10.

---

### Phase 12 — Model Governance (Registry, Champion/Challenger, Drift, Feedback Loop)

**Goal:** Operationalize §14 — challengers score in shadow, drift monitors fire retrains, analyst labels feed weekly XGBoost retrains, promotions are auditable + rollback-able.

**Files:**
```
training/promote.py        # staging → production with audit; rollback to prior version
training/drift_monitor.py  # PSI/KS feature drift + score/outcome drift → alert + on-demand retrain
gateway/app/scoring/shadow.py   # challenger scores alongside champion (no action), logs metrics
gateway/app/routers/admin.py    # /admin/models (list/promote/rollback), /admin/drift
training/tests/test_drift.py · gateway/tests/test_shadow.py
```

**`shadow.py`** — when a challenger model is registered (`stage="staging"`), the scoring path **also** runs it without acting, recording its score/decision to `risk_scores` (flagged) for offline comparison on fraud-value-caught at the bounded FP/step-up budget.
**`promote.py`** — promote a challenger to `production` only when it beats the incumbent; archive the previous; write an `audit_logs` row. `rollback(model_name, version)` flips stages without redeploy.
**`drift_monitor.py`** — PSI/KS on input distributions (online features vs training), score drift, outcome drift (precision/recall on confirmed labels); breach → alert + enqueue on-demand retrain.
**Feedback loop** — weekly `train_xgboost` consumes `s3://cogniguard/labels/...`; IF baselines update incrementally from LOW-risk, no-step-up sessions; quarantine gates step-up telemetry.

**Acceptance check:**
```bash
docker compose exec gateway python -m training.train_xgboost --stage staging         # register challenger
# drive traffic → shadow scores recorded alongside champion
docker compose exec gateway pytest gateway/tests/test_shadow.py training/tests/test_drift.py -q
docker compose exec gateway python -m training.promote --model xgboost_txn --to production   # audited promotion
docker compose exec gateway python -m training.drift_monitor   # PSI/KS report; alert on breach
```
**Depends on:** Phases 5, 6, 9.

---

## 4. API Implementation Reference

All paths prefixed `/api/v1` except the WebSocket. Mirrors PRD §11/§17 and Architecture §5/§6.

| Method | Path | Request | Response | Status | Auth |
|--------|------|---------|----------|--------|------|
| GET | `/auth/nonce` | — | `NonceResponse` | 200 | none |
| POST | `/auth/register` | `RegisterRequest` | `{user_id,status}` | 201, 409 | none |
| POST | `/auth/consent` | `ConsentRequest` | `{consent_status,consent_timestamp}` | 200, 404 | none (demo) |
| POST | `/auth/login` | `LoginRequest` | `DecisionResponse` | 200, 400 (INTEGRITY_REJECT), 401 (block body), 423 (locked) | none |
| POST | `/auth/step-up/verify` | `StepUpVerifyRequest` | `DecisionResponse` (allow+token; sample→quarantine) | 200, 400, 401 | none |
| POST | `/payment/score` | `PaymentScoreRequest` (+ Bearer) | `PaymentScoreResponse` | 200, 400, 401 | JWT |
| POST | `/behavior/ingest` | `BehaviorPayload` (+ Bearer) | `{action, reauth?, risk_score, risk_band}` | 200, 400, 401, 409 (nonce reuse) | JWT |
| GET | `/risk/session/{id}` | — | `{session_id,risk,band,status}` | 200, 404 | JWT |
| GET | `/admin/events?band=&user_id=&entity_type=&limit=` | query | `EventOut[]` | 200 | admin |
| GET | `/admin/users/{id}` | — | `UserDetailOut` | 200, 404 | admin |
| GET/PUT | `/admin/policy` | `PolicyUpdate` | `{active_policy}` | 200, 422 | admin |
| GET/POST | `/admin/cases` · `/admin/cases/{id}` | `CaseUpdate` | `Case[]` / `Case` | 200 | admin |
| GET/POST | `/admin/models` · `/admin/models/{name}/promote` | — | `ModelRegistry[]` | 200 | admin |
| POST | `/admin/retrain` | `{model?}` | `{queued}` | 202 | admin |
| WS | `/ws/soc-feed` | — | stream of risk_scores/decisions JSON | 101 | admin (demo: open) |
| GET | `/health` | — | `{status,db,redis,kafka,s3,model_registry}` | 200, 503 | none |

**Conventions:** locked IP/device → `423` with `hardening` body (never an account lock); bad credentials → `200` with `action:"block"` + `hardening` (don't leak credential validity via codes); telemetry replay/tamper → `400` with `integrity:"INTEGRITY_REJECT"` (+ fail-counter); nonce reuse on `/behavior/ingest` → `409`; enroll/capture without consent → `403`.

---

## 5. Seeding & Demo Data

**Goal:** `generate_fraud_scenarios.py` + `seed_demo.py` create reproducible personas + a default active policy + registered production models so the PRD scenarios work every run. Seeded RNG = deterministic. **Genuine = real/seeded baselines; fraud = synthetic scenarios only.**

### 5.1 Personas (seed = 1337)
| Persona | username | typing profile | device/geo | role |
|---------|----------|----------------|------------|------|
| **Genuine** | `genuine` | steady dwell/flight | known device, Mumbai (19.07, 72.87), balance ₹100k, daily-avg ₹2k | enrolled, low-risk baseline |
| **Impostor** | (attacks `genuine`) | erratic/slow | new device, Tallinn (59.43, 24.75), recent Mumbai prior | rhythm + impossible travel |

`seed_demo.py`: upsert default active `policy` (`scoring_mode="stacked"`, thresholds `low_max:30/medium_max:60/very_high_min:85`, amplifiers, risk×action matrix, stepup ladder, hardening, cooling_off); register `production` `isolation_forest` + `xgboost_txn` from S3; create `genuine` (Argon2id `Passw0rd!`), grant consent, seed Redis profile/known-sets + 30-day baselines, register known device, add a **new beneficiary `scammer@upi` ~40 min ago**; write demo fixtures.

### 5.2 Generated fixtures (curl/pytest/UI)
```
tests/fixtures/login_genuine.json     # genuine rhythm, known device, Mumbai; SIGNED
tests/fixtures/login_impostor.json    # impostor rhythm, new device, Tallinn, recent prior
tests/fixtures/ingest_hijack.json     # mid-session behavior swap (continuous → very_high)
tests/fixtures/txn_app_fraud.json     # genuine behavior, ₹50000 to scammer@upi added 40m ago → ×1.5
tests/fixtures/replay_login.json      # a captured signed payload to replay (consumed nonce)
```

---

## 6. Testing Strategy

### 6.1 Backend (pytest + httpx)
| Test file | Type | Key cases |
|-----------|------|-----------|
| `flink-jobs/tests/test_windows.py` | unit | velocity/rolling-sum, zscore, haversine, baseline deviation |
| `test_feature_reader.py` | unit | Redis-only read (no DB session); cold-start defaults; amount_zscore derivation; known-set membership |
| `test_scoring.py` | unit | stacked genuine→low / impostor→high; Behavior_Score fed to XGBoost; XGB error→`degraded_mode` + fallback (NFR-4) |
| `test_amplifiers.py` | unit | new-payee(<2h)+amount>80% fires ×1.5; `apply = clamp(base×Π,0,100)`; benign→none |
| `test_explain.py` | unit | top drivers by \|z\|; phrase map; `std→ε` guard; no SHAP/LIME; within budget |
| `test_decision.py` | unit | band map; risk×action matrix cells; cold-start very_high→verify (never block); assurance ladder |
| `test_txn_fraud_layer.py` | unit | cooling/reconfirm/manual/coercion fired by triggers/amplifiers |
| `test_integrity.py` | unit | valid→OK + nonce consumed; replay/unknown/expired→reject; tamper→HMAC mismatch; seq non-increasing→reject; skew→reject |
| `test_hardening.py` | unit | fail#3→DELAY; #4→CAPTCHA; #5→lock `lock:ip`/`lock:device` (NEVER account); distributed ASN alert |
| `test_quarantine.py` | unit | step-up sample `accepted=False`/`+7d`; clean window→promote; HIGH event in window→discard |
| `test_rtbf.py` | unit | WITHDRAWN→purge behavior_samples+model; risk_scores/decisions retained |
| `test_auth_flow.py` | integration | register→consent→genuine login `allow`+JWT+reason_codes; impostor `verify`/`block`; replay→INTEGRITY_REJECT |
| `test_payment_flow.py` | integration | genuine behavior + new-payee high-value → ×1.5 → `verify` + txn_controls (coercion case) |
| `test_continuous.py` | integration | ingest hijack → reauth + session TERMINATED + JWT denylisted |
| `test_shadow.py` / `test_drift.py` | unit | challenger scores in shadow (no action); PSI/KS breach → alert |
| `test_latency.py` | perf | login p95 < 300 ms; payment p95 < 500 ms (server-side, incl. reason codes) |

Run: `docker compose exec gateway pytest -q`.

### 6.2 Frontend (Vitest)
- `behavior-sdk`: `KeystrokeCapture` dwell/flight; password field never emits real chars; `collect()` returns a valid signed payload.
- `web-app`: `Login` renders; channel switch toggles modalities; `verify` routes to `StepUp`; `Payment` renders coercion-check/manual-amount on `txn_controls`.
- `bank-dashboard`: `EventTable` renders WS events; `ReasonCodePanel`/`AmplifierBadges`/`BandDistribution`/`LatencyHistogram` render.

---

## 7. Running the Full Demo

```bash
docker compose up --build
```
| Service | URL |
|---------|-----|
| Gateway API + Swagger | http://localhost:8000/docs |
| Web banking demo | http://localhost:5173 |
| Bank / SOC dashboard | http://localhost:5174 |
| Flink UI | http://localhost:8081 |
| MinIO console | http://localhost:9001 |

On startup the gateway runs migrations + `seed_demo.py`, registers production models, and submits the Flink feature job. Open the dashboard to watch the live feed.

### 7.1 Scenario script (maps to PRD §3.1 / §10 / §16)
1. **Genuine happy path.** Log in as `genuine`/`Passw0rd!` typing steadily → `low` → `allow`, instant dashboard. Feed shows a low/allow event.
2. **ATO at login.** Replay `login_impostor.json` (new device, Tallinn, recent Mumbai prior) → `high`/`very_high` → `verify`(strong)/`block` + alert. `ReasonCodePanel`: impossible-travel + keystroke mismatch.
3. **Coercion at payment (the signature case).** Genuine login, then `POST /payment/score` with `txn_app_fraud.json` (₹50000 to `scammer@upi` added 40 min ago) → `NEW_BENEF_HIGHVAL ×1.5` → `verify` + **cooling + manual amount + coercion check**. `AmplifierBadges` show the fired ×1.5.
4. **Mid-session hijack.** Login genuinely, go to Transfer (continuous), POST `ingest_hijack.json` → continuous score `very_high` → session TERMINATED, JWT denylisted, `{action:"verify",reauth:true}`, HIGH alert on feed.
5. **Brute force (IP/device, never account).** 5 wrong passwords → DELAY(3) → CAPTCHA(4) → lock `lock:ip`/`lock:device` (423). A clean device/IP still authenticates the genuine user.
6. **Replay defeated.** `curl ... -d @replay_login.json` (consumed nonce) → `400` + `integrity:"INTEGRITY_REJECT"`; `IntegrityFlag` on the feed; fail-counter bumps.
7. **Admin tuning.** Lower `medium_max` in `Policy.tsx` → `PUT /admin/policy`; re-run a borderline login → resolves to a higher band live (no restart).
8. **Quarantine anti-poisoning.** Drive an impostor login to `verify`, pass demo OTP `123456` → telemetry lands `accepted=false, quarantine_until=+7d`; `QuarantineStatus` shows the profile unchanged; `python -m app.jobs.quarantine` after injecting a HIGH event → discarded.
9. **Right-to-be-forgotten.** Withdraw consent → `python -m app.jobs.rtbf` → `behavior_samples` + model purged; `risk_scores`/`decisions`/audit retained.
10. **Reason codes.** Any `verify`/`block` carries `reason_codes` (top deviation drivers + amplifiers), rendered by `ReasonCodePanel` and stored in `decisions`.
11. **Analyst case + feedback.** Open the case on a blocked event, label `confirmed_fraud` → label row to S3; the weekly retrain consumes it.
12. **Governance.** `Governance.tsx` shows a challenger scoring in shadow, `LatencyHistogram` (p95 vs 300/500 ms), and the `DriftPanel`.

---

## 8. Definition of Done Checklist

### Goals (PRD §2.1) & latency
- [ ] **G1** ≥80% fraud value caught at the chosen threshold. *(Phases 6,12)*
- [ ] **G2** ≤1% genuine high-value events blocked. *(Phases 7,12)*
- [ ] **G3** ≤5% genuine logins see added friction. *(Phases 7,12)*
- [ ] **G4** Login decision **p95 < 300 ms**. *(`test_latency.py`)*
- [ ] **G5** Payment decision **p95 < 500 ms**. *(`test_latency.py`)*
- [ ] **G6** Behavioral anomaly EER ≤ 10% on CMU/HMOG. *(Phase 5 training)*
- [ ] **G7** 100% of `verify`/`block` carry reason codes. *(Phases 6,7)*
- [ ] **G8** ≥2,000 scoring events/sec/region (partitioned Kafka, sharded Redis). *(Phases 3,4)*

### Streaming & data architecture
- [ ] Pipeline runs `Gateway → Kafka → Flink → Redis → Models → Decision → Dashboard`. *(Phases 3,4,8,11)*
- [ ] **Inference reads Redis only**; PostgreSQL never on the hot path; Redis rebuildable from PG + Kafka/S3. *(Phases 4,5)*
- [ ] 16 OLTP tables via Alembic; 6 Kafka topics; Redis feature keys; S3 lake. *(Phases 1,3,4)*
- [ ] **No graph database / mule-network model anywhere.** *(scope guardrail)*

### Models & decisions
- [ ] Stacked IF→XGBoost single score (weighted alt configurable, never both). *(Phase 6)*
- [ ] Bands low/medium/high/very_high; decisions allow/verify/block; from active policy. *(Phases 6,7)*
- [ ] Dynamic Risk Amplifiers `final = clamp(base × Π, 0, 100)`; transaction-fraud layer (cooling/reconfirm/manual/coercion). *(Phases 6,7)*
- [ ] Risk×action matrix; assurance-ordered adaptive auth; cold-start → verify never block. *(Phase 7)*
- [ ] Continuous re-scoring → very_high terminates session + JWT denylist. *(Phase 9)*
- [ ] Reason-code explainer deterministic (no SHAP/LIME), within budget. *(Phase 6)*

### Security, privacy, governance
- [ ] Telemetry integrity: single-use nonce + HMAC + seq + skew; verify before password; replay→INTEGRITY_REJECT. *(Phases 8,10)*
- [ ] Two-track lockout: IP/device only, never the account. *(Phase 8)*
- [ ] Mobile edge extraction: only derived features transmitted. *(Phase 10)*
- [ ] Quarantine anti-poisoning; consent gating + ≤24h RTBF; residency; immutable audit. *(Phases 9)*
- [ ] Model registry + champion/challenger shadow + drift monitors + label feedback loop. *(Phase 12)*
- [ ] Graceful degradation: XGB down→IF+rules; Redis degraded→verify; timeout→safe action; `degraded_mode`. *(Phases 6,8)*

### Engineering / NFR gates
- [ ] `docker compose up --build` brings up all services; `/health` green (pg/redis/kafka/flink/s3/registry).
- [ ] No raw secret keystroke content / no raw mobile sensor series transmitted.
- [ ] JWT + Argon2id + Pydantic validation + parameterized SQLAlchemy; PII tokenized; secrets via env/vault.
- [ ] All pytest + Vitest suites green; `ruff`/`black`/`eslint`/`prettier` clean.

---

## Appendix A — Build Order Dependency Graph
```
P0 ─▶ P1 ─▶ P2 ─▶ P3 ─▶ P4 ─▶ P5 ─▶ P6 ─▶ P7 ─▶ P8 ─▶ P9 ─▶ P11 ─▶ P12
                  └────────────────────────────────────▶ P10 ─────────┘
```
P10 (behavior-sdk) needs only P2's payload shape and can proceed in parallel once schemas are frozen. P12 (governance) builds on P5/P6/P9.

## Appendix B — Consistency Anchors (do not drift)
- **Repo root** `cogniguard/`, tree exactly per Architecture §9.
- **Pipeline:** `Gateway → Kafka → Flink → Redis Feature Store → Risk Models → Decision Engine → Dashboard`; inference reads **Redis only**.
- **Models:** XGBoost primary (stacked on IF `Behavior_Score`) → one fraud probability; weighted alt 60/25/15; LSTM Phase 2.
- **Bands** `low` 0–30 / `medium` 30–60 / `high` 60–100 / `very_high` ≥85; **decisions** `allow`/`verify`/`block`; from active policy.
- **Amplifiers** `NEW_BENEF_HIGHVAL ×1.5, RAPID_FANOUT ×1.4, DRAIN ×1.3, COERCION_TIME ×1.2`; `final = clamp(base × Π, 0, 100)`.
- **Integrity-sig:** `HMAC-SHA256(nonce ‖ canonical(metrics) ‖ device_fingerprint ‖ ts)`; single-use nonce (Redis `nonce:{n}` TTL, DEL on consume); monotonic `seq`; reject → `INTEGRITY_REJECT`.
- **Latency:** login p95 < 300 ms, payment p95 < 500 ms.
- **Schemas** `BehaviorPayload` / `FeatureBundle` / `ScoreResult` / `DecisionResponse` exactly per Architecture §5.
- **16 tables** (Architecture §4) · **6 Kafka topics** (§4.2) · **Redis feature keys** (§4.1).
- **Ports** postgres 5432, redis 6379, kafka 9092, flink 8081, minio 9000/9001, gateway 8000, web-app 5173, bank-dashboard 5174.
- **Datasets** INB_REQ_LOG, TXN_HISTORY_UPI_FIN, CMU, HMOG; synthetic generator for **fraud scenarios only**.
- **No graph database, no graph-based mule-network detection — any phase.**
