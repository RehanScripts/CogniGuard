# CogniGuard — Demo Upgrade Log

Branch: `final_2` · Date: 2026-06-29 · Purpose: pre-demo polish for Central Bank of India hackathon presentation.

---

## 1. Screen Recording — FLAG_SECURE fix

**Problem:** Android screen recording / screen share blacks out the app while the user types a password, because `FLAG_SECURE` was missing from some activities.

**Fix:** Added `window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)` as the first line of `onCreate` in the four activities that were missing it:

| Activity file | Status |
|---|---|
| `RegisterActivity.kt` | Fixed |
| `EmailVerifyActivity.kt` | Fixed |
| `ProfileActivity.kt` | Fixed |
| `UpiPinActivity.kt` | Fixed |

Already present in: `LoginActivity`, `DashboardActivity`, `TransferActivity`, `SecurityCenterActivity`, `TransactionHistoryActivity`, `TransferSuccessActivity`.

**Note on IME blanking:** Some on-screen keyboards (Gboard in incognito mode) still blank the keyboard overlay during screen recording regardless of the app flag — this is OS/keyboard-controlled and cannot be fully suppressed by the app. Workaround: use Samsung keyboard, or in a demo, switch the password EditText to `inputType="textVisiblePassword"` in the layout temporarily.

**How to verify:** Use Android built-in screen recorder or Google Meet screen share → navigate through Login → UPI PIN → Profile. No app-level blackout should appear.

---

## 2. Live Trust Score / Risk Jitter on SOC Dashboard

**Problem:** The Identity & Trust panel on the SOC dashboard showed static values between WebSocket events, making it look dead during a demo.

**Fix:** `bank-dashboard/src/components/TrustPanel.tsx` — added a `useEffect` + `setInterval(2000)` that applies ±2–4 pt random deviation (clamped 0–100) to the displayed values around the last real WS value, so the bars "breathe" every 2 seconds. The underlying data is unchanged; jitter resets when a new WS event arrives.

**How to verify:** Log in to SOC dashboard (`http://localhost:5174`) and wait for a scored event. The Trust Score / Behavior Match / Device Trust / Risk bars should visibly tick every ~2 s.

---

## 3. AI Investigate from Live Feed + Enhanced SHAP Explanation

### 3a. Click any Live Feed row → AI Investigate drawer

**Problem:** Clicking a live-feed row only navigated to User Detail; there was no way to AI-investigate a specific scored event from the live feed.

**Fix:**
- `EventTable.tsx` — added `scoreId?: string | null` to `EventRow`, changed click handler to call `onRowClick(row)` prop.
- `Live.tsx` — wires `onRowClick` to `selectedRow` state; renders `<EventDrawer>` when a row is selected.
- `EventDrawer.tsx` (new) — right-side drawer showing event meta + `SHAPExplainer` (AI investigate). Shows "View user profile →" link separately.
- `ws.ts` — added `score_id?: string | null` to `RiskScoreEvent` interface.
- Gateway: `schemas/topics.py` `RiskScoreEvent` → added `score_id: str | None`. `services/event_producer.py` → threads `score_id` through. `services/auth_flow.py` + `services/payment_flow.py` → pre-generate `uuid.uuid4()` and pass to both `persist_scoring_outcome` and `emit_risk_score` so the WS event carries the same ID that lands in the DB. `models/scoring.py` → added Python-side `default=uuid.uuid4` alongside existing server default. `services/audit.py` → `persist_risk_score` + `persist_scoring_outcome` accept optional `score_id`.

**Rows from `listEvents` (initial 50-row load):** always carry `score_id` → fully explainable.  
**Live WS rows from auth_flow / payment_flow:** carry `score_id` after this fix.  
**Decision-only WS rows (no risk score):** no `score_id` → drawer shows a message.

### 3b. Enhanced SHAP AI Explanation

**Problem:** Groq explanation was 3–4 plain sentences, too thin for a demo.

**Fix:**
- `gateway/app/services/groq_explain.py` — rewrote the closing prompt to request structured markdown: **Verdict**, **Why flagged** (bold keywords per signal), **What it means**, **Recommended action**. Raised `max_tokens` from 320 → 700.
- `bank-dashboard/src/components/SHAPExplainer.tsx` — added `MarkdownText` inline renderer that splits on `\n\n`, renders `**bold**` spans as `<strong className="font-semibold text-soc-primary">`, and wraps the AI section in a scrollable `max-h-80` container.

**How to verify:** Click any scored event row in the Live Feed → AI Investigate drawer opens → click "Explain Score (SHAP + AI)" → output should show structured verdict + bold keywords.

---

## 4. Navigation: Left Sidebar

