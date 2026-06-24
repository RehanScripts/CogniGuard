# CogniGuard Prototype Testing Plan — Web, Dashboard & Android-on-Phone

## Context

Development through Phase 30 is done; we now want to manually exercise the prototype
end-to-end. Three surfaces talk to the **same gateway** (`http://localhost:8000`):

- **web-app** (customer Internet Banking demo) — `:5173`
- **bank-dashboard** (fraud-ops / SOC) — `:5174`
- **android** native capture-sdk demo app — runs on a physical phone over USB

Machine check results: Docker + Compose ✅, `.env` ✅, trained `model.tflite` present in
`models/` ✅. **Missing:** Android SDK + `adb`; system JDK is 21 while the project (AGP
8.1.4) targets JDK 17. Decision: install **Android Studio** (bundles SDK, platform-tools/adb,
JDK 17, USB device deploy) — this is the only setup gap and it sidesteps the Java-version issue.

Goal: a repeatable runbook to demo the genuine happy path, ATO-at-login (impostor),
coercion-at-payment, and the SOC live feed — from the browser and from a real phone.

A follow-on goal (Part C): after testing, redesign the **web-app** and **Android app** UI/UX
with **Google Stitch** so both look like a polished Central Bank of India product. Stitch
(stitch.withgoogle.com, Google Labs) turns text prompts / reference images into responsive
mobile + web UIs and exports HTML/CSS or Figma. Part C gives a CBI theme spec and
copy-pasteable, screen-by-screen Stitch prompts.

---

## Part A — Backend + Web stack (ready today, no install)

One command brings up all infra + gateway + both UIs (migrations, demo seed, AE
calibration, fraud fixtures, Kafka topics, and the Flink job all auto-run on startup):

```bash
cd /home/ojasbhalerao/Documents/prj/x
docker compose --profile ui up --build
```

Wait ~2–3 min, then sanity-check before testing:

```bash
curl -s http://localhost:8000/health | jq .        # expect status ok
# Flink UI:    http://localhost:8081
# Swagger:     http://localhost:8000/docs
```

| Surface | URL | Login |
|---|---|---|
| Web-app (customer) | http://localhost:5173 | `genuine` / `Passw0rd!` |
| Bank-dashboard (SOC) | http://localhost:5174 | `admin@cogniguard.dev` / `Passw0rd!` (or `analyst@…`) |

### Web-app flows to verify
1. **Genuine happy path** — login as `genuine` / `Passw0rd!`, type at a normal rhythm →
   expect `allow`, land on Dashboard.
2. **Step-up** — when a login returns `verify`, the app routes to `/step-up`; OTP is
   `123456` (dev `demo_otp`).
3. **Coercion / APP-fraud** — Dashboard → Transfer → new beneficiary `scammer@upi`, amount
   ≥ ₹2000 → expect `NEW_BENEF_HIGHVAL` amplifier + cooling / manual-amount / reconfirm.
4. **Impostor / ATO** — the web UI has no impostor toggle; reproduce via the freshly-signed
   fixture (regenerated each container start, ~short TTL):
   ```bash
   curl -s -X POST http://localhost:8000/api/v1/auth/login \
     -H 'Content-Type: application/json' \
     -d @gateway/tests/fixtures/impostor_erratic.json | jq .   # expect action: verify, high band
   ```

### Bank-dashboard flows to verify
- **Live** feed updates (WebSocket from Kafka via Redis pub/sub) as you drive web-app/phone
  actions; **UserDetail** drill-down; **Policy**, **Cases**, **Governance** panels render.

---

## Part B — Android app on the physical phone (USB)

### B1. Install toolchain (one-time)
1. Install **Android Studio** (includes SDK manager, platform-tools/adb, bundled JDK 17).
2. In SDK Manager install: **Android SDK Platform 34** (compileSdk/targetSdk) + **Platform-Tools**.
3. Confirm `adb` is on PATH (Studio installs it under `~/Android/Sdk/platform-tools/`):
   ```bash
   ~/Android/Sdk/platform-tools/adb version
   ```

### B2. Provide the on-device model (gitignored, copy manually)
```bash
cd /home/ojasbhalerao/Documents/prj/x/android
mkdir -p capture-sdk/src/main/assets
cp ../models/lstm_autoencoder_tflite/lstm_autoencoder@2026-06-21/model.tflite \
   capture-sdk/src/main/assets/model.tflite
```
(Use the newest version dir; `2026-06-21` is latest present.)

