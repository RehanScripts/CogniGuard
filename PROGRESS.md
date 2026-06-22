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
>
> **Phase 11 (web-app + bank-dashboard) is also now done**, same branch. Along the way,
> a real gap surfaced: `gateway/scripts/seed_demo.py` and `generate_fraud_scenarios.py`
> (Implementation.md §5/§7) had never actually been written — only `create_topics.py`/
> `load_datasets.py` existed — so a fresh `docker compose up` had no demo persona and a
> new user could never escape cold-start. Both scripts are now built (full fidelity:
> the `genuine` persona + policy + Redis baseline/known-sets + `scammer@upi` beneficiary,
> and all 5 named fixtures, signed for real via `integrity.issue_nonce`/
> `compute_signature`), wired into `entrypoint.sh` under `RUN_SEED_ON_START`, and
> verified end-to-end against the live stack: `genuine`/`Passw0rd!` with steady typing
> now resolves to `low`/`allow`; the impostor fixture correctly fires `NEW_DEVICE` +
> high-sigma deviation reason codes (band escalation itself is still capped by the
> already-documented Phase 5/6 model-quality gap, not a Phase 11 bug); the coercion
> fixture against `/payment/score` fires `NEW_BENEF_HIGHVAL ×1.5` with cooling + manual
> amount, exactly per the demo script. `web-app/` (Login → StepUp → Dashboard →
> Transfer/Payment) and `bank-dashboard/` (Live/UserDetail/Policy/Cases/Governance) are
> both built, type-checked, linted, and built for production cleanly; `npm test` green
> in both (9 + 13 tests). `docker compose --profile ui up --build` brings up all three
> new images alongside the existing stack. See §8 for the gotchas this surfaced
> (timestamp-skew fixture freshness, the SDK's `startContinuous` blind spot, the
> `IntegrityFlag`/live-feed gap, and others).
>
> **Phase 12 (model governance) is also now done**, on its own branch
> `phase-12-model-governance` (branched from `phase-11-web-app-dashboard`). New pieces:
> `training/promote.py` (`promote_to_production`/`rollback`, CLI `--model --version --to
> --rollback`) flips `model_registry.stage` and writes one `AuditLog` row per flip;
> `training/drift_monitor.py` computes PSI/KS on the `risk_scores` table's persisted
> score columns (live window vs. an older reference window — there's no table that
> persists historical per-request feature vectors, so the score columns are the only
> "online distribution" data that exists) plus outcome precision over resolved cases,
> and on a breach registers a new `staging` challenger via the existing training
> scripts' new `--stage` flag (never straight to `production`); `gateway/app/scoring/
> shadow.py` runs a `staging` challenger alongside the champion on every login/payment/
> continuous-ingest scoring call (`Registry.get_challenger()`), persisting a flagged
> `is_shadow=True` `RiskScore` row — never a `Decision` row, never broadcast to the live
> SOC feed, excluded from `/admin/events`/`/admin/users/{id}` by default. `GET/POST
> /api/v1/admin/models`, `.../promote`, `.../rollback`, and `GET /api/v1/admin/drift`
> expose all of this; `bank-dashboard`'s `DriftPanel` is now wired to both (read-only —
> no promote/rollback buttons by design). Verified end-to-end against the live stack:
> registered a `staging` challenger, drove a real login, confirmed the shadow row
> appeared with the challenger's version and that `/admin/events` never returned it,
> promoted it to `production` (previous production row auto-archived, `AuditLog` row
> written), rolled back, and ran `python -m training.drift_monitor` for a live PSI/KS
> report — in addition to the automated suite (131 gateway tests + 4 drift tests + 15
> bank-dashboard tests, all green). See §8 for two gotchas this surfaced: the
> single-migration-file edit trap, and `Registry.reload()`'s cross-process limit.
>
> **Phases 13–19 (LSTM Autoencoder primary + native Android on-device TFLite) added to
> the tracker on `phase-6-scoring-service`, none started yet.** This is a deliberate
> architecture shift from the PRD v2.0 / CLAUDE.md framing of "XGBoost primary + IF net,
> LSTM is Phase 2 only": the **LSTM Autoencoder becomes the primary behavioral model**
> (reconstruction error over a rolling 9-dim sequence window → a new common
> **calibration layer** → unified `Behavior_Score`), **Isolation Forest becomes the
> cold-start + degradation fallback and runs in shadow** otherwise, and a **native
> Android (Kotlin) app + capture SDK** runs the autoencoder on-device via TensorFlow
> Lite so only the reconstruction error/derived features leave the device. The
> downstream stack (XGBoost, decision engine, amplifiers, bands, reason codes,
> continuous re-scoring) is unchanged — see Implementation.md Phases 13–19 for the
> file-by-file plan and the full plan file for the design rationale. Phase 19
> (PRD.md/CLAUDE.md/System Architecture.md) is the last phase precisely because those
> docs should describe the shipped contracts, not the in-flight ones.
>
> **Phase 13 (calibration layer + LSTM Autoencoder scoring module) is now done**, on
> `phase-12-model-governance` (no new branch cut, same pattern as Phases 7–9 on
> `phase-6-scoring-service`). New pieces, both pure and uncalled by anything yet —
> `stack.py` is untouched, this phase is inert by design: `gateway/app/scoring/
> calibration.py` (`CalibrationParams`, `calibrate_ae`/`calibrate_if` — robust-z →
> logistic, anchored so `raw == threshold → ~0.5`, same 0=normal/1=anomalous polarity as
> `isolation_forest.behavior_score`; `load_calibration()` reads per-user
> `behavior:{id}:ae_calib` else population `calib:ae:population` else a built-in
> default — nothing seeds either Redis key yet, that's Phase 16) and `gateway/app/
> scoring/autoencoder.py` (`reconstruction_error()` — masked MSE over a `(16,9)` window
> matching `BEHAVIOR_COLUMNS`, against an **injected** `onnxruntime.InferenceSession`,
> mirroring `isolation_forest.py`'s injected-model shape; `behavior_score()` runs it
> through `calibrate_ae`). `gateway/app/scoring/registry.py`'s `_load()` now branches
> artifact filename + loader by `model_name` (`_ARTIFACT_SPECS` dict) so
> `lstm_autoencoder` resolves `model.onnx` via `onnxruntime.InferenceSession` while
> `isolation_forest`/`xgboost_txn` keep their existing `model.joblib`/`joblib.load`
> path unchanged — `get()`/`reload()`/`get_challenger()` untouched. **Gap not in
> Implementation.md's Phase 13 file list:** `onnxruntime` wasn't a declared gateway
> dependency; added `"onnxruntime>=1.17"` to `gateway/pyproject.toml` and rebuilt the
> image (TensorFlow itself correctly stays out of the gateway, confined to `training/`
> per the doc). Verified: `pytest tests/test_calibration.py tests/test_autoencoder.py
> -q` (17 new tests — monotonicity, threshold→~0.5, clamping, population/default
> fallback, IF-polarity match, masked-MSE correctness including all-masked/short
> windows, and the registry's onnx-vs-joblib dispatch) plus the full existing suite (147
> passed; 1 pre-existing Kafka-roundtrip flake in `test_event_producer.py`, confirmed
> unrelated by reproducing it against the pre-Phase-13 baseline too). One real bug
> caught by the clamping test: `calibration._logistic`'s naive `1/(1+exp(-z))` form
> raises `OverflowError` for large-magnitude `z` (expected at the tails of a robust-z
> calibration, not just a theoretical edge case) — fixed with the standard branch-on-sign
> stable-sigmoid form.
>
> **Phase 14 (schema + sequence buffer + feature-reader extensions for AE) is now done**,
> same branch (`phase-12-model-governance`, no new branch cut — same pattern as Phase
> 13). Additive-only schema fields: `ScoreResult` gains `behavior_score_source`/
> `if_shadow_score`/`ae_recon_error`; `BehaviorPayload` gains `ae_recon_error`/
> `ae_model_version` (mobile-only, **not yet** added to `integrity.canonical_metrics()` —
> that's Phase 17, once a Kotlin SDK exists to mirror it); `FeatureBundle` gains
> `behavior_sequence`/`behavior_sequence_mask`/`ae_recon_error`/`ae_cold_start`;
> `FeatureReadContext` gains `session_id`. The real work is in
> `gateway/app/services/feature_reader.py`: a capped Redis LIST ring buffer
> (`behavior:{session_id}:seq`, `RPUSH`+`LTRIM -16 -1`+refreshed 24h `EXPIRE` on every
> push) for the `web` channel, left-padded to `SEQ_LEN=16` so the most recent sample is
> always last; `mobile` never touches Redis for this and just folds through its own
> device-computed `ae_recon_error`. `ae_cold_start` is `True` when fewer than `MIN_SEQ=4`
> real rows exist (web) or no device `ae_recon_error` was supplied (mobile) **or** no AE
> calibration exists yet at all (per-user `behavior:{uid}:ae_calib` or population
> `calib:ae:population` — both still unseeded until Phase 16's `seed_calibration.py`).
> Two small additions beyond Implementation.md's literal Phase 14 file list: `MIN_SEQ=4`
> was added to `gateway/app/scoring/autoencoder.py` (alongside the `SEQ_LEN`/`N_FEATURES`
> it already defined, rather than inventing a second home for it) and
> `calibration.py`'s inline `f"behavior:{uid}:ae_calib"` was extracted into an exported
> `user_calibration_key()` so the new cold-start check can reuse the exact key instead of
> duplicating the string literal. **No caller passes `session_id` yet** —
> `auth_flow.py`/`payment_flow.py`/`behavior_flow.py` are deliberately untouched, exactly
> matching Phase 13's "inert by design" pattern; per Phase 15's own file list
> (`behavior_flow.py` "assemble sequence window pre-score"), wiring real call sites is
> explicitly *not* this phase's job. Confirmed zero behavior change: every existing
> caller still gets `ae_cold_start=True`/`behavior_sequence=None` exactly as before, since
> none of them constructs a `FeatureReadContext` with `session_id` set. Verified:
> `pytest tests/test_feature_reader.py tests/test_schemas.py tests/test_calibration.py
> tests/test_autoencoder.py -q` (12 new tests — buffer push/cap/trim-oldest, left-pad
> shape, cold-start gating on both `MIN_SEQ` and calibration-absence for web and mobile,
> mobile no-Redis-write) plus the full existing suite (158 passed; the same
> `test_event_producer.py` Kafka-roundtrip flake from Phase 13, reconfirmed unrelated by
> reproducing it against this phase's pre-change baseline too). One operational note: the
> live container's `tests/fixtures/*.json` regenerate themselves with fresh nonces/
> timestamps as a side effect of running the suite (the documented ~30s freshness-window
> behavior, §8) — harmless, but worth `git checkout --` reverting before a commit if you
> want a clean diff.
>
> **Phase 15 (AE-primary / IF-shadow / fallback routing) is now done, 2026-06-20**, same
> branch (`phase-12-model-governance`, no new branch cut). This is "the actual behavior
> change" Phase 13/14 set up: `gateway/app/scoring/stack.py`'s `_behavior_score()` now
> routes `Behavior_Score` through the LSTM Autoencoder whenever a usable
> sequence/recon-error is available and the bundle isn't AE-cold-start
> (`_ae_primary()` — mobile uses the device-supplied `ae_recon_error` directly, web runs
> `autoencoder.reconstruction_error()` against the Redis-assembled rolling window);
> Isolation Forest is *always* computed (`_if_shadow()`, unchanged math, just lifted into
> its own function) and logged as `if_shadow_score` regardless of which source wins, and
> is also what AE-cold-start and AE-failure both fall back to. Everything downstream
> (XGBoost, amplifiers, bands, reason codes) is untouched — it only ever sees the
> resulting single `bscore`, never which model produced it. `gateway/app/scoring/
> explain.py` gained the optional `ae_anomaly_reason()` (`BEHAVIOR_AE_ANOMALY`, fires
> only when AE actually drove `bscore` and the calibrated score is above the neutral
> 0.5 midpoint). `gateway/app/services/behavior_flow.py`'s `ingest()` now passes
> `session_id=str(session.session_id)` into `FeatureReadContext` — the one caller wired
> in this phase, per Implementation.md's literal Phase 15 file list, which lets the AE
> ring buffer actually accumulate real rows across repeated continuous-ingest calls in a
> session and eventually clear `MIN_SEQ=4`.
>
> **Three scope decisions, deliberately not in Implementation.md's literal pseudocode:**
> (1) `auth_flow.login()` and `payment_flow.score_payment()` are **not** wired with
> `session_id` this phase — login has no real `Session` row yet at scoring time (it's
> created *after* the decision, only on `allow`/step-up-success), so there's nothing to
> key a rolling window off; payment does have `session.session_id` available and could
> be wired trivially, but isn't in this phase's file list, so it's left for a later
> phase (the AE window will simply accumulate via `behavior_flow.ingest` calls within the
> same session in the meantime). (2) The literal pseudocode checks only
> `bundle.ae_cold_start`, but `FeatureBundle.ae_cold_start` defaults to `False` and every
> hand-built bundle in `test_scoring.py` (Phase 6 baseline) never sets it or
> `behavior_sequence`/`ae_recon_error` either — a literal reading would route those
> bundles into the AE branch, where AE has nothing to run on, "fails," and flips
> `degraded_mode` to `True` for every Phase 6 test. Fixed by also treating "no AE input
> present at all" (`behavior_sequence is None and ae_recon_error is None`) as
> cold-start — there's no signal yet, which isn't a *failure* — so `test_scoring.py`
> needed zero changes. (3) `if_shadow_score` is populated whenever IF succeeds,
> regardless of which source drives `bscore`, matching the goal statement's "always
> computed, logged" framing literally rather than only when AE happens to be primary.
> **Confirmed out of scope, not done:** persisting `behavior_score_source`/
> `if_shadow_score`/`ae_recon_error` into the `RiskScore` Postgres model or the
> `risk_scores` Kafka topic — neither is in this phase's file list; `scoring/shadow.py`'s
> Phase 12 challenger-shadow mechanism still only A/B-tests `isolation_forest`/
> `xgboost_txn`, not `lstm_autoencoder` itself, but needed no change since its
> `_ShadowRegistry` already delegates unknown model names (including
> `lstm_autoencoder`) straight to the real registry. Verified:
> `pytest tests/test_stack_ae.py -q` (7 new tests — AE-primary happy path with an
> if-vs-ae equal-bscore regression guard, AE failure → IF fallback degraded, AE
> cold-start → IF fallback not degraded, both-fail → zero fallback degraded, the
> legacy-no-AE-input-bundle cold-start treatment, the mobile device-recon-error path,
> and the `BEHAVIOR_AE_ANOMALY` reason code) plus the full existing suite unmodified
> (165 passed; the same pre-existing `test_event_producer.py` Kafka-roundtrip flake from
> Phases 13–14, reconfirmed unrelated by re-running it in isolation against this phase's
> change set too).

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

# The Flink feature-engine job is submitted automatically by the one-shot
# `flink-job-submit` service (Phase 26) -- no manual `flink run` step needed.
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
| 11 | web-app + bank-dashboard | ✅ | — | phase-6-scoring-service | full demo via `--profile ui` |
| 12 | Model governance: registry, champion/challenger, drift, feedback loop | ✅ | — | phase-12-model-governance | shadow scoring + promotion + drift |
| 13 | Calibration layer + LSTM Autoencoder scoring module (ONNX, pure) | ✅ | — | phase-12-model-governance | calibration math + AE scorer tests; registry loads ONNX |
| 14 | Schema + sequence buffer + feature-reader extensions for AE | ✅ | — | phase-12-model-governance | `behavior:{session_id}:seq` buffer; new schema fields; no behavior change |
| 15 | AE-primary / IF-shadow / fallback routing in the scoring stack | ✅ | — | phase-12-model-governance | AE drives `Behavior_Score`; IF shadow logged; fallback ladder; regression-safe |
| 16 | LSTM Autoencoder training (ONNX + TFLite + calibration export) | ✅ | — | phase-15-ae-scoring-routing | trains + exports both artifacts; registry promotion; calib seeded |
| 17 | Cross-platform integrity canonicalization (mobile AE fields) | ✅ | — | phase-15-ae-scoring-routing | Python/TS canonical bytes match a shared golden vector |
| 18 | Native Android app + capture SDK (on-device TFLite) | ✅ | — | phase-15-ae-scoring-routing | Kotlin signing matches golden vector; on-device AE scores end-to-end |
| 19 | Docs realignment: PRD.md, CLAUDE.md, System Architecture.md | ✅ | — | phase-15-ae-scoring-routing | no remaining "LSTM Phase 2 only" claims; AE-primary documented |
| 26 | Boot correctness: Flink auto-submit + AE calibration self-seeding | ✅ | — | phase-20-continuous-identity-verification | clean `docker compose up`; Flink job RUNNING with no manual step; `calib:ae:population` present when a local AE artifact exists |
| 27 | Surface & persist trust signals (`trust_score`/`behavior_match_score`/`behavior_score_source`) | ✅ | — | phase-20-continuous-identity-verification | `/auth/login`, `/payment/score`, `/behavior/ingest` all return trust fields; `risk_scores` persists them; `/admin/events` surfaces them; 185 passed/1 skipped |
| 28 | Thin read-only banking endpoints (`/api/v1/banking/*`, authorized exception) | ✅ | — | phase-20-continuous-identity-verification | profile/accounts/transactions/beneficiaries/security-settings return real, PII-masked data behind `deps.get_current_user`; no new writes/models; 191 passed/1 skipped |
| 29 | web-app UI for the Phase 28 banking endpoints | ✅ | — | phase-20-continuous-identity-verification | Dashboard shows real account balance/profile name; new `/transactions` and `/security` pages render transaction/beneficiary/device/session data; `tsc --noEmit`, `eslint`, `vite build` clean; 15/15 vitest passing |
| 30 | Real RBAC for `/admin/*` (CLAUDE.md §8 "role-scoped JWT") | ✅ | — | phase-20-continuous-identity-verification | new `analysts` table (17th, documented exception like Phase 28's banking tables) + `POST /api/v1/admin/login` issuing a separate admin-track JWT (`kind: admin`); `deps.require_role("admin"\|"analyst")` replaces the old shared-secret `require_admin`/`X-Admin-Token` on every route (policy/model writes admin-only, reads either role); bank-dashboard gets a login page + sessionStorage JWT + route guard; seed_demo seeds `admin@cogniguard.dev`/`analyst@cogniguard.dev`; 199 passed/1 skipped; verified live via curl (login, 200 read, 403 write-as-analyst) |

**Dependency graph (what can run in parallel):**
```
P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7 → P8 → P9 → P11 → P12
                  └───────────────────────────► P10 (SDK; needs only P2's payload shape)

P6 → P13 → P14 → P15 → P17 → P18 → P19
      P5 ────────► P16 ─────┘
```
P10 (SDK) can start in parallel once Phase 2 contracts are frozen. P11 (UI) needs P8–P10. P12 builds on P5/P6/P9. P13–19 (LSTM Autoencoder primary + native Android) is a separate track off P6: P16's ONNX/TFLite artifacts feed both P15 (server-side AE) and P18 (Android); P19 (docs) lands last so the authoritative docs describe shipped contracts, not in-flight ones.

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
training/       offline training + registry + drift (Phase 5/12); train_lstm_autoencoder.py (Phase 16)
behavior-sdk/   TS capture SDK (Phase 10)
web-app/        Internet Banking demo (Phase 11)
bank-dashboard/ Fraud-ops / SOC dashboard (Phase 11)
android/        Native Android (Kotlin) capture-sdk/ + demo IB app/ (Phase 18 — not started)
SAMPLE_DATA/    CMU, HMOG (+ hmog_features.csv + eda_report.md), INB_REQ_LOG, TXN_HISTORY_UPI_FIN
models/         local mirror of S3 model artifacts (gitignored)
```

---

## 8. Gotchas & operational notes (learned while building)

- **Dev bind-mounts:** compose mounts `./gateway:/app` and `./flink-jobs:/flink-jobs` so source edits are live (no rebuild for code changes). Rebuild the image only when **dependencies** change: `docker compose build gateway` (or `flink-jobmanager`).
- **pytest lives in the gateway image** (`.[dev]` in the Dockerfile). If a fresh container says "No module named pytest", you're on an old image — `docker compose build gateway`.
- **Flink job is auto-submitted on startup (Phase 26)** by the one-shot `flink-job-submit` compose service (mirrors `minio-init`'s pattern: `depends_on: flink-jobmanager {service_healthy}`, `restart: "no"`), and `gateway` itself waits on `flink-job-submit: {condition: service_completed_successfully}` before starting -- so a clean `docker compose up` alone gets Redis features flowing, no manual `flink run`. A second one-shot, `kafka-topics-init` (gateway image, `python -m scripts.create_topics`), runs first and `flink-job-submit` depends on it too -- without it, the auto-submitted job races ahead of topic creation (`KAFKA_AUTO_CREATE_TOPICS_ENABLE=false`) and fails immediately with `UnknownTopicOrPartitionException`; this was never visible before because the job was always submitted by hand, well after `gateway`'s own lifespan (the only prior topic-creator) had already booted. Re-submit by hand after changing `feature_engine.py`/`sinks.py` on a running stack (cancel the old job first via the Flink UI at :8081, then `docker compose up -d flink-job-submit` to re-run the one-shot).
- **Flink value-only stream:** topic **values carry the routing id** (`user_id`/`device_id`) because the Kafka message key isn't available to the value-only deserializer. Keep that field populated in producers.
- **runc "working directory is outside mount namespace" on `docker compose exec`:** a stale-container quirk after recreates — `docker compose restart gateway` and retry.
- **Migrations:** the gateway auto-runs `alembic upgrade head` on startup (`RUN_MIGRATIONS_ON_START=true`). To add a migration: edit models → `docker compose exec gateway alembic revision --autogenerate -m "msg"` → review the generated file (it's root-owned via the mount; `chown` it back or edit inside the container) → `alembic upgrade head`.
- **`uvicorn` runs without `--reload` (`entrypoint.sh`'s final line is a plain `exec uvicorn ...`):** on a long-lived `docker compose up` dev stack, editing Python source under the bind-mounted `./gateway:/app` does **not** take effect until you `docker compose restart gateway` — confirmed in Phase 27 when a new response field stayed `null` over the wire even though the scoring log line already showed the right value, because the *process* importing the old module was still running. Always restart after a source edit before curling/verifying against a live stack; `pytest`/`TestClient` runs are unaffected (they import fresh).
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
- **Phase 15 is done; Phase 16 (LSTM Autoencoder training pipeline: ONNX + TFLite + calibration export) is next** per the dependency graph (§5). Phases 11, 12, 13, 14, and 15 are on separate/stacked branches (`phase-11-web-app-dashboard`, `phase-12-model-governance` branched from it, Phases 13–15 built directly on `phase-12-model-governance` with no new branch cut) — none is merged into `main` yet.
- **Phase 15's AE-primary path is exercised today only via `behavior_flow.ingest()`'s continuous re-scoring** — `auth_flow.login()`/`payment_flow.score_payment()` were deliberately left unwired (no `session_id` passed into `FeatureReadContext`), so login and payment scoring still always resolve to the IF path until a later phase wires them too (see the Phase 15 summary-block entry above for why). Also, until Phase 16's `seed_calibration.py` seeds `calib:ae:population`, `calibration.load_calibration()` falls back to `default_calibration()` (`scale=1.0, threshold=0.5, temperature=1.0`) for every AE-primary call — usable, but not a real fit, so don't read early AE-primary `behavior_score` values as meaningful before Phase 16 lands.
- **No real GeoIP/ASN lookup, captcha provider, or WebAuthn/biometric verification** — all demo stand-ins (see Phase 8 gotchas above). Real RBAC for `/admin/*` landed in Phase 30 (see below); GeoIP/ASN/captcha/WebAuthn remain demo stand-ins.
- **`gateway/scripts/seed_demo.py` / `generate_fraud_scenarios.py` didn't exist before Phase 11** — Implementation.md §5/§7 described them and `entrypoint.sh` already had the conditional hook, but the files themselves were never written (only `create_topics.py`/`load_datasets.py` existed). Without them, a fresh stack had no demo persona and a freshly-registered user could never reach the clean low-risk `allow` path (no 30-day baseline ⇒ permanent cold-start). Both are now built to full fidelity (genuine persona, policy, Redis baseline/known-sets, `scammer@upi` beneficiary 40 min old, the impostor persona as fixture-only data, and all 5 named fixtures) and reuse existing services exclusively (`policy.DEFAULT_POLICY`, `auth_flow.register/consent_action`, `fingerprint.get_or_create_*`, `integrity.issue_nonce/compute_signature`, `training.train_isolation_forest/train_xgboost`) — no new business logic was invented, only the Redis profile/baseline writer (`_seed_profile_and_baseline`) was genuinely new since nothing else wrote that shape.
- **Fixture freshness is tighter than just "nonce TTL":** `BehaviorPayload.ts` is skew-checked against wall-clock time (`settings.integrity_skew_s`, default 30s), independently of the nonce. A fixture generated at container boot is only good for ~30s after that, not for the rest of the demo session — confirmed by hitting `TIMESTAMP_SKEW`/`INTEGRITY_REJECT` a few minutes after a fresh `docker compose up --build`. Re-run `docker compose exec gateway python -m scripts.generate_fraud_scenarios` immediately before curling/replaying a fixture if more than ~30s has passed since the last generation.
- **Login's `seq` floor is bound to the device fingerprint forever** (`auth_flow.login`, `seq_binding=device_fp`) — and `login_genuine.json`/`login_impostor.json`/`replay_login.json` use fixed, reused fingerprints by design (that's the whole "known device" story). A hardcoded small `seq` would permanently `SEQ_REPLAY` after the very first successful login against that fingerprint, surviving even a fresh regeneration (regenerating only mints a new nonce, it can't roll back the seq floor). `generate_fraud_scenarios.py`'s `_login_seq()` uses wall-clock milliseconds instead; `test_seed_demo.py`'s own login helper matches that same unit so neither side can produce a smaller value than a floor the other already set. Payment's and `/behavior/ingest`'s `seq` are bound to `session_id` instead (a fresh one every login), so `txn_app_fraud.json`/`ingest_hijack.json` don't have this problem.
- **web-app's `file:../behavior-sdk` dependency needs `behavior-sdk/dist/` built before `npm install`** — there's no npm workspace at the repo root, and the SDK's `package.json` `main`/`types` point at `dist/`, not source. `web-app/Dockerfile` builds it inline; doing this locally outside Docker needs `cd behavior-sdk && npm install && npm run build` run once before `cd web-app && npm install`. This also forced `web-app`'s `docker-compose.yml` service to widen its build `context` from `./web-app` to the repo root (`context: ., dockerfile: web-app/Dockerfile`) so the Dockerfile can `COPY behavior-sdk/` at all — `bank-dashboard` needed no such change since it doesn't depend on the SDK.
- **`behavior-sdk.collect()` hardcodes `channel:"web"`** (`index.ts`) — `web-app`'s `ChannelSwitcher` component is therefore visual-only (toggles local UI state, calls an `onChange` callback, has zero effect on captured telemetry). Not fixed by extending the SDK here, since Phase 10 is a frozen contract per CLAUDE.md's "don't invent alternatives" rule.
- **`CogniGuard.startContinuous()` can't surface its `/behavior/ingest` response to the caller** — its `tick()` posts and discards the result (`index.ts`), so `web-app`'s `Transfer.tsx` has no hook to react to a hijack-triggered `{action:"verify",reauth:true}` inline. The mid-session-hijack demo step (Implementation.md §7.1 step 4) has to be driven by POSTing `ingest_hijack.json` directly against `/behavior/ingest` (bypassing the silent background loop) while the UI is open; the UI-side proof is that the *next* authenticated call 401s because the JWT got denylisted. A real fix (an `onResult` callback param) would touch Phase 10's frozen SDK contract, so it's flagged here rather than silently patched.
- **`bank-dashboard`'s `/ws/soc-feed` messages carry no `type` discriminator** (confirmed against `gateway/app/schemas/topics.py`/`routers/ws.py`/`services/broadcaster.py`) — `ws.ts`'s `isDecisionEvent`/`isRiskScoreEvent` infer the type from field presence (`action` vs. `final_risk_score`) instead. Fragile if the two schemas ever both grow an overlapping optional field with one of those names.
- **`IntegrityFlag` is built but can never fire from the live feed today** — `auth_flow.login`/`payment_flow.score_payment`'s early-return `INTEGRITY_REJECT` paths return their reject body directly without ever calling `event_producer.emit_risk_score`/`emit_decision`, and neither `RiskScoreEvent` nor `DecisionEvent` carries an `integrity` field regardless. The component is ready to consume one if a future phase adds it to `DecisionEvent` and makes the reject paths emit too — that's a Phase 7-9 contract change, explicitly out of scope for Phase 11 to make unilaterally.
- **`bank-dashboard`'s `Governance.tsx`/`DriftPanel` were a deliberate partial placeholder through Phase 11** — `/admin/models` and `/admin/drift` didn't exist yet. **Phase 12 wired `DriftPanel` to both** (`api.ts`'s `listModels()`/`getDrift()`): a registered-models table (name/version/stage/deployed_at) and a score-drift table (PSI/KS/breach status per column) plus outcome precision, read-only by design (no promote/rollback UI — those stay API/CLI-only, see the Phase 12 plan's scope decision). `LatencyHistogram` was already wired to real data since Phase 11.
- **JWT is stored in `sessionStorage`, not `localStorage`** (`web-app/src/api.ts`) — cleared on tab close, matches the short-lived demo JWT (`JWT_TTL_MINUTES=30`). A real production app would prefer no JWT in any Web Storage at all (in-memory + refresh-token rotation), but that needs a refresh-token endpoint that doesn't exist here; out of scope for this demo.
- **Both new frontends' `signingSecret`/admin auth come from `.env`/`.env.example`** (mirroring `JWT_SECRET`'s dev value) — consistent with the already-accepted precedent that `behavior-sdk`'s signing secret ends up in client-served JS (gotcha above). `bank-dashboard`'s `VITE_ADMIN_TOKEN`/shared-secret `X-Admin-Token` header is gone as of Phase 30 — it now has a real login page (`AdminLogin.tsx`) issuing a role-scoped JWT; see the Phase 30 gotcha below.
- **Phase 30 RBAC design:** a second, disjoint JWT track (`issue_admin_jwt`/`get_current_analyst` in `app/utils/security.py`/`app/deps.py`) carries `kind: "admin"` + `role` claims, decoded with the same `jwt.decode`/secret as the customer track but never accepted by `get_current_user` (and vice versa — `deps.require_role` rejects a customer session token with 401 since it lacks `kind: "admin"`). A new `Analyst` model/table (17th table, documented exception beyond PRD §17.1's canonical 16, same pattern as Phase 28's banking tables) backs `POST /api/v1/admin/login`. Deliberately **not** done: converting `Case.assigned_to`/`AuditLog.actor_id` (free-text `String`, not FKs) to reference `Analyst` — out of scope, noted here for whoever picks it up next. `deps.require_admin` (the old shared-secret stand-in) was deleted outright once every `/admin/*` route migrated to `require_role`, rather than left as a deprecated shim. Demo logins: `admin@cogniguard.dev`/`analyst@cogniguard.dev`, password `Passw0rd!` (seeded idempotently by `scripts/seed_demo.py`).
- **The gateway container doesn't run uvicorn with `--reload`** — editing router/service/model code under the bind-mounted `./gateway:/app` is visible inside the container immediately, but the running process won't pick it up. `docker compose restart gateway` is required after backend code changes before curling/exercising new routes (confirmed while wiring Phase 30: `/api/v1/admin/login` 404'd until restarted, then worked). Migrations/seeding (`alembic upgrade head`, `python -m scripts.seed_demo`) can still be run via `docker compose exec` without a restart since those are one-off scripts, not the long-lived app process.
- **Editing the single initial Alembic migration doesn't retroactively apply to an already-running dev Postgres volume:** Phase 12 added an `is_shadow` column to `RiskScore` the same way every prior phase extended `9dd0899e3e0a_initial_schema.py` directly (one migration, no chain) — but `alembic_version` already recorded that revision id as applied against this repo's long-lived `pgdata` volume (2+ days of accumulated dev/seed data from earlier phases), so `alembic upgrade head` on gateway startup was a no-op and the column was silently missing until a test actually inserted a row (`UndefinedColumn: is_shadow`). Fixed in place with `ALTER TABLE risk_scores ADD COLUMN IF NOT EXISTS is_shadow boolean NOT NULL DEFAULT false` against the live container rather than `docker compose down -v` (which would have wiped unrelated users/sessions/cases data accumulated since Phase 8). **Whoever next edits this migration file**: either apply the equivalent `ALTER`/`CREATE` by hand against any volume that predates the edit, or start fresh with `docker compose down -v` if there's nothing in it worth keeping — autogenerate/`upgrade head` will not see the diff once the revision id is already marked applied.
- **Phase 28's `/api/v1/banking/*` endpoints deliberately exclude every risk/trust field** (`transaction_risk_score`, `decision`, `decision_reason`, device `trust_score`) even though the wire contract for `/auth/login`/`/payment/score`/`/behavior/ingest` already carries trust fields (Phase 27) — this is an intentional design choice made *now*, not deferred to Phase 29/30's UI stripping, since these are brand-new schemas with no existing precedent to match. `services/banking.py` is the one place in the codebase that masks PII (`utils/mask.py`, new) — account numbers (last 4 visible), email (first char + domain visible), phone (last 4 visible) — there was no prior masking utility.
- **Phase 29 added `web-app/src/pages/Transactions.tsx` and `Security.tsx` rather than folding everything into `Dashboard.tsx`:** Dashboard now fetches `getProfile`/`listAccounts` (replacing the old hardcoded "₹1,00,000.00" balance) and links out to the two new pages for `listTransactions`/`listBeneficiaries` and `getSecuritySettings` respectively — keeping each page's data fetch matched to one or two endpoints, the same granularity Phase 28's router already chose. All three pages reuse the existing `getSessionToken()`-guard-then-`navigate("/login")` pattern from `Transfer.tsx` rather than inventing a `ProtectedRoute` wrapper (no such wrapper exists anywhere in `web-app` yet, so adding one here would be a bigger refactor than this phase's scope). New `api.ts` types/functions (`ProfileOut`/`AccountOut`/`TransactionOut`/`BeneficiaryOut`/`TrustedDeviceOut`/`ActiveSessionOut`/`SecuritySettingsOut`, `getProfile`/`listAccounts`/`listTransactions`/`listBeneficiaries`/`getSecuritySettings`) mirror `gateway/app/schemas/banking.py` field-for-field, same convention as every existing type in that file. Verified: `npm run test -- --run` (15/15, including two new tests per page), `npx tsc --noEmit`, `npm run lint`, and `npm run build` all clean.
- **`Registry.reload()` is process-local, confirmed in practice:** `/admin/models/{name}/promote` and `.../rollback` call `registry.reload(model_name)` in-process so the same gateway worker picks up the flip immediately (verified: promote → next request's `model_version` reflects the new `production` row with no restart). A promotion driven by the documented CLI (`docker compose exec gateway python -m training.promote ...`) runs in a separate, short-lived process and never touches the long-running gateway's cache at all — that worker only re-resolves `model_name` on its own next cache miss (i.e. never, until restart, since `Registry.get()` caches forever once loaded). Not a bug to fix here; if a CLI-driven promotion needs to take effect on a live gateway without a restart, that's a new pub/sub invalidation channel for a future phase, not something Phase 12's scope called for.
