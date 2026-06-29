# CogniGuard Upgrade Plan & Tracker

Production-readiness upgrade across ML, continuous monitoring, auth, SOC, and UX.
Status legend: ⬜ not started · 🟡 in progress · ✅ done · ⏸️ paused/awaiting review

## Context

CogniGuard already has a mature streaming risk pipeline: Kafka→Flink→Redis features,
AE-primary/IF-shadow/XGBoost stacking, decision engine, adaptive auth, txn-fraud layer,
case management, policy engine, SOC live feed, on-device TFLite autoencoder, device/session
models, and Argon2id+JWT auth. This upgrade is therefore mostly **gap-filling and wiring**.

The five requested areas map to concrete gaps:
1. **Continuous monitoring** — capture is gate-based; `/behavior/ingest` exists but is never
   called mid-session; device-trust Redis key exists but is **never written** (no algorithm);
   no UPI-PIN screen and no adaptive pre-UPI-PIN re-auth gate.
2. **SOC dashboard** — live/cases/policy/governance exist; **missing**: auth timeline, device
   intelligence, SHAP, LLM assistant, analyst-only role-gating of risk internals.
3. **Auth** — OTP hardcoded `"123456"`; no signup UI; trusted-device/session endpoints read-only.
4. **UX** — Security Center read-only; no signup; risk internals must stay hidden from users.
5. **ML** — only EER/AUC per model; **no Transformer**, **no unified benchmark**.

### Decisions locked with the user
- **Sequencing: benchmark first, then PAUSE** — build Phase A, present comparison + recommendation,
  stop for review before Phases B–E.
- **OTP: real, email via SMTP** (Redis-backed codes; SMTP creds from env).
- **LLM assistant: pluggable interface + deterministic local stub** now; Claude creds later.
- **Android biometrics: real KeyStore-backed** keypair + server public-key binding + signed assertions.

---

## PHASE A — Model Evaluation Report & Selection  ✅ COMPLETE

Goal: a **comprehensive, presentation-ready model bake-off** evaluating **all suitable behavioral-
authentication and transaction-fraud models** head-to-head on the same data, with a full metrics table,
ROC/PR curves, inference latency, and a **clear recommendation with justification** ("why we chose X")
ready to drop into the hackathon deck. The system has **two distinct ML tasks**, so the report has **two
tracks** plus a combined narrative — each apples-to-apples within its track.

> **Approval gate:** after generating and presenting `MODEL_EVALUATION.md`, **PAUSE and wait for explicit
> approval**. Do **not** integrate/promote any model or start Phases B–F until the user approves the
> recommendation.

### Track 1 — Behavioral biometrics (genuine-vs-impostor)
Data: pooled CMU+HMOG, labeled via the existing Killourhy–Maxion per-subject protocol
(`train_isolation_forest.validate_g6_eer` — reference reps → genuine test + 1 sample/other subject = impostor).
Candidate models:
- **Isolation Forest** (unsupervised, current cold-start prior)
- **One-Class SVM** (unsupervised baseline)
- **LSTM Autoencoder** (current AE-primary; per-window recon error)
- **Transformer Encoder autoencoder** (new — see A1)
- **Random Forest**, **LightGBM**, **XGBoost** (supervised genuine/impostor classifiers on the labeled protocol)
- **Logistic Regression** (simple supervised baseline / sanity floor)

### Track 2 — Transaction fraud (supervised classification)
Data: `training/txn/transactions.parquet` (the same features `train_xgboost.py` uses).
Candidate models: **XGBoost** (current), **LightGBM**, **Random Forest**, **Logistic Regression** (baseline)
— optional **MLP** if time permits. Reports PR-AUC alongside ROC-AUC (fraud is class-imbalanced).

- [x] **A1. Transformer encoder anomaly model** — `training/train_transformer.py` (new).
  Mirror `train_lstm_autoencoder.py`: same pooled CMU+HMOG `(16,9)` windows, normalization,
  masked-MSE recon objective, `fit_calibration` robust-z anchor, registry/S3 export.
  Architecture: `Input(16,9) → Masking → Normalization → [MultiHeadAttention + FFN]×2 (pos-enc,
  residual/LayerNorm) → reconstruct (16,9)` as a Transformer-encoder **autoencoder** (same
  recon-error → calibration → Behavior_Score contract as the AE). Keras → ONNX via `export_onnx`.
  Register as `transformer_encoder` (stage `staging`).
- [x] **A2. Unified benchmark harness** — `training/benchmark.py` (new). Runs **both tracks** on shared
  holdouts. For each candidate compute: **Accuracy, Precision, Recall, F1, FAR, FRR, EER, ROC-AUC, PR-AUC,
  + inference latency (p50/p95, single-row & batched)**. Binary metrics taken at the EER operating point;
  reuse `_eer` from `train_isolation_forest`. Unsupervised scorers (IF/OCSVM/AE/Transformer) use their
  anomaly/recon score; supervised models use predicted probability. Keep a per-track leaderboard sorted by
  the track's primary metric (biometric: EER↓ / ROC-AUC↑; fraud: PR-AUC↑ / recall@fixed-FPR).