**Problem:** Top horizontal navbar was requested to be a left sidebar for a more analyst-grade look.

**Fix:**
- `bank-dashboard/src/components/NavBar.tsx` — converted from horizontal `<nav>` to fixed `<aside className="w-56">` with brand at top, nav links in `<nav>`, and Sign Out pinned at bottom.
- `bank-dashboard/src/App.tsx` — layout changed from stacked `<NavBar/><main>` to flex-row `<div className="flex min-h-screen"><NavBar/><main className="ml-56 flex-1">`.

**How to verify:** Open `http://localhost:5174` → left sidebar appears with Live Feed / Cases / Policy / Governance links. Active link highlighted. Sign Out at bottom.

---

## 5. Android: Check Balance + Face Auth

### 5a. Check Balance (reveal/mask toggle)

**Problem:** Balance was always shown. User wanted it masked by default with a reveal-on-tap affordance.

**Fix:**
- `DashboardActivity.kt` — balance starts masked (`₹ ••••••`) after account load; real value cached in `cachedBalance`/`cachedCurrency`. New `toggleBalance()` reveals/re-masks on tap.
- `setupQuickActions()` — new "B / Balance" tile added before "H / History".

**How to verify:** Login → Dashboard. Balance card shows `₹ ••••••`. Tap "Balance" quick-action → reveals real amount. Tap again → re-masks.

### 5b. Dummy Face Authentication (very_high risk)

**Problem:** `very_high` risk band immediately blocked the transfer. User wanted a face scan (camera opens 2s, closes) before UPI PIN instead.

**Fix:**
- `AndroidManifest.xml` — added `CAMERA` permission.
- `build.gradle.kts` — added CameraX deps (`camera-core`, `camera-camera2`, `camera-lifecycle`, `camera-view` 1.3.1).
- `FaceAuthActivity.kt` (new) — opens front camera via CameraX `Preview`, shows "Verifying your identity…" overlay, auto-closes with `RESULT_OK` after 2 s. On permission denied, also closes with `RESULT_OK` (proceed to PIN).
- `activity_face_auth.xml` (new) — FrameLayout: `PreviewView` + dim overlay + scan ring + status text.
- `bg_face_scan_ring.xml` (new) — oval ring drawable.
- `UpiPinActivity.kt` — `very_high` branch now launches `FaceAuthActivity` via `ActivityResultContracts.StartActivityForResult`; on return, shows PIN entry. (Scoring at PIN submit decides allow/block.)

**DPDP/privacy note:** No image is captured, stored, or transmitted. The camera preview is purely cosmetic.

**How to verify:** Force a very_high risk transfer (e.g., impostor user / large new-payee amount via seeded scenario). Front camera should open for ~2 s with overlay, then PIN entry screen appears. Scoring then decides the outcome.

---

## 6. OTP: Real Validation + Central Bank of India Branding

### 6a. Real OTP Validation in UPI Flow

**Problem:** `UpiPinActivity.showOtpDialog` only checked non-empty; it never called `verifyPaymentStepUp` with the OTP. The emailed OTP was never validated.

**Fix:** `UpiPinActivity.kt` restructured `submitWithPin`:
1. `scorePayment` → if action=`verify` and `challenge_type=OTP`, shows `showPaymentOtpDialog(challengeId)`.
2. User enters OTP from email.
3. `verifyPaymentStepUp(challengeId, enteredOtp)` — gateway validates against Redis `otp:{challengeId}` and consumes on success.
4. Non-OTP step-ups (MPIN / biometric) continue to use `"MPIN:{pin}"`.

**Dev shortcut:** No email inbox? Run `GET http://10.22.36.33:8000/api/v1/dev/otp/{challenge_id}` (only works when `APP_ENV=dev`) to read the OTP directly.

### 6b. Email Branding → Central Bank of India

**Problem:** OTP emails and AI investigation output referenced "Heritage Trust Bank".

**Fix:**
- `gateway/app/services/otp.py` — subject + body now say "Central Bank of India".
- `gateway/app/config.py` — `smtp_from_email` default changed to `noreply@centralbankofindia.co.in`.
- `gateway/app/services/investigation_llm.py` — analyst persona changed to "Central Bank of India".

**How to verify:** Trigger a high-risk UPI transfer → check received email subject/body → should say "Central Bank of India".

---

## Rebuild / Restart Notes

| Component | Action needed |
|---|---|
| Android | Rebuild in Android Studio (Sync Gradle → Rebuild Project → Install on device) |
| SOC Dashboard | `docker compose --profile ui up --build bank-dashboard` or `npm run dev` in `bank-dashboard/` |
| Gateway | `docker compose up --build gateway` or restart with uvicorn |
| No DB migration needed | `score_id` has a Python-side default; no schema change |
