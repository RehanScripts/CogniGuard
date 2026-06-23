# Phase 28 — Thin Read-Only Banking Endpoints (Authorized Exception)

## Goal

The customer banking screens (Accounts, Transactions, Beneficiaries, Profile, Security
Settings) had no existing read API — only the `Account`/`Transaction`/`Beneficiary`/
`User` ORM models with zero routes over them. This is the **one user-approved exception**
to "don't add backend functionality": thin, read-only `GET` endpoints, PII-masked, no new
tables/writes/scoring/business logic. Phase 29/30 (web-app + Android redesign) consume
these directly.

## What changed

1. **`utils/mask.py`** (new)
   - `mask_account_number`/`mask_email`/`mask_phone` — the first PII-masking utility in
     the codebase. No prior helper existed; previously nothing returned raw PII to a
     client at all (admin endpoints return ids, not account numbers/emails/phones).

2. **`schemas/banking.py`** (new)
   - `ProfileOut`, `AccountOut`, `TransactionOut`, `BeneficiaryOut`,
     `TrustedDeviceOut`/`ActiveSessionOut`/`SecuritySettingsOut`.
   - Deliberately carries **no** risk/trust fields (`transaction_risk_score`, `decision`,
     `decision_reason`, device `trust_score`) — unlike Phase 27's wire contracts (which
     inherited trust fields from a pre-existing precedent), these schemas are brand new,
     so the customer/SOC split is enforced from the first commit rather than deferred to
     Phase 29/30's UI-level stripping.

3. **`services/banking.py`** (new)
   - `get_profile`, `list_accounts`, `list_transactions`, `list_beneficiaries`,
     `get_security_settings` — thin SQLAlchemy 2.x `select()`/`execute()` queries scoped
     to the authenticated user, masking PII before constructing response objects.
   - `list_transactions` left-joins `Beneficiary` for a display name/masked account on
     each row. `list_beneficiaries` joins `UserBeneficiary` → `Beneficiary`.
     `get_security_settings` joins `UserDevice` → `Device` (trusted devices) and
     `Session` → `Device` (active sessions, `status == "active"` only) — no numeric
     trust score surfaced, just an `is_trusted` boolean and a human label.

4. **`routers/banking.py`** (new)
   - `GET /profile`, `/accounts`, `/transactions`, `/beneficiaries`,
     `/security-settings` — all behind `deps.get_current_user` (the same JWT+session
     dependency `payment.py`/`auth.py` already use). No new auth mechanism.

5. **`main.py`**
   - Mounted `banking.router` at `/api/v1/banking`.

6. **Verified, not changed:** `payment_flow.py` already persists a `Transaction` row
   with a correct status label (`status_map = {"allow": "allowed", "verify": "verified",
   "block": "blocked"}`) on every decision branch — the plan's stated verification
   concern for this phase required no code change.

## Files changed

- `gateway/app/utils/mask.py` (new)
- `gateway/app/schemas/banking.py` (new)
- `gateway/app/services/banking.py` (new)
- `gateway/app/routers/banking.py` (new)
- `gateway/app/main.py`
- `gateway/tests/test_banking.py` (new)
- `PROGRESS.md`
- `phases/PHASE_28_banking_endpoints.md` (this file)

## Verification

- `docker compose restart gateway` (uvicorn has no `--reload` — see PROGRESS.md gotcha),
  then `docker compose exec gateway python -m pytest -q tests/test_banking.py` →
  **6 passed**.
- Full suite: `docker compose exec gateway python -m pytest -q` → **191 passed, 1
  skipped** (185 pre-existing + 6 new banking tests).
- `ruff check` + `black --check` clean on all new/changed files.
- Live-style coverage in `test_banking.py` against the real running app (register →
  consent → login → bearer token), asserting:
  - `/profile` returns `customer_ref`/`account_status` and never a raw `email`/`phone`
    key (only the `masked_*` aliases exist in the schema at all).
  - `/accounts` returns the seed account (`balance: 100000.0`) with
    `masked_account_number` starting `X...` and ending in the real last 4 digits; no
    `account_number` key present.
  - `/transactions` and `/security-settings` never carry `transaction_risk_score`,
    `decision_reason`, `decision`, or a device `trust_score`.
  - All five endpoints 401/403 without a bearer token.