- [x] **A3. Evaluation report** — emit machine-readable `training/benchmark_report.json` **and** a
  presentation-ready `MODEL_EVALUATION.md`: per-track comparison tables, ROC + PR curve PNGs
  (`training/reports/`), a latency-vs-accuracy trade-off note, and a clear **recommendation per track**
  (e.g. AE/Transformer for behavior, XGBoost/LightGBM for fraud) with the **rationale** for the deck.
  Add `pytest` coverage in `training/tests/test_benchmark.py` (metric correctness on a tiny synthetic set).
- [x] **A4. Present & HARD STOP** — approved 2026-06-27; score orientation bugs fixed; production stack confirmed — run the harness, surface the comparison tables + ROC/PR charts +
  recommendation-with-justification, then **pause and wait for explicit approval**. No model integration,
  no promotion, and no Phase B–F work until approved.

**Dependencies:** add `lightgbm` (and `tensorflow`/`tf2onnx` already present) to `training/requirements.txt`;
`scikit-learn` (RF, OCSVM, LogReg) and `xgboost` are already available.

**Verify:** `python -m training.train_transformer` → `python -m training.benchmark`; `MODEL_EVALUATION.md`
shows both tracks with all metric columns across all candidates + ROC/PR charts + recommendation;
`pytest training/` green.

---

## PHASE B — Continuous Monitoring + Device Trust + Adaptive Pre-UPI-PIN

- [x] **B1. Device Trust Engine** ✅ — `gateway/app/scoring/device_trust.py` created;
  computes `device_trust ∈ [0,100]` + class **trusted/known/new/suspicious** from
  `is_rooted/is_emulator`, `is_new_device`, geo velocity (impossible-travel check), biometric
  binding. Wired into `feature_reader.read_bundle()`: Redis cache hit → use cached value; cache
  miss → `device_trust.compute()` + `persist()` inline (two tiny SETs, only on first encounter).
  17 unit tests green (`tests/test_device_trust.py`).
- [x] **B2. Continuous mid-session ingest** ✅ — Android `DashboardActivity` starts a 30 s
  `CoroutineScope` ingest job in `onResume()` / cancels in `onPause()`; `action="verify"` triggers
  biometric `AlertDialog`; `reauth=true` (very_high, session terminated) navigates to Login.
  Web: `useSessionIngest.ts` hook + `ingestBehavior()` in `api.ts`; Dashboard mounts hook and shows
  `ShieldAlert` banner on `action="verify"`; `sessionTerminated` redirects to `/login`.
- [x] **B3. Adaptive pre-UPI-PIN re-auth** ✅ — new Android `UpiPinActivity`; `TransferActivity`
  intercepts UPI submit → `upiPinLauncher`; `UpiPinActivity` calls `ingest()` → branches by band:
  **low → PIN immediately; medium → biometric → PIN; high → OTP dialog → biometric → PIN;
  very_high → block dialog** (gateway already opened SOC case). PIN submission calls `scorePayment()`
  + `verifyPaymentStepUp()`; RESULT_OK on allow → `TransferSuccessActivity`.
  Registered in `AndroidManifest.xml`. Layout: `activity_upi_pin.xml`.
- [x] **B4. Dynamic personalized scoring** ✅ — device-trust budget constants externalized from
  `device_trust.py` to `policy.py["device_trust"]`; `compute()` accepts optional `budgets` dict
  (fallback to `_BUDGET_DEFAULTS`); all three hot-path callers (`auth_flow`, `behavior_flow`,
  `payment_flow`) pass `policy.get("device_trust")`. Per-user `user:{uid}:risk_baseline` EMA
  (α=0.1, 90-day TTL) written by `behavior_flow.ingest()` on clean low-risk sessions; loaded by
  `feature_reader` into `FeatureBundle.risk_baseline`; `stack.map_band_adaptive()` uses it when
  ≥20 samples available (thresholds clamped to ±30% of global policy). 21 device-trust tests green.

**Verify:** idle on Android dashboard → ingest fires; UPI transfer at each band shows correct factor
ladder; critical blocks + SOC case appears.

---

## PHASE C — Authentication (real OTP, signup, trusted devices, sessions) ✅ COMPLETE

- [x] **C1. Real OTP via SMTP** — `gateway/app/services/otp.py` (new): `generate_otp`/`verify_otp` with
  Redis TTL. SMTP env config in `config.py`. Replaced `_DEMO_OTP_CODE = "123456"` in `adaptive_auth.py`.
- [x] **C2. Signup flow** — `web-app/src/pages/Signup.tsx` with Heritage Trust Bank theme, DPDP consent,
  password strength indicator; route added; Login page links to it.
