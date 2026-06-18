# CogniGuard — Build Progress & Team Guide

Living tracker + onboarding for the team. **Read this first**, then the four source docs.
Keep this file up to date: when you finish a phase, tick it here in the same PR.

> **Last verified:** Phase 9 complete on `phase-6-scoring-service` (branched from
> `phase-5-feature-reader` — none of the three are merged to `main` yet; `main` still
> only has Phase 0–4). On top of Phase 8's hot paths, a human can now also: POST
> `/api/v1/behavior/ingest` (Bearer-authenticated continuous re-scoring — a `very_high`
> band terminates the session, denylists its JWT, and opens a case; otherwise it
> updates `session:risk:{id}` and returns `{action:"allow"}`); connect to `WS
> /ws/soc-feed` and see `risk_scores`/`decisions` Kafka events live (broadcaster bridges
> them through Redis pub/sub); and drive `/api/v1/admin/cases` GET/PATCH (analyst
> assign/note/resolve, with `confirmed_fraud`/`false_positive` writing a labeled row to
> S3 for Phase 12). `python -m app.jobs.quarantine` promotes/discards step-up telemetry
> past its clean window; `python -m app.jobs.rtbf` hard-deletes a withdrawn user's
> `behavior_samples` + Redis baseline while retaining the audit trail. Verified by hand
> against the live stack (curl/httpx/WS round-trips, plus running both jobs from the
> CLI) in addition to the automated suite (110 tests passing).
>
> **Phase 10 (behavior-sdk) is also now done**, same branch. The standalone TS package
> at `behavior-sdk/` mirrors the gateway's signing scheme exactly: `KeystrokeCapture`/
> `MouseCapture`/`TouchCapture` (events.ts) buffer raw timing/motion data (password
> fields always masked to `"x"`); `fingerprint.ts` builds the device fingerprint;
> `edge.ts` does mobile edge feature extraction with the same math as
> `feature_reader.py`'s web-path reduction; `payload.ts` fetches a nonce, computes
> `canonical(metrics)` byte-for-byte matching Python's `json.dumps(sort_keys=True,
> separators=(",",":"))` (including the float-coercion quirk — see gotcha below), and
> signs with HMAC-SHA256 via Web Crypto; `index.ts` exposes the public
> `CogniGuard.init/attach/collect/startContinuous` API. `npm run build && npm test`
> green (23 tests) — including a cross-check of `signPayload()`'s `integrity_sig`
> against an independently computed `node:crypto` HMAC using the same formula.

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
| 6 | Scoring service (IF → XGBoost stacked) + explain + registry | ✅ | — | phase-6-scoring-service | stacked score + reason codes; degraded fallback; amplifier math |
| 7 | Decision engine + adaptive auth + risk×action + txn-fraud layer | ✅ | — | phase-6-scoring-service | band→action; cold-start→verify; controls fire |
| 8 | Gateway flows: integrity, login, step-up, payment, JWT, hardening, consent, audit | ✅ | — | phase-6-scoring-service | `/auth/login` + `/payment/score` return `DecisionResponse` |
| 9 | Continuous re-scoring + SOC WS broadcaster + case mgmt + RTBF/quarantine jobs | ✅ | — | phase-6-scoring-service | `/behavior/ingest` + `/ws/soc-feed` live |
| 10 | behavior-sdk (TypeScript) | ✅ | — | phase-6-scoring-service | capture + signed payload; SDK tests |
| 11 | web-app + bank-dashboard | ⬜ | | | full demo via `--profile ui` |
| 12 | 
Model governance: registry, champion/challenger, drift, feedback loop | ⬜ | | | shadow scoring + promotion + drift |

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
- **`behavior:{id}:baseline` naming mismatch (pre-existing Phase 4 gap, surfaced in Phase 6):** Flink's `update_from_behavior_event` (`flink-jobs/sinks.py`, `BEHAVIOR_FEATURES`) only tracks 5 abbreviated dims — `typing_speed`, `key_latency`, `swipe_angle`, `touch_pressure`, `mouse_velocity` — not the 9 `BehaviorFeatures` names `gateway/app/schemas/features.py` defines (`key_latency_avg`, `swipe_angle_dev`, `touch_pressure_avg`, `mouse_velocity_mean`, plus `typing_rhythm_std`/`hold_time_avg`/`swipe_velocity_norm`/`acceleration_variance` aren't tracked by Flink's baseline at all). `gateway/app/scoring/isolation_forest.py`'s `load_baseline`/`_BASELINE_KEY_MAP` defensively maps the 5 overlapping dims and passes the other 4 through unstandardized rather than crashing or guessing — not fixed here since `flink-jobs/` is a separate deployment unit and renaming its keys risks breaking Phase 4's merged tests. Worth a follow-up ticket to widen Flink's baseline tracking to the full 9-dim vector.
- **Phase 6 scoring service is feature-complete but unwired:** `gateway/app/scoring/{isolation_forest,xgboost_model,registry,amplifiers,explain,stack}.py` implement the stacked IF→XGBoost score, the weighted-ensemble alternative, Dynamic Risk Amplifiers, the deterministic reason-code explainer, and NFR-4 fallback — but `Registry` is not yet instantiated anywhere in `main.py`, and no router calls `stack.score()` yet. That wiring is Phase 8's job, per the dependency graph.
- **No `policies` table — `policy.py` is Redis-cached, not DB-backed:** `Implementation.md` describes `policy.py`'s `active_policy()` as "DB-backed single active row, else defaults," but the canonical 16-table OLTP schema (PRD §17.1) has no `policies` table, and Phase 8's file list doesn't add one either. Phase 7 implements `gateway/app/services/policy.py` as `DEFAULT_POLICY` (a complete dict: thresholds, action_sensitivity, amplifiers, stepup ladder, cooling_off, hardening) optionally deep-merged with a `policy:active` JSON blob read from Redis — the same small-live-config role Redis already plays for nonces/locks/counters, and what lets an admin policy edit (Phase 8's `PUT /admin/policy`) take effect live without a restart or a Postgres read on the hot path. `active_policy()` never raises — missing/empty/malformed/unreachable Redis all fall back to defaults. **Whoever builds Phase 8's `/admin/policy` endpoint**: write the overlay to the `policy:active` Redis key (see `POLICY_REDIS_KEY` in `policy.py`), not a new table.
- **Phase 7 decision layer is pure logic, not yet called by any router:** `gateway/app/services/{decision_engine,adaptive_auth,txn_fraud_layer}.py` are fully implemented and tested (`tests/test_decision.py`, `tests/test_adaptive_auth.py`, `tests/test_txn_fraud_layer.py`, `tests/test_policy.py` — 31 new tests) but nothing calls them yet. Phase 8's `auth_flow.py`/`payment_flow.py` are the first real callers: get `ScoreResult` from `stack.score()` → `decision_engine.decide(result.risk_band, action_type, policy=policy, cold_start=..., degraded=result.degraded_mode)` → if `action=="verify"`, `adaptive_auth.select_factor(decision.assurance, device_caps, policy["stepup"])` → on the payment path, also `txn_fraud_layer.resolve_controls(result.risk_band, result.amplifiers, txn_ctx, policy)`.
- **`RISK_ACTION_MATRIX` in `decision_engine.py` is a module constant, not in the policy dict:** it transcribes PRD §10.2 verbatim (the *shape* of band×stakes→action). Only the per-action-type stakes *classification* (`policy["action_sensitivity"]`) is policy-driven/admin-tunable — e.g. a bank could decide `"raise_limit"` should be `medium`-stakes instead of `high`. If a future phase needs the matrix cells themselves to be admin-editable too, move `RISK_ACTION_MATRIX` into the policy dict at that point; Phase 7 kept it a constant to match `Implementation.md`'s own pseudocode shape and avoid speculative configurability.
- **Phase 8 wired everything end-to-end** — `routers/{auth,payment,risk,admin}.py` mounted under `/api/v1`, `app.state.registry = Registry()` instantiated once in `main.py`'s lifespan (`deps.get_registry` reads it back out), `deps.get_current_user` is denylist-only (decodes the JWT, checks `jwt:denylist:{jwt_id}`, no extra Postgres read beyond loading the `User`/`Session` rows the caller actually needs). Manually verified against the live stack (curl/httpx round-trips for register→consent→login→payment) in addition to the 98-test automated suite.
- **`canonical(metrics)` for the HMAC signature is defined in `integrity.py`, not in any doc** — `Implementation.md`/Architecture specify `key=sha256(jwt_secret+nonce)` and `msg=nonce‖canonical(metrics)‖fingerprint‖ts` but never pin down what "metrics" actually serializes (the behavior-sdk that would need to mirror this, Phase 10, doesn't exist yet). `integrity.canonical_metrics()` is the one definition: a sorted-key, no-whitespace JSON dump of `{channel, source, action, keystroke, mouse, touch, derived_features, context}` — everything in `BehaviorPayload` except the signature envelope (`nonce`/`seq`/`ts`/`integrity_sig`) and `device` (only its `fingerprint` is bound in, separately). **Whoever builds Phase 10's SDK must mirror this exactly.**
- **Two new Redis key families not in Architecture §4.1's catalog** (same pattern as Phase 7's `policy:active`): `seq:{binding}` (int, persists the monotonic-seq floor for anti-replay — `binding` = device fingerprint pre-login, `session_id` once one exists) and `user:{user_id}:new_payees_recent` (SET, TTL 1h, tracks distinct new payees for the `RAPID_FANOUT` amplifier's `new_payee_count_recent` input). Both originate in `integrity.py`/`payment_flow.py` respectively.
- **`session:risk:{session_id}` originates in Phase 8, not Phase 9** — `auth_flow.py`/`payment_flow.py` write it after every scoring event so `GET /api/v1/risk/session/{id}` has real data immediately; Phase 9's continuous re-scoring just keeps writing the same key.
- **Found and fixed during Phase 8 integration testing:** `decision_engine`'s `RISK_ACTION_MATRIX` cells carry `cooling_off`/`reconfirm` flags (e.g. low risk + high-stakes new payee → "verify + cooling-off", PRD §10.2) but `txn_fraud_layer.resolve_controls()` only triggers from `risk_band`/fired amplifiers — it has no visibility into those matrix-level flags (its own Phase 7 signature/tests didn't change, by design). `payment_flow.py` merges both signals after calling `resolve_controls()`: if `decision.cooling_off`/`decision.reconfirm` is set and `txn_controls` didn't already populate that field, it fills in `cooling_until`/`reconfirm` from `policy["cooling_off"]`. Without this merge, a low-risk-but-high-stakes new-payee transfer would say `action: "verify"` but return empty `txn_controls` — caught by `tests/test_payment_flow.py::test_new_payee_high_value_populates_txn_controls_when_flagged`.
- **`Session.ip_address` is a Postgres `INET` column** — `routers/auth.py`/`routers/payment.py`'s `_client_ip()` validates `request.client.host` via `ipaddress.ip_address()` and falls back to `"0.0.0.0"` for anything unparseable (e.g. `TestClient`'s default `"testclient"` host, or a misconfigured reverse-proxy header) — found via `test_auth_flow.py` failing with a Postgres `InvalidTextRepresentation` error before this fix.
- **Real ASN/GeoIP lookup is out of scope** — `_client_asn()` in both routers reads an optional `X-Demo-Asn` header (no GeoIP/ASN library is wired into this project); `asn` is `None` in any real deployment until that's added. The distributed-bruteforce-detection counter (`bruteforce:asn:{asn}`) is only exercised when that header is present.
- **Real model quality (Phase 5/6 gap) means `test_auth_flow.py`/`test_payment_flow.py` assert structure, not specific outcomes** — confirmed deliberately (not a synthetic-model override) when planning Phase 8. Tests check `action in {allow,verify,block}` and that the *consequences* of whichever action came back are correct (JWT+Session on allow, AuthChallenge+step-up on verify, no token on block) rather than asserting a specific genuine/impostor verdict. The step-up-completion test sidesteps model nondeterminism entirely by seeding the `AuthChallenge`/`stepup:{id}` state directly rather than depending on a real login returning `verify`.
- **Phase 9's `/behavior/ingest` does not call `decision_engine.decide()`** — Architecture §6.4's sequence is a flat two-branch safety net on `risk_band` (`very_high` → terminate the session + denylist its JWT + open a case; else → update `session:risk:{id}` and `{action:"allow"}`), not a stakes-gated action attempt like login/payment. `entity_type="transaction"` is used for its `risk_scores`/`decisions` rows (CLAUDE.md's canonical entity types are only `login`/`transaction`; Implementation.md literally says "entity `transaction`/continuous" for this path). New logic lives in `services/behavior_flow.py` (not named in Implementation.md's Phase 9 file list, but added to match every prior phase's thin-router convention).
- **Case-opening on `block`/`very_high` is one shared `case_mgmt.maybe_open_case(...)` background task**, called from all three scoring call sites (`auth_flow.login`, `payment_flow.score_payment`, `behavior_flow.ingest`) — `schemas/admin.py`'s `CaseUpdate` (and `UserDetailOut.quarantined_samples`, previously always 0) were defined back in Phase 2 and just got wired up here via `/admin/cases` GET/PATCH.
- **The SOC broadcaster (`services/broadcaster.py`) uses an ephemeral, per-instance Kafka consumer group (`soc-broadcaster-{uuid}`) reading from `"latest"`**, not the shared/persistent group `kafka_client.get_consumer()` gives every other consumer in this codebase. It's a live tail-the-topic fan-out, not a stateful processor: a persistent shared group caused real rebalance-contention flakiness in `test_continuous.py`'s WS test every time `uvicorn --reload`/a fresh `TestClient(app)` restarted the lifespan (each restart rejoining the same group while the previous member was still leaving). `"latest"` also means a freshly (re)started broadcaster won't replay backlog — by design for a live feed, but it does mean a WS client that connects and expects to see an event needs the broadcaster's consumer to have completed partition assignment first; `test_continuous.py` adds a short grace sleep before producing traffic for exactly this reason.
- **`jobs/quarantine.py`/`jobs/rtbf.py` are one-off CLI scripts** (`python -m app.jobs.quarantine` / `python -m app.jobs.rtbf`), not wired to any scheduler — there's no APScheduler/cron in this repo yet. Run them manually or via an external K8s CronJob in a real deployment.
- **`jobs/rtbf.py` only purges `behavior_samples` + the Redis `behavior:{id}:baseline` key** (the "per-user model artifact") for `consent_status=WITHDRAWN` users, plus any `BehaviorSample` past `retention_expires_at` regardless of consent — `risk_scores`/`decisions`/`audit_logs` are left untouched since they carry score/band/decision, not raw biometric data, so there's nothing in them to strip per Implementation.md's "retain stripped to score/band/decision" wording.
- **Phase 10's behavior-sdk mirrors `integrity.canonical_metrics()` exactly** (see
  gotcha above) — there's no other source of truth for the HMAC message format since
  Phase 8 is the first place it's ever been implemented. `behavior-sdk/src/payload.ts`'s
  `canonical()` recursively sorts object keys and serializes with no whitespace to match
  Python's `json.dumps(sort_keys=True, separators=(",",":"))`.
- **Known security gap, carried forward on purpose:** the HMAC signing key derives from
  `key=sha256(jwt_secret+nonce)` — a *server* secret — per `Implementation.md` line 499's
  literal formula, so `behavior-sdk`'s `CogniGuard.init({signingSecret})` has to be
  configured with that same secret to sign client-side, which means it ends up in
  client-served JS once `web-app` (Phase 11) wires this in. This is a real weakness for
  a production deployment, accepted here as a documented prototype simplification (not
  redesigned in Phase 10, since `CLAUDE.md` says not to invent alternatives to a
  doc-pinned contract). **Real fix for a later phase:** have the gateway mint a
  short-lived, per-nonce signing key returned alongside `GET /auth/nonce` instead of
  reusing `jwt_secret`, so the actual JWT secret never has to leave the server.
- **Cross-language float-formatting quirk in `canonical(metrics)`:** Pydantic coerces
  any `float`-typed `BehaviorPayload` field (keystroke `down`/`up`, the three `context`
  timing fields, every `derived_features` value) to a Python `float` on parse, so when
  `integrity.canonical_metrics()` re-serializes the model, a whole-number value like
  `12` always renders as `"12.0"` — never `"12"` — regardless of what the wire JSON
  looked like. JS's `JSON.stringify(12)` renders `"12"`, which would silently break the
  signature match. `behavior-sdk/src/payload.ts` works around this with a `pyFloat()`
  leaf marker (`canonical()` renders `pyFloat(12)` as `"12.0"`) applied only to those
  specific Pydantic-`float`-typed leaf positions; `mouse`/`touch` fields are untyped
  `dict` passthroughs on the gateway side (no coercion), so their numbers are left as
  plain JS numbers, matching Python's pass-through behavior. Verified in
  `payload.test.ts` by independently recomputing the HMAC via `node:crypto` (a different
  crypto API than the implementation's Web Crypto path) and asserting a byte-for-byte
  match.
- **`canonical(metrics)` agreement never depends on dict/object insertion order, on either side:** `canonical()` (JS) sorts keys via `Object.keys(obj).sort()` at *every* level it recurses into — top-level metrics, nested blocks, objects inside arrays — exactly as Python's `sort_keys=True` re-sorts every dict its encoder visits, at any depth (stdlib guarantee, not just the top level). Neither implementation ever trusts caller-supplied insertion order. `payload.test.ts` has two regression tests for this: `canonical()` given the same logical tree built with reversed key order at every level produces an identical string, and `signPayload()` given two logically-identical `UnsignedPayload`s whose nested objects (`device`, `context`, `keystroke.events[]` entries) declare keys in reverse order — with the system clock frozen via `vi.useFakeTimers()` so `ts` matches and key order is the only variable — produces the same `integrity_sig`. (Array *element* order, e.g. the sequence of keystroke events, is intentionally **not** order-independent — it's meaningful temporal data, not a set — so that test holds the events array order fixed and only varies each event object's own key order.)
- **Phase 6 inherits the Phase 5 model-quality gap:** improve label quality before trusting `xgboost_txn`'s output in a real demo; per-user `behavior:{id}:baseline` should do the real biometric discrimination once it tracks the full 9-dim vector (see gotcha above) — the global IF prior is only the cold-start fallback, not expected to hit G6 alone.
- **`phase-5-feature-reader` and `phase-6-scoring-service` are not merged into `main` yet** — `main` currently only has Phase 0–4. Whoever merges should land Phase 5 before Phase 6 (Phase 6 branches from Phase 5, not from `main`). Phases 7, 8, and 9 were all built directly on `phase-6-scoring-service` (same branch, no new branch cut) since they're tightly-coupled follow-ons to Phase 6's scoring service.
- **Phase 10 is done; Phase 11 (web-app + bank-dashboard) is next** per the dependency graph (§5) — it needs Phases 8–10 (gateway flows, this SDK).
- **Auto-submit Flink job** (gateway startup or a flink-init service) — currently manual.
- **No real GeoIP/ASN lookup, captcha provider, or WebAuthn/biometric verification** — all demo stand-ins (see Phase 8 gotchas above). Real RBAC for `/admin/*` also still pending (currently a shared `X-Admin-Token` header check).
