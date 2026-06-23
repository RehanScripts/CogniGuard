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

## References
- Google Stitch — https://stitch.withgoogle.com/
- Stitch Prompt Guide — https://discuss.ai.google.dev/t/stitch-prompt-guide/83844
- Introducing Stitch (Google Developers Blog) — https://developers.googleblog.com/stitch-a-new-way-to-design-uis/
- CBI logo colour scheme — https://www.schemecolor.com/central-bank-of-india-logo.php
- CBI brand assets (Brandfetch) — https://brandfetch.com/centralbankofindia.co.in