- [x] **C3. Trusted-device/session/login-history write endpoints** — `routers/banking.py` +
  `services/banking.py`: `POST /banking/devices/{id}/trust`, `DELETE /banking/sessions/{id}` (revoke via
  `security.revoke` denylist), `GET /banking/login-history`. `web-app/src/pages/Security.tsx` wired up
  with Trust/Revoke buttons. Android: `BiometricEnrollmentManager.kt` generates RSA-2048 KeyStore keypair,
  signs enrollment nonce, binds to server via `/mobile/device/enroll-challenge` + `/mobile/device/bind-biometric`.
  Alembic migration adds `public_key TEXT` to `user_devices`.

---

## PHASE D — SOC Dashboard build-out (analyst-only internals) ✅ COMPLETE

- [x] **D1. Role-gate risk internals** — `require_role("admin","analyst")` / `require_role("admin")`
  FastAPI dependencies applied to all admin routes.
- [x] **D2. Auth timeline** — `GET /admin/users/{id}/auth-timeline`; `AuthTimeline.tsx` in bank-dashboard.
- [x] **D3. Device intelligence** — `GET /admin/devices/{id}` (trust class, geo trend); `DeviceIntelligence.tsx`.
- [x] **D4. SHAP** — `gateway/app/scoring/shap_explainer.py` (TreeExplainer on XGBoost, off hot path);
  `POST /admin/explain/{scoreId}`; `SHAPExplainer.tsx` horizontal bar chart.
- [x] **D5. LLM investigation assistant** — `services/investigation_llm.py` (DeterministicStubProvider +
  ClaudeProvider when `LLM_PROVIDER=claude`); `POST /admin/cases/{id}/investigate`; `InvestigationAssistant.tsx`.
- [x] **D6. HITL + model monitoring** — case label writes to S3 `labels/{status}/{case_id}.json`; HITL
  already wired in `case_mgmt._write_label()`.

---

## PHASE E — UX redesign (Android + Web) ✅ COMPLETE

- [x] **E1.** Heritage Trust Bank theme applied across web + Android; Signup.tsx created.
- [x] **E2.** Security Center: Trust buttons on devices, Revoke buttons on sessions; login history section.
  Android `SecurityCenterActivity` + `BankingViews` updated with action callbacks; `CogniGuardClient`
  has `trustDevice()`, `revokeSession()`, `getLoginHistory()`.
- [x] **E3.** No risk internals to end users: `TrustBadge.tsx` → qualitative labels only ("Verified"/
  "Active"/"Calibrating"), "Security Status" header not "CogniGuard Risk Engine"; `RiskBadge.tsx` → band
  label only, no raw numeric score; `Payment.tsx` raw `action:` field removed.

---

## PHASE F — ML productionization (after Phase A selection) ✅ COMPLETE

- [x] **F1.** `training/promote.py` updated: `promote_from_benchmark()` reads `benchmark_report.json`
  winners and promotes to production; CLI supports `from-benchmark`, `promote`, `rollback` subcommands.
- [x] **F2.** Feature store formalized: `feature_reader.snapshot_features()` writes `FeatureBundle` JSON
  to S3 `features/{date}/{session_id}.json` as a background task on clean low-risk sessions.
- [x] **F3.** Drift + feedback-driven retraining: `training/drift_monitor.py` already in place (PSI/KS on
  risk_scores table; triggers IF/XGBoost staging challengers on breach). New
  `gateway/app/scoring/drift_monitor.py` adds S3-snapshot feature drift check (PSI/KS on F2 snapshots,
  Kafka alert, label scanning).
- [x] **F4. AE Embedding Store** — `build_model()` now returns `(training_model, serving_model, encoder_model)`;
  `encoder_model` exports to `lstm_encoder.onnx` registered as `lstm_encoder` in model_registry.
  `gateway/app/scoring/embedding_store.py`: encodes sequences → 16-dim embedding → EMA centroid at
  `behavior:{uid}:embedding` → cosine similarity stored at `behavior:{uid}:embedding_sim`.
  `feature_reader.read_bundle()` reads `embedding_sim`; `stack.py` blends it (weight=0.25) with robust-z
  `behavior_match_score` in Trust Score. F5/F6 deferred.
- [ ] **F5. Embedding Enhancements** *(gate: EER ≤ 0.25 on AEEmbedding benchmark row)* — deferred.
- [ ] **F6. Contrastive Fine-Tuning** *(gate: EER > 0.25)* — deferred.

---

## Cross-cutting constraints (CLAUDE.md — must hold)
- Inference reads **Redis only**; Postgres writes off the hot path.
- Bands/thresholds/amplifiers/weights from **active policy**, never hardcoded.
- Cold-start/medium → **verify**, never block genuine users.
- Every verify/block persists reason codes + `model_version` + latency; `degraded_mode` on fallback.
- Telemetry nonce/HMAC verified & consumed; quarantine step-up telemetry.
- Latency: login p95 < 300 ms, payment p95 < 500 ms.
- Tests (`pytest` + `vitest`) green; `ruff`/`black` + TS `strict`/`eslint` clean.

## Build order
**A (pause for review)** → B → C → D → E → F. A is the gate; F depends on A's selection.
