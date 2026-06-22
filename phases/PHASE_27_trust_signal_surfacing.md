# Phase 27 — Surface & Persist Already-Computed Trust Signals

## Goal

Continuous re-scoring (`/behavior/ingest`) returns the same trust fields `/auth/login`
and `/payment/score` already did; the AE/IF provenance (`behavior_score_source`) is
visible everywhere a trust field is, not just internally logged; and both are persisted
on the `risk_scores` row so the SOC dashboard's history/case views (Phase 31) have real
data to render. **No new calculation anywhere** — every field added here already existed
on `ScoreResult` (`gateway/app/scoring/stack.py`); this phase only plumbs it through to
responses, the Kafka `risk_scores` topic, and Postgres.

## What changed

1. **`schemas/decision.py`**
   - `BehaviorIngestResponse` gained `trust_score`, `behavior_match_score`,
     `behavior_score_source`, `device_trust` (previously only `risk_score`/`risk_band`).
   - `DecisionResponse` (used by `/auth/login` and, via `PaymentScoreResponse`,
     `/payment/score`) already had `trust_score`/`behavior_match_score`/`device_trust`
     from Phase 20-22 but was missing `behavior_score_source` — added for parity across
     all three entity flows.

2. **`services/behavior_flow.py`, `auth_flow.py`, `payment_flow.py`**
   - Each flow's response construction now passes `trust_score`, `behavior_match_score`,
     `behavior_score_source` (and, where missing, `device_trust=result.device_score`)
     from the already-computed `ScoreResult` into its response object.
     `payment_flow.py`'s `PaymentScoreResponse` previously didn't surface any trust
     fields at all (a pre-existing gap vs. `auth_flow.py`) — brought to parity here.
   - Each flow's `event_producer.emit_risk_score(...)` background task now also passes
     `behavior_score_source` (it already passed `trust_score`/`behavior_match_score`).

3. **`schemas/topics.py` / `services/event_producer.py`**
   - `RiskScoreEvent` gained `behavior_score_source: str | None`.
   - `build_risk_score_event`/`emit_risk_score` accept and forward it. `broadcaster.py`
     forwards the raw Kafka message bytes unchanged to the SOC WebSocket feed, so no
     change was needed there for the new field to reach `bank-dashboard`.

4. **`models/scoring.py` + migration `7127f86380d8`**
   - `RiskScore` gained three nullable columns: `trust_score Numeric(5,2)`,
     `behavior_match_score Numeric(5,2)`, `behavior_score_source String(16)` — same
     scale/type convention as the existing `behavior_score`/`device_score` columns.
   - `alembic revision --autogenerate` detected exactly these three columns (no other
     drift), confirming the models and live schema were otherwise in sync.

5. **`services/audit.py`**
   - `persist_risk_score` now copies `trust_score`/`behavior_match_score`/
     `behavior_score_source` from `ScoreResult` onto the new columns.

6. **`schemas/admin.py` / `routers/admin.py`**
   - `EventOut` gained the same three fields; `_event_out()` populates them from the
     persisted `RiskScore` row, so `GET /admin/events` (the SOC dashboard's history feed)
     carries them too.

## Files changed

- `gateway/app/schemas/decision.py`
- `gateway/app/schemas/topics.py`
- `gateway/app/schemas/admin.py`
- `gateway/app/services/behavior_flow.py`
- `gateway/app/services/auth_flow.py`
- `gateway/app/services/payment_flow.py`
- `gateway/app/services/event_producer.py`
- `gateway/app/services/audit.py`
- `gateway/app/models/scoring.py`
- `gateway/app/routers/admin.py`
- `gateway/alembic/versions/7127f86380d8_phase_27_persist_trust_score_behavior_.py` (new)
- `PROGRESS.md`
- `phases/PHASE_27_trust_signal_surfacing.md` (this file)

## Verification (actually run against this branch, not just described)

- `alembic revision --autogenerate` detected only the 3 intended new columns; reviewed
  the generated migration unedited; `alembic upgrade head` applied cleanly.
- `docker compose exec gateway python -m pytest -q` → **185 passed, 1 skipped** (no
  scoring/behavior change, plumbing only) — run both before and after the live restart
  below, identical result.
- Live round-trip against the running stack (`docker compose restart gateway` was
  required first — see the new `uvicorn --reload` gotcha in `PROGRESS.md` — code edits
  on a long-lived dev stack don't take effect until the process restarts):
  - `POST /api/v1/auth/login` with a freshly-signed genuine-persona payload →
    `200 allow`, `risk_band: low`, and for the first time
    `"behavior_score_source": "if"` alongside `trust_score`/`device_trust`/`enrollment`
    in the same response (`behavior_match_score` correctly stays `null` — this user's
    enrollment isn't complete yet, an existing cold-start gate, not a regression).
  - Queried `risk_scores` directly via `SessionLocal` inside the gateway container:
    the row from that login carries `trust_score=67.30`, `behavior_score_source='if'`
    (rows scored before the restart correctly show `NULL` for all three — they were
    persisted by the pre-restart process running the old code, not a bug).
  - `GET /admin/events?limit=3` (with `X-Admin-Token`) → the same three fields appear
    in the JSON response, confirming the full path from scoring → Postgres → admin API.

## Note on scope vs. CLAUDE.md's customer/SOC split

`DecisionResponse`/`PaymentScoreResponse` (the schemas the web-app/Android clients
literally receive over the wire) now carry `behavior_score_source` alongside the trust
fields Phase 20-22 already put there. This mirrors the existing precedent (login already
returned `trust_score` before this phase) and is intentional: Phase 29/30 are where the
client-side rendering of any of these fields gets stripped from the *UI*, not where the
wire contract stops carrying them. No telemetry is customer-visible today only because
the current web-app/Android UIs don't render these fields yet.