### B3. Prepare the phone
- Settings → enable **Developer options** → turn on **USB debugging**.
- Plug in via USB, accept the "Allow USB debugging" RSA prompt.
- Verify: `adb devices` lists the device as `device` (not `unauthorized`).

### B4. Point the app at the laptop gateway
The app's debug build already uses `API_BASE = "http://127.0.0.1:8000"` and
`usesCleartextTraffic="true"`. For a USB device, tunnel that loopback to the laptop:
```bash
adb reverse tcp:8000 tcp:8000     # re-run after each reconnect / adb restart
```
No code change needed. (`SIGNING_SECRET` already mirrors the gateway dev `JWT_SECRET`.)

**Known fragility**: this tunnel silently drops on USB disconnect, device sleep, or an
`adb` daemon restart — the app then shows "Could not reach CogniGuard" on every screen
that calls the gateway, even though the gateway itself is healthy. There's no in-app
retry/reconnect logic (out of scope for a demo prototype). For judging day, run this
watcher in the background for the whole demo instead of relying on a single one-shot
call:
```bash
while true; do
  adb reverse --list 2>/dev/null | grep -q "tcp:8000 tcp:8000" || adb reverse tcp:8000 tcp:8000
  sleep 5
done
```

### B5. Build, install, launch
Easiest via Android Studio: open `/home/ojasbhalerao/Documents/prj/x/android`, let Gradle
sync, select the device, click **Run** on the `:app` module.

