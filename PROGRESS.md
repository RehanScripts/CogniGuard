# CogniGuard — Build Progress & Team Guide

Living tracker + onboarding for the team. **Read this first**, then the four source docs.
Keep this file up to date: when you finish a phase, tick it here in the same PR.

> **Last verified:** Phase 5 complete on `main`. Stack runs end-to-end:
> `docker compose up` → infra + gateway healthy → Flink feature job populates Redis + S3
> → `load_datasets` stages CMU/HMOG/INB/TXN parquet → IF + XGBoost train and register.

---

## 1. How we stay on the same page

1. **Source of truth (do not re-derive, do not casually edit):**
   - [`PRD.md`](PRD.md) — *what & why* (authoritative).
   - [`System Architecture.md`](System%20Architecture.md) — *how it fits together* (schema, topics, contracts, flows).
   - [`Implementation.md`](Implementation.md) — *the build plan*: phases 0–12, file-by-file, each with an **acceptance check**.
   - [`CLAUDE.md`](CLAUDE.md) — coding conventions + architecture invariants (the rules).
2. **This file (`PROGRESS.md`)** is the living tracker — phase status, owner, branch, gotchas.
3. **One phase = one branch = one PR**, gated by that phase's acceptance check. Phases are mostly sequential (see §5 dependency graph).
4. **Same environment everywhere:** everything runs in Docker Compose. No "works on my machine" — if it doesn't pass the acceptance check in a clean `docker compose up`, it's not done.
5. When in doubt about a name/schema/endpoint, copy it **verbatim** from the source docs. Don't invent alternatives.

---

## 2. First-time setup on a new laptop

Prereqs: **Docker + Docker Compose**, Git. (Python/Node only needed if you run things outside containers.)

```bash
git clone https://github.com/xemorph64/Cogni_Guard.git
cd Cogni_Guard
cp .env.example .env          # .env is gitignored — never commit it

# Build images (gateway + custom Flink image are the slow ones, ~3–5 min first time)
docker compose build

# Bring up infra + gateway (UI services are behind the 'ui' profile, Phase 11)
docker compose up -d
curl -s http://localhost:8000/health | jq .     # expect status ok; db/redis/kafka/s3 ok

# Apply DB schema (also auto-runs on gateway startup)
docker compose exec gateway alembic upgrade head

# Submit the Flink feature-engine job (Phase 4+)
docker compose exec flink-jobmanager flink run -d -py /jobs/feature_engine.py
```

| Service | URL |
|---------|-----|
| Gateway API + Swagger | http://localhost:8000/docs |
| Flink UI | http://localhost:8081 |
| MinIO console | http://localhost:9001 (minioadmin / minioadmin) |
| Web app / Bank dashboard | http://localhost:5173 / :5174 (Phase 11, `--profile ui`) |

**Datasets** are committed under `SAMPLE_DATA/` (CMU `DSL-StrongPasswordData.csv`, HMOG raw session + `hmog_features.csv`, `INB_REQ_LOG.csv`, `TXN_HISTORY_UPI_FIN.csv`, `eda_report.md`).

---

## 3. Running tests

```bash
# Gateway (FastAPI) tests
docker compose exec gateway python -m pytest -q

# Flink feature-engine pure-logic tests (windows + sinks)
docker compose exec -e PYTHONPATH=/flink-jobs gateway python -m pytest /flink-jobs/tests -q
```
Every phase must keep **all** suites green. New logic ships with tests.

---

## 4. Git workflow (everyone follows this)

```bash
git switch main && git pull
git switch -c phase-<N>-<shortname>     # e.g. phase-5-feature-reader
# ...build the phase, keep tests green...
docker compose exec gateway python -m pytest -q          # run the acceptance check
git add -A && git commit -m "Phase <N>: <summary>"
git push -u origin phase-<N>-<shortname>
# open a PR on GitHub, or fast-forward merge once the acceptance check passes:
git switch main && git merge --ff-only phase-<N>-<shortname> && git push origin main
```