CLI equivalent (uses Studio's JDK 17 — set `JAVA_HOME` to the bundled JBR if needed):
```bash
cd /home/ojasbhalerao/Documents/prj/x/android
./gradlew :app:assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.cogniguard.demoapp/.LoginActivity
```

### B6. Android flows to verify
- **Register / consent / login** (`LoginActivity`) with on-device keystroke+touch+motion
  capture → TFLite autoencoder computes reconstruction error on-device; only the error is
  sent. Expect `allow` for genuine-style input; watch it appear in the **bank-dashboard Live**
  feed (channel `mobile`).
- **Transfer** (`TransferActivity`) → `/api/v1/payment/score`; try a new high-value payee to
  trigger the coercion/amplifier path; biometric step-up (`USE_BIOMETRIC`) if challenged.

---

## Part C — UI/UX redesign with Google Stitch (CBI theme)

Do this **after** Part A/B testing, so the redesign targets the real screens we've exercised.
Stitch best practice (from Google's prompt guide): **start with one simple prompt, then refine
screen-by-screen with one or two changes per prompt** — long all-in-one prompts (>5k chars)
drop components, and mixing layout + component changes makes Stitch rebuild and break the
layout. So: (1) establish the theme once, (2) generate each screen, (3) make small targeted edits.

### C0. Central Bank of India theme spec (paste into the first prompt of every project)
- **Brand palette:** primary blue **Poseidon `#176FC1`**, accent/alert red **Atomic Raspberry
  `#CE0F3E`**, base **White `#FFFFFF`**; neutrals: light grey `#F4F6F8` surfaces, `#1A2330`
  text. Red is reserved for alerts/CTAs-of-consequence, blue for primary actions/headers.
- **Feel:** trustworthy, professional, "heritage bank since 1911" + modern fintech; generous
  white space, clear hierarchy, AA-contrast, rounded-medium corners, soft shadows.
- **Type:** clean professional sans-serif (e.g. Inter / Public Sans); large readable numerals
  for balances and amounts.
- **Iconography:** simple line icons; a small bank/banyan-tree style logo lockup top-left.

> Tip: also upload the CBI logo PNG + a screenshot of centralbankofindia.co.in as
> **reference images** so Stitch matches the visual style, not just the colors.

### C1. Web-app (desktop + responsive) — generate these screens
Foundation prompt (run first, Experimental/Gemini-2.5-Pro mode):
> "Design a responsive web app for an Internet Banking portal for an Indian retail bank.
> Theme: primary blue #176FC1, accent red #CE0F3E, white background, light-grey #F4F6F8
> cards, professional sans-serif, trustworthy heritage-bank feel with a modern fintech polish.
> Top navigation bar in blue with the bank logo on the left. Generate a clean, accessible
> design system I'll reuse across screens."

Then, one screen per prompt (refine after each):
1. **Login** — "Login screen: centered card on a subtle blue gradient, username + password
   fields, primary blue 'Log in' button, small 'consent to behavioural security' checkbox with
   a learn-more link, bank logo and tagline above the card."
2. **Step-up / OTP** — "Step-up verification screen: heading 'Verify it's you', a 6-digit OTP
   input, a countdown 'resend code' link, primary blue 'Verify' button; a small reassuring note
   that this extra check was triggered by our risk engine."
3. **Dashboard** — "Banking dashboard: top blue nav, a greeting with masked profile, account
   summary cards (balance in large numerals, account number masked, status chip), quick-action
   buttons (Transfer, Transactions, Security), and a recent-activity list."
4. **Transfer** — "Fund transfer screen: beneficiary selector (with an 'add new payee' option),
   amount field with large numerals, transfer-type segmented control (IMPS / NEFT / RTGS /
   UPI), and a prominent blue 'Continue' button. Show a non-blocking amber 'cooling-period /
   confirm this is you' info banner state for new high-value payees."
5. **Transactions** — "Transaction history: filterable table/list with date, payee, amount
   (debits in red, credits in green), status chip, and a risk badge column."
6. **Security** — "Security settings: trusted-devices list, active-sessions list with a
   'revoke' action, and behavioural-consent toggle; calm, reassuring layout."

### C2. Android app (mobile) — generate these screens
Foundation prompt (select **Mobile** target):
> "Design an Android mobile banking app for an Indian retail bank. Same theme: blue #176FC1,
> red #CE0F3E accents, white, professional sans-serif, Material-style components, bottom or
> top app bar with the bank logo, thumb-friendly large tap targets, heritage-bank-but-modern."

Then per screen:
1. **Login / register / consent** — "Mobile login screen: logo, username + password,
   biometric-login affordance, and a first-run behavioural-security consent sheet (Grant /
   Decline) explaining on-device behaviour capture in plain language."
2. **Home** — "Mobile banking home: account balance card in large numerals, quick actions
   (Transfer, History), and a recent-transactions list."
3. **Transfer** — "Mobile transfer screen: payee picker, large amount keypad/field, transfer
   type chips (IMPS/NEFT/RTGS/UPI), and a blue 'Send' button; include a step-up state that
   prompts fingerprint/biometric confirmation for risky transfers."
4. **Step-up biometric** — "Biometric verification prompt screen: 'Confirm with fingerprint'
   with fallback OTP entry, reassuring copy that an extra check was triggered."

### C3. Hand-off back to code
- Export each screen as **HTML/CSS** or paste into **Figma**; use it as the visual reference.
- Re-skin the real apps to match: web-app is React + **Tailwind** (`web-app/src/pages/*`,
  `bank-dashboard/src/pages/*`) — translate Stitch's colors/spacing into the existing Tailwind
  classes; Android is Kotlin views under `android/app/src/main/` — re-skin layouts/themes.
  Keep all existing API calls and behaviour-capture wiring intact; this is a visual re-skin only.
- (Optional) also run the **bank-dashboard** through Stitch with the same theme for a
  consistent SOC look (data-dense tables, Recharts-style panels, live-feed list).

## Verification checklist (end-to-end)
- [ ] `docker compose --profile ui up --build` → `/health` ok, Flink job running (`:8081`).
- [ ] Web-app: genuine `allow`; impostor fixture → `verify`/high; coercion transfer fires amplifier + cooling.
- [ ] Dashboard: Live feed reflects each action; reason codes visible on verify/block.
- [ ] `adb devices` shows the phone; `adb reverse tcp:8000 tcp:8000` set.
- [ ] App launches, logs in, and its `mobile`-channel events show up in the dashboard Live feed.
- [ ] (Optional) `./gradlew :capture-sdk:connectedAndroidTest` — TFLite-vs-ONNX parity test passes (skips gracefully only if model asset missing).

## Notes / gotchas
- Impostor & coercion **fixtures regenerate on each gateway start** with a short nonce TTL —
  use them promptly or restart the gateway to refresh.
- Re-run `adb reverse` after unplug/replug or `adb kill-server`.
- If a CLI Gradle build errors on Java 21, point `JAVA_HOME` at Android Studio's bundled JBR
  (`<studio>/jbr`) — building from inside Studio avoids this entirely.
- This plan changes **no source code**; the only file additions are the local `model.tflite`
  asset (gitignored) and toolchain installs.

---

## Part D — Phase 31: CBI reskin + Android banking screens (in progress, branch `phase-31-cbi-theme-reskin`)

Status as of 2026-06-23: web-app, bank-dashboard, and the Android demo app have all been
re-themed to the Central Bank of India palette (`#176FC1` / `#CE0F3E`, Inter typography) per
the Part C spec above, and the Android app has grown from Login/Transfer-only into a fuller
banking experience. Pushed to `origin/phase-31-cbi-theme-reskin` (not yet merged to `main`).

### D1. Done
- **Theme**: `android/app/src/main/res/values/themes.xml` parent switched to
  `Theme.MaterialComponents.Light.NoActionBar` (enables `MaterialCardView`); `colors.xml`
  extended with light/muted/divider/success variants; new oval badge/status-dot/success-circle
  drawables under `res/drawable/`.
- **Banking data plumbing**: `CogniGuardClient.kt` (capture-sdk) gained `getProfile`,
  `listAccounts`, `listTransactions`, `listBeneficiaries`, `getSecuritySettings` — mirrors
  `web-app/src/api.ts`'s existing `/api/v1/banking/*` calls 1:1, refactored into
  `requestRaw`/`request` (object)/`requestArray` (array) to handle both response shapes.
- **New screens** (layout + `Activity` written): `DashboardActivity` (welcome/balance card,
  quick actions, recent transactions), `SecurityCenterActivity` (qualitative-only protection
  status — no raw scores/model names, per the customer/SOC data split), `TransferSuccessActivity`
  (client-generated display reference + real amount/beneficiary/timestamp), `TransactionHistoryActivity`
  (full transaction + beneficiary lists). Shared row/badge builders in `BankingViews.kt`.
- **Web-app**: extracted a shared `AppHeader.tsx`; reskinned `Dashboard`/`Login`/`Payment`/
  `Security`/`StepUp`/`Transactions`/`Transfer` pages and `CalibrationBanner`/`ChannelSwitcher`/
  `CoercionCheck`/`CoolingNotice` components + `tailwind.config.js`/`index.css`.
- **Bank-dashboard (SOC)**: reskinned `NavBar`/`BandDistribution`/`CaseDrawer`/
  `LatencyHistogram`/`QuarantineStatus` + `AdminLogin`/`Governance`/`Live`/`Policy` pages +
  `tailwind.config.js`/`index.css`.

### D1b. Build bug found + fixed during web-app verification
`web-app` failed to load with `Failed to resolve import "@cogniguard/behavior-sdk" from
"src/pages/Login.tsx"`. Root cause: the repo had no root-level `.dockerignore`, so
`web-app/Dockerfile`'s `COPY web-app/ ./` (which runs *after* its own `RUN npm install`)
copied the host's local `web-app/node_modules/` straight into the image, clobbering the
freshly-installed, correctly-linked `node_modules` with whatever was on the Windows host —
including a `file:../behavior-sdk` symlink baked with a literal `C:/vs code/...` target that
can't resolve inside the Linux container. Same risk existed for `behavior-sdk/`'s own
`COPY behavior-sdk/ ./` step. Fixed by adding a root `.dockerignore` (`**/node_modules`,
`**/dist`, `**/.git`) and rebuilding both `web-app` and `bank-dashboard`; confirmed
`@cogniguard/behavior-sdk` now resolves to `/behavior-sdk` inside the container and Vite
serves `Login.tsx` cleanly (200, no import-analysis error).

### D1c. Real bug found + fixed: web-app login/payment always failed nonce-fetch
After the `.dockerignore` fix, the web-app still showed "Could not reach CogniGuard" on
every login/payment attempt. Root cause was a genuine, pre-existing bug in
`behavior-sdk/src/payload.ts`'s `fetchNonce()`: it built the URL as
`${apiBase}/auth/nonce`, missing the `/api/v1` prefix every other endpoint in this SDK
uses (e.g. `index.ts`'s `${cfg.apiBase}/api/v1/behavior/ingest`). `VITE_API_BASE` is
`http://localhost:8000` (no prefix) per `.env.example`/`Implementation.md` since Phase
11, so `fetchNonce` always 404'd against the real `/api/v1/auth/nonce` route — meaning
`CogniGuard.collect()` (called by both `Login.tsx` and `Payment.tsx`) has been broken
since `behavior-sdk` was first written in Phase 10, silently caught by a bare `catch {}`
that shows the same generic error for every failure mode. Fixed the URL, updated the
matching test assertion in `payload.test.ts`, confirmed all 28 `behavior-sdk` vitest
cases pass, and rebuilt+recreated `web-app`/`bank-dashboard` with the corrected `dist/`.

### D1d. Real bug found + fixed: `devices.browser` column too narrow
After the nonce-URL fix, login still failed in-browser (still "Could not reach
CogniGuard") because the gateway then 500'd inserting into `devices`:
`psycopg.errors.StringDataRightTruncation: value too long for type character
varying(64)`. `devices.browser` (`gateway/app/models/device.py`) stored the raw
`device_info.ua` User-Agent string capped at `String(64)` — too narrow for real-world
UAs (the tester's Electron-based browser sent a ~140-char UA). Widened the column to
`Text` (matching `device_fingerprint`'s already-unbounded pattern for the same kind of
free-form client-supplied string), generated+applied an Alembic migration
(`7ecc6f2ac478_widen_devices_browser_to_text.py`), and confirmed via a replayed login
with that exact long UA that it now returns `action: allow` with a session token
instead of crashing. **Web-app login confirmed working end-to-end in-browser.**

### D1e. Real gap found + fixed: SOC Live feed rows weren't clickable
Tester reported Live-feed rows had no drill-down into `UserDetail`. Root cause: the
`RiskScoreEvent`/`DecisionEvent` Kafka topic payloads (`gateway/app/schemas/topics.py`)
never carried `user_id` -- only the REST `/admin/events` backfill's `EventOut` did (it
reads from Postgres, which has always had it). The live WS feed just relays the raw
Kafka bytes (`services/broadcaster.py`), so `EventTable`/`Live.tsx` had no `user_id` to
link with, even though `UserDetail`'s route (`/users/:userId`) already existed.
Threaded `user_id` end-to-end: added it to both topic schemas, `event_producer.py`'s
builders, and all 6 `emit_risk_score`/`emit_decision` call sites in
`auth_flow.py`/`payment_flow.py`/`behavior_flow.py` (the `user.user_id` already in
scope from the adjacent `audit.persist_scoring_outcome` calls); added `user_id` to
`bank-dashboard/src/ws.ts`'s `RiskScoreEvent`/`DecisionEvent` types and `EventRow`,
threaded it through `Live.tsx`'s/`UserDetail.tsx`'s row mappers, and made `EventTable`
rows clickable (`useNavigate` to `/users/{userId}`) when present. Updated
`EventTable.test.tsx` to wrap renders in `MemoryRouter`. All 18 bank-dashboard vitest
cases and all 7 gateway `test_event_producer.py` cases pass. Verified live: consumed
the raw `risk_scores` Kafka message for a fresh login and confirmed `"user_id": "..."`
is now present on the wire.

### D2. Remaining before this is demo-ready
1. **Wire navigation** — done:
   - `AndroidManifest.xml` registers `DashboardActivity`, `SecurityCenterActivity`,
     `TransferSuccessActivity`, `TransactionHistoryActivity` (`exported="false"`);
     `DashboardActivity` has `android:launchMode="singleTop"` so `TransferSuccessActivity`'s
     "Done" button (`Intent.FLAG_ACTIVITY_CLEAR_TOP`) reuses the existing instance.
   - `LoginActivity.kt` navigates to `DashboardActivity` on `action == "allow"` (both the
     initial decision and `submitStepUp()`'s success path), passing session token, username,
     and the `trust_score`/`behavior_match_score`/`device_trust` doubles.
   - `TransferActivity.kt` navigates to `TransferSuccessActivity` on a clean `allow` with no
     pending `txn_controls`.
   - **Follow-up fix (found during on-device walkthrough)**: the original wiring left
     `manual_amount`/`coercion_check` as dead-end static text with no way to clear them (the
     success-navigation condition could never become true once either fired). Added real
     `coercionPanel`/`manualAmountPanel` interactive panels to `activity_transfer.xml` +
     `TransferActivity.kt`, mirroring `CoercionCheck.tsx`/`ManualAmountEntry.tsx` — resolved
     entirely client-side against the already-received `scorePayment` response (no second
     network call), via `coercionAnswered`/`confirmedManualAmount` local state. Verified
     on-device: a manual-amount-flagged transfer now reaches `TransferSuccessActivity`.
2. **Build + on-device verification** — done. Login → Dashboard → Transfer (incl.
   manual-amount control) → Success → back to Dashboard (reused instance) → Security Center
   → Transaction History (shows the transfer) all walked end-to-end on the physical phone
   with no crashes (`adb logcat` clean of fatals/`AndroidRuntime` errors). Also hit, and
   fixed, an unrelated `adb reverse` tunnel-drop fragility (see Part B4 note above).
3. **Web-app verification (Part B in the original sense)**: re-run the Part A web flows
   (genuine happy path, step-up, coercion/amplifier, impostor fixture) against the reskinned
   pages — confirm no console errors, no failed API calls, no broken layout from the Tailwind
   changes.
4. **SOC dashboard verification**: Live feed, Policy, Cases, Governance, user drill-down —
   confirm WebSocket feed and Kafka-backed events still render correctly post-reskin.
5. **End-to-end pipeline spot-check**: one real signed `BehaviorPayload` (via `behavior-sdk`)
   through login → gateway → Flink → Redis → decision → Kafka → SOC Live feed, to catch any
   regression the reskin/refactor (e.g. the `CogniGuardClient` request-shape split) might have
   introduced.
6. **Final demo-readiness pass**: short writeup of remaining risks (by severity) and a
   go/no-go per surface (Backend, Android, Web, SOC, Risk Engine, UX) — no model retraining,
   threshold tuning, or architecture changes in scope for this pass, only stability/polish.

---

## Part E — Stitch screen → backend wiring contract

Read this **before** building screens in Stitch, and keep it open while wiring the
exported HTML/CSS or Figma back into `web-app/`/`android/`. It exists because Stitch
only knows what a prompt tells it — it can't know which endpoint a button calls, what
shape the response is, or that two "non-network" panels (coercion check, manual-amount
entry) are actually resolved **client-side with no second API call**. Field names below
are copy-pasted from the actual Pydantic/TS/Kotlin contracts — use them verbatim in the
re-skinned components, don't rename.

### E0. Two things that don't fit in a Stitch prompt
1. **Behavior capture is the product, not chrome.** Every screen that has a `login` or
   `transaction` form must run through the SDK's `collect()`/sign flow before the
   network call — never hand-build the `behavior` JSON block or skip it to "simplify"
   a Stitch-exported form. Web: `CogniGuard.init()` once, `CogniGuard.attach(formEl)` on
   mount, `await CogniGuard.collect("LOGIN" | "TRANSFER" | ...)` right before submit.
   Android: build an `UnsignedBehaviorPayload` from on-device capture, then
   `CogniGuardClient.signBehavior(partial)` (fetches a fresh nonce + HMAC-signs) before
   the `login`/`scorePayment` call.
2. **Most outcomes are HTTP 200.** `login`, `step-up/verify`, and `payment/score` encode
   the real outcome in the JSON body's `action` field (`allow`/`verify`/`block`), not the
   status code — branch on `body.action`, never on `response.ok` alone. The only non-200s
   that matter: `423` (IP/device lockout, login only), `400` (malformed/integrity-rejected
   payload), `404`/`401` (step-up: challenge not found / exhausted or wrong code).

### E1. Base setup (both surfaces)
- Base URL: web `VITE_API_BASE` (default `http://localhost:8000`); Android
  `API_BASE = "http://127.0.0.1:8000"` (tunneled via `adb reverse tcp:8000 tcp:8000`).
  **All paths are prefixed `/api/v1/...`** — a bare `/auth/nonce` 404s (this exact bug bit
  Phase 31, see Part D1c above).
- Auth header: `Authorization: Bearer <session_token>` on every banking/payment/behavior
  call. `session_token` comes from a successful `login` or `step-up/verify` response —
  store it (web: `sessionStorage`, key `cogniguard_session_token`; Android: in-memory /
  activity-result extra) and attach it to every subsequent call until logout.
- Centralize all calls in one place per surface — web already does this in
  `web-app/src/api.ts`; Android in `android/capture-sdk/.../net/CogniGuardClient.kt`.
  When re-skinning, **add new UI components against these files, never call
  `fetch`/`HttpURLConnection` directly from a screen/Activity.**

### E2. Web-app screens — endpoint, request, response → UI mapping

| Screen (`web-app/src/pages/`) | Fires on | Endpoint | Request body | Response fields that drive UI |
|---|---|---|---|---|
| **Login** | form submit | `POST /api/v1/auth/login` | `{username, password, behavior}` (behavior via `CogniGuard.collect("LOGIN")`) | `action`: `allow`→store `session_token`, go to Dashboard; `verify`→navigate to Step-up with `{challenge: step_up, requiredFactors: required_factors}`; `block`→show `hardening.action`/`retry_after_s` as the error banner. Also surface `enrollment` (→ "Security Profile Calibration N/10" banner) and `trust_score`/`behavior_match_score` (→ trust badge) when present. |
| **Step-up** (`/step-up`) | OTP form submit, or biometric "Simulate"/real-assertion button | `POST /api/v1/auth/step-up/verify` | `{challenge_id, otp_or_assertion}` (`challenge_id` came from Login's `step_up.challenge_id`; demo OTP is `123456`) | `action === "allow"` + `session_token` present → store token, go to Dashboard. Otherwise show "Incorrect code, try again." `404` = stale/unknown challenge, `401` = wrong code or attempts exhausted — route both back to Login. |
| **Dashboard** | on mount | `GET /api/v1/banking/profile`, `GET /api/v1/banking/accounts`, `GET /api/v1/banking/transactions?limit=N` (Bearer token) | — | Greeting/profile card ← `ProfileOut` (`full_name`, `masked_email`, `kyc_level`); balance cards ← `AccountOut[]` (`balance`, `masked_account_number`, `status`); recent-activity list ← `TransactionOut[]`. **No risk/score fields exist on this contract by design** (customer/SOC split) — don't add a risk badge here from imagination. |
| **Transfer** (hosts `Payment`) | on mount: starts `CogniGuard.startContinuous(token)` (background re-scoring, no UI to wire — it POSTs `/api/v1/behavior/ingest` itself); form submit: `CogniGuard.collect("TRANSFER")` → score | `POST /api/v1/payment/score` | `{amount, beneficiary_vpa (or beneficiary_id), transfer_type: "IMPS"\|"NEFT"\|"RTGS"\|"UPI", channel: "web", behavior}` | See **E5** below — `txn_controls` (`coercion_check`, `manual_amount`, `cooling_until`) gate three mutually-exclusive panels with **no further network call**; also show `risk_band`/`risk_score` via a badge and `amplifiers[]` (e.g. `NEW_BENEF_HIGHVAL`) as the reason the panel appeared. |
| **Transactions** | on mount | `GET /api/v1/banking/transactions?limit=N` | — | `TransactionOut[]`: date (`initiated_at`), payee (`beneficiary_name`), amount (debit styling — this contract has no separate credit/debit flag, treat all listed transfers as debits from this account), `status`, `transfer_type`. No "risk badge column" field exists server-side for the customer view — if a risk column is wanted, it has to come from the SOC dashboard's WS feed, not this endpoint. |
| **Security** | on mount | `GET /api/v1/banking/security-settings` | — | `SecuritySettingsOut.trusted_devices[]` (`label`, `is_trusted`, `last_used_at`) and `.active_sessions[]` (`device_label`, `location`, `started_at`). Consent toggle uses `POST /api/v1/auth/consent` with `{username, action: "GRANT"\|"WITHDRAW", consent_version}`. There is currently **no revoke-session endpoint** — a "Revoke" button has nothing to call yet; either omit it from the Stitch screen or flag it as a stub. |

### E3. Android screens — endpoint, request, response → UI mapping
Same contracts as E2 (the gateway doesn't distinguish web/Android beyond `channel` and
`behavior.source`), via `CogniGuardClient.kt`'s methods. Screens already exist
(`android/app/src/main/kotlin/com/cogniguard/demoapp/`) — re-skin layouts, keep the
`Activity` ↔ client-method wiring as-is.

| Activity | Client method(s) | Request | Response → UI |
|---|---|---|---|
| `LoginActivity` (login/register/consent) | `register(username, password)`, `setConsent(...)`, `login(username, password, behavior)` | same fields as web Login, `behavior.source = "mobile_edge"`, `behavior.derived_features`/`ae_recon_error` populated from the on-device TFLite autoencoder instead of raw `keystroke`/`mouse`/`touch` blocks | identical `action` branching to web; on `allow` it already passes `trust_score`/`behavior_match_score`/`device_trust` as Intent extras to `DashboardActivity`. On `verify`, present the step-up UI in-place (no separate Activity) and call `verifyStepUp`. |
| `DashboardActivity` | `getProfile`, `listAccounts`, `listTransactions` | — | same field mapping as web Dashboard. |
| `TransferActivity` | `scorePayment(token, amount, beneficiaryVpa, transferType, behavior)` | `channel` is hardcoded `"mobile"` inside the client | same `txn_controls` state machine as E5, resolved via `coercionPanel`/`manualAmountPanel` local view state in `activity_transfer.xml` — **do not** add a second network call when these fire. On clean `allow` with no pending `txn_controls`, navigates to `TransferSuccessActivity`. |
| `TransferSuccessActivity` | none (pure display) | — | renders the already-received response's amount/beneficiary/timestamp + a client-generated display reference; no extra fetch. |
| `SecurityCenterActivity` | `getSecuritySettings` | — | **qualitative-only** — per the customer/SOC split, do not surface raw scores or model names here even if you can see them elsewhere in the response; this Activity intentionally only derives a "Protected" / "Needs attention" style qualitative state. |
| `TransactionHistoryActivity` | `listTransactions`, `listBeneficiaries` | — | same mapping as web Transactions, plus a beneficiary list panel. |

### E4. Decision-response field glossary (appears in `login`, `step-up/verify`, `payment/score`, `behavior/ingest`)
This is the one schema (`DecisionResponse` / `PaymentScoreResponse`) every screen above
that touches risk decisions has to read from — Stitch should design states for each row,
not just the happy path:

| Field | Type | Drives |
|---|---|---|
| `action` | `"allow" \| "verify" \| "block"` | top-level navigation/branch — design all three as real states, not just `allow` |
| `risk_band` | `"low" \| "medium" \| "high" \| "very_high"` | badge color (`RiskBadge.tsx` pattern) — never invent a 5th band |
| `risk_score` | 0–100 float | numeric readout next to the badge |
| `reason_codes[]` | `{code, detail, sigma?}` | "why this happened" list/tooltip on verify/block |
| `amplifiers[]` | `{code, multiplier, detail}` | e.g. `NEW_BENEF_HIGHVAL` chip on the transfer-risk panel |
| `step_up` | `{challenge_type, assurance, challenge_id}` \| `null` | only present when `action === "verify"`; drives the Step-up screen's heading/instructions |
| `txn_controls` | see **E5** | only on the payment path |
| `hardening` | `{action: DELAY\|CAPTCHA\|LOCKOUT, scope, retry_after_s}` \| `null` | only on `block`; the retry-after copy on the error banner |
| `degraded_mode` | bool | a small "running in fallback mode" badge — don't hide this, it's a required demo state |
| `trust_score` / `behavior_match_score` / `device_trust` | 0–100 float \| `null` | `TrustBadge.tsx`-style qualitative chip; `null` is a valid cold-start state ("not yet calibrated"), design for it explicitly |
| `enrollment` | `{collected, required, complete, just_finalized}` \| `null` | "Security Profile Calibration N/10" banner (`CalibrationBanner.tsx`) |
| `integrity` | `"OK" \| "INTEGRITY_REJECT"` | should never reach the UI in normal use; if it does, treat like a generic error, not a risk band |

### E5. Client-side-only state machine — no backend round trip
`payment/score` returns **one** response that already encodes every control that might
fire; the three follow-up panels are resolved **entirely against that one response**,
gated by local booleans — there is no `POST /confirm-coercion` or `POST /manual-amount`
endpoint to design a call for:
1. `txn_controls.coercion_check === true` → show the Coercion Check panel
   (`CoercionCheck.tsx` / Android `coercionPanel`); "Yes, this is me" just flips a local
   `coercionAnswered = true`, "Cancel" discards the response and returns to the form.
2. Else if `txn_controls.manual_amount === true` → show Manual Amount Entry
   (`ManualAmountEntry.tsx` / `manualAmountPanel`); user re-types the amount to confirm
   it matches `expectedAmount`; on match, flips `confirmedManualAmount = true` locally.
3. Else if `txn_controls.cooling_until` is set → show a non-blocking Cooling Notice
   countdown (`CoolingNotice.tsx`) until that timestamp.
4. Only once all applicable flags are cleared does the UI treat the transfer as
   "complete" (Android: navigates to `TransferSuccessActivity`; web: just stops
   rendering the panels). Design Stitch states for **each** of these three panels plus
   the "all clear" state — don't design only one and assume the others reuse it.

### E6. Edge/empty states to design (often skipped by a single happy-path Stitch prompt)
- Busy/loading state on every submit button (`busy` flag in every page above).
- Network-unreachable error ("Could not reach CogniGuard. Please try again.") — generic,
  fires on any `fetch`/connection failure, not just 4xx/5xx.
- Lockout banner with the literal retry-after seconds from `hardening.retry_after_s`.
- Cold-start trust state (`trust_score`/`behavior_match_score` both `null`) — must look
  intentional, not like a loading glitch.
- `degraded_mode: true` badge.
- Empty list states for Transactions/Beneficiaries/Trusted-devices (new accounts have
  none yet — the seeded demo personas do, but design for zero).

---

## References
- Google Stitch — https://stitch.withgoogle.com/
- Stitch Prompt Guide — https://discuss.ai.google.dev/t/stitch-prompt-guide/83844
- Introducing Stitch (Google Developers Blog) — https://developers.googleblog.com/stitch-a-new-way-to-design-uis/
- CBI logo colour scheme — https://www.schemecolor.com/central-bank-of-india-logo.php
- CBI brand assets (Brandfetch) — https://brandfetch.com/centralbankofindia.co.in