Conventions:
- **Branch name:** `phase-<N>-<shortname>`.
- **Commit body** ends with: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` (we used Claude Code).
- **Don't commit** `.env`, model artifacts (`models/*.joblib`), `__pycache__`, `node_modules` — already in `.gitignore`.
- **Update this file** (status + owner + any gotcha) in the same PR that finishes a phase.

---

## 5. Phase tracker

Status: ✅ done · 🚧 in progress · ⬜ todo. Update the row when you pick up / finish a phase.

| Phase | Scope | Status | Owner | Branch | Acceptance (see Implementation.md) |
|------:|-------|:------:|-------|--------|-------------------------------------|
| 0 | Scaffold + Docker Compose topology + gateway skeleton | ✅ | — | merged | `/health` 200, `/docs` loads |
| 1 | PostgreSQL OLTP schema (16 tables) + Alembic | ✅ | — | merged | `alembic upgrade head` → 16 tables, `alembic check` no drift |
| 2 | Pydantic canonical contracts | ✅ | — | merged | `BehaviorPayload` validates fixture; schema tests pass |
| 3 | Kafka topics + event production | ✅ | — | merged | 6 topics created; produce→consume round-trip |
| 4 | Flink feature engine (Kafka→Redis+S3) | ✅ | — | merged | job RUNNING → Redis keys populate + S3 mirror; `test_windows`/`test_sinks` pass |
| 5 | Feature reader (Redis-only) + dataset loaders + offline training | ✅ | — | phase-5-feature-reader | `read_bundle` hits Redis only; IF + XGBoost artifacts in S3 + registry |
| 6 | Scoring service (IF → XGBoost stacked) + explain + registry | ⬜ | | | stacked score + reason codes; degraded fallback; amplifier math |
| 7 | Decision engine + adaptive auth + risk×action + txn-fraud layer | ⬜ | | | band→action; cold-start→verify; controls fire |
| 8 | Gateway flows: integrity, login, step-up, payment, JWT, hardening, consent, audit | ⬜ | | | `/auth/login` + `/payment/score` return `DecisionResponse` |
| 9 | Continuous re-scoring + SOC WS broadcaster + case mgmt + RTBF/quarantine jobs | ⬜ | | | `/behavior/ingest` + `/ws/soc-feed` live |
| 10 | behavior-sdk (TypeScript) | ⬜ | | | capture + signed payload; SDK tests |
| 11 | web-app + bank-dashboard | ⬜ | | | full demo via `--profile ui` |
| 12 | Model governance: registry, champion/challenger, drift, feedback loop | ⬜ | | | shadow scoring + promotion + drift |

**Dependency graph (what can run in parallel):**
```
P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7 → P8 → P9 → P11 → P12
                  └───────────────────────────► P10 (SDK; needs only P2's payload shape)
```
P10 (SDK) can start in parallel once Phase 2 contracts are frozen. P11 (UI) needs P8–P10. P12 builds on P5/P6/P9.

---

## 6. Architecture guardrails (the non-negotiables)

Full list in [`CLAUDE.md`](CLAUDE.md) §6. The ones that bite if ignored:
- **Inference reads Redis ONLY** on the hot path — never PostgreSQL, never recompute Flink windows.
- **Stacked scoring:** Isolation Forest → `Behavior_Score` → XGBoost → one fraud probability. (Weighted ensemble is the configurable alternative — never both.)
- **Bands/thresholds/amplifiers come from the active policy** — never hardcode.
- Decisions are `allow` / `verify` / `block`; bands `low`/`medium`/`high`/`very_high`.
- **No graph database / no graph mule-network detection** — out of scope, all phases.
- Cold-start → `verify`, never `block`. ML failure → fall back + flag `degraded_mode`.
- Verify & **consume** the telemetry nonce before trusting a payload (anti-replay).
- Latency budgets: login p95 < 300 ms, payment p95 < 500 ms.

---

## 7. Repo layout (where things live)

```
gateway/        FastAPI gateway: app/{models,schemas,services,scoring,routers}, scripts/, tests/, alembic/
flink-jobs/     PyFlink feature engine: feature_engine.py, sinks.py, windows.py, tests/, Dockerfile
training/       offline training + registry + drift (Phase 5/12)
behavior-sdk/   TS capture SDK (Phase 10)
web-app/        Internet Banking demo (Phase 11)
bank-dashboard/ Fraud-ops / SOC dashboard (Phase 11)
SAMPLE_DATA/    CMU, HMOG (+ hmog_features.csv + eda_report.md), INB_REQ_LOG, TXN_HISTORY_UPI_FIN
models/         local mirror of S3 model artifacts (gitignored)
```

---

## 8. Gotchas & operational notes (learned while building)

- **Dev bind-mounts:** compose mounts `./gateway:/app` and `./flink-jobs:/flink-jobs` so source edits are live (no rebuild for code changes). Rebuild the image only when **dependencies** change: `docker compose build gateway` (or `flink-jobmanager`).
- **pytest lives in the gateway image** (`.[dev]` in the Dockerfile). If a fresh container says "No module named pytest", you're on an old image — `docker compose build gateway`.
- **Flink job is submitted manually** after the stack is up (see §2). It is not auto-submitted on startup yet. Re-submit after changing `feature_engine.py`/`sinks.py` (cancel the old job first: `flink cancel <jobid>` or via the Flink UI).
- **Flink value-only stream:** topic **values carry the routing id** (`user_id`/`device_id`) because the Kafka message key isn't available to the value-only deserializer. Keep that field populated in producers.
- **runc "working directory is outside mount namespace" on `docker compose exec`:** a stale-container quirk after recreates — `docker compose restart gateway` and retry.
- **Migrations:** the gateway auto-runs `alembic upgrade head` on startup (`RUN_MIGRATIONS_ON_START=true`). To add a migration: edit models → `docker compose exec gateway alembic revision --autogenerate -m "msg"` → review the generated file (it's root-owned via the mount; `chown` it back or edit inside the container) → `alembic upgrade head`.
- **S3/MinIO:** bucket `cogniguard` is created by the `minio-init` one-shot service. Inspect via boto3 from the gateway, or the MinIO console at :9001.
- **Windows checkout — CRLF breaks `entrypoint.sh`:** with `core.autocrlf=true` and no `.gitattributes`, git checks the file out with CRLF, and the container's `#!/usr/bin/env bash` shebang then reads as `bash\r` → `env: 'bash\r': No such file or directory`, gateway exits 127. Fixed by adding `.gitattributes` (`*.sh` / `entrypoint.sh` forced to `eol=lf`) — this should no longer bite on a fresh Windows clone. If it ever recurs: `sed -i 's/\r$//' gateway/entrypoint.sh`.
- **Gateway started but port 8000 not reachable after a crash-loop:** if the gateway container was created once while crashing (e.g. the CRLF issue above) and you only `docker compose up -d gateway` afterward, the port publish can silently not bind (`docker port` shows nothing even though `docker-compose.yml` has `ports: ["8000:8000"]`). Fix: `docker compose up -d --force-recreate gateway`.
- **`training/` package:** added a `./training:/app/training` bind mount on the `gateway` service so `python -m training.xxx` resolves from `/app` — `training/` isn't part of the `gateway` image build (different top-level dir), it only works via this dev mount. Training scripts reuse `app.db`/`app.s3_client`/`app.config` directly (same container, same Python env) rather than re-implementing clients — that's intentional, not a violation of the Redis-only rule (that rule is about the *scoring* hot path, not offline training).
- **Phase 5 model quality is a known gap, not a script bug:** `train_isolation_forest` prints **EER 0.29** against TXN_HISTORY/CMU (target G6 ≤ 0.10) — it's validated honestly against the *reduced* 4-dim typing vector the live system actually ships (`typing_speed`/`key_latency_avg`/`typing_rhythm_std`/`hold_time_avg`), not the richer 31-dim raw CMU vectors papers usually report ~1–10% EER on. `train_xgboost` found **0 positives** from the PRD heuristic label on the 100-row TXN_HISTORY_UPI_FIN sample (mostly single-transaction payers → cold-start `amount_zscore=0` → heuristic never fires) — AUC is `None`. Both scripts run end-to-end and register `production` models (mechanically satisfies the Phase 5 acceptance check), but neither model is meaningfully trained yet. Revisit in Phase 6/12: either loosen the heuristic, get a larger/labeled TXN sample, or accept IF/XGBoost as placeholders until real data arrives — flag to whoever owns Phase 6.
- **No real join between `INB_REQ_LOG` and `TXN_HISTORY_UPI_FIN`:** the two sample extracts use disjoint user/account id namespaces, so `train_xgboost` does *not* join INB session features in (it sets a neutral `behavior_score=0.5` constant instead, documented in the script's docstring). A live system would join on the same `user_id` once both come from `behavior_events`/`transaction_events`.

---

## 9. Open items for upcoming phases

- **Phase 6:** improve label quality (see gotcha above) before trusting `xgboost_txn`'s output; per-user `behavior:{id}:baseline` (already written by Flink) should do the real biometric discrimination — the global IF prior is only the cold-start fallback, not expected to hit G6 alone.
- **Auto-submit Flink job** (gateway startup or a flink-init service) — currently manual.
