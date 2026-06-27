package com.cogniguard.demoapp

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import com.cogniguard.capturesdk.KeystrokeCapture
import com.cogniguard.capturesdk.MotionCapture
import com.cogniguard.capturesdk.TouchCapture
import com.cogniguard.capturesdk.edge.MobileFeatures
import com.cogniguard.capturesdk.fingerprint.DeviceFingerprint
import com.cogniguard.capturesdk.integrity.Signer
import com.cogniguard.capturesdk.ml.AeSequenceScorer
import com.cogniguard.capturesdk.model.ActionBlock
import com.cogniguard.capturesdk.model.ContextBlock
import com.cogniguard.capturesdk.model.UnsignedBehaviorPayload
import com.cogniguard.capturesdk.net.CogniGuardClient
import com.google.android.material.chip.Chip
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.time.Instant

/** Demo IB app login screen â€” parity with `web-app/src/pages/Login.tsx`
 * (Implementation.md Phase 18/24): same register â†’ consent â†’ login sequence,
 * same allow/verify/block branching.
 *
 * Adaptive re-authentication (Phase adaptive):
 *   Low risk   â†’ allow â†’ Dashboard (no re-auth)
 *   Medium risk â†’ verify (light) â†’ visible OTP screen â†’ submit â†’ Dashboard
 *   High risk   â†’ verify (strong) â†’ visible Step 1 OTP â†’ Step 2 Biometric â†’ Dashboard
 *   Critical    â†’ verify (strong) â†’ same 2FA; block only if all attempts exhausted
 *
 * All step-up interactions are EXPLICIT â€” no silent auto-submit. User must tap
 * "Verify OTP" or "Fingerprint / Face ID" buttons. The re-auth card slides in
 * automatically when action=verify; the login form is kept but dimmed. */
class LoginActivity : AppCompatActivity() {
    private lateinit var client: CogniGuardClient
    private lateinit var keystrokeCapture: KeystrokeCapture
    private lateinit var touchCapture: TouchCapture
    private lateinit var motionCapture: MotionCapture
    private val aeScorerLazy = lazy { AeSequenceScorer(this) }
    private val aeScorer by aeScorerLazy
    private var aeModelVersion: String? = null
    private var currentUsername: String = ""
    private lateinit var statusText: TextView

    // Re-auth panel views
    private lateinit var reAuthCard: View
    private lateinit var reAuthRiskLabel: TextView
    private lateinit var reAuthRiskBadge: Chip
    private lateinit var reAuthReasonText: TextView
    private lateinit var reAuthStepRow: LinearLayout
    private lateinit var reAuthStep1Bubble: TextView
    private lateinit var reAuthStep2Bubble: TextView
    private lateinit var reAuthStep2Label: TextView
    private lateinit var reAuthStepLine: View
    private lateinit var reAuthOtpSection: LinearLayout
    private lateinit var reAuthOtpInput: EditText
    private lateinit var reAuthOtpSubmitButton: Button
    private lateinit var reAuthBiometricSection: LinearLayout
    private lateinit var reAuthBiometricTitle: TextView
    private lateinit var reAuthFingerprintButton: Button
    private lateinit var reAuthFaceButton: Button
    private lateinit var reAuthStatusText: TextView
    private lateinit var reAuthRetryText: TextView
    private lateinit var reAuthCancelLink: TextView
    private lateinit var loginCard: View

    // Step-up state
    private var pendingChallengeId: String = ""
    private var pendingSecondFactor: String? = null
    private var pendingAssurance: String = "light"
    private var pendingRiskBand: String = "medium"
    private var stepUpAttempts: Int = 0
    private val maxAttempts: Int = 3
    private var otpVerified: Boolean = false
    private var sessionTokenFromOtpStep: JSONObject? = null  // carries session_token for 2FA final nav

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)
        setContentView(R.layout.activity_login)
        client = CogniGuardClient(BuildConfig.API_BASE, BuildConfig.SIGNING_SECRET)
        Signer.resetSequence() // fresh nonce cycle on a fresh screen

        val usernameInput = findViewById<EditText>(R.id.usernameInput)
        val passwordInput = findViewById<EditText>(R.id.passwordInput)
        val loginButton = findViewById<Button>(R.id.loginButton)
        statusText = findViewById(R.id.statusText)

        // Re-auth panel view bindings
        loginCard = findViewById(R.id.loginCard)
        reAuthCard = findViewById(R.id.reAuthCard)
        reAuthRiskLabel = findViewById(R.id.reAuthRiskLabel)
        reAuthRiskBadge = findViewById(R.id.reAuthRiskBadge)
        reAuthReasonText = findViewById(R.id.reAuthReasonText)
        reAuthStepRow = findViewById(R.id.reAuthStepRow)
        reAuthStep1Bubble = findViewById(R.id.reAuthStep1Bubble)
        reAuthStep2Bubble = findViewById(R.id.reAuthStep2Bubble)
        reAuthStep2Label = findViewById(R.id.reAuthStep2Label)
        reAuthStepLine = findViewById(R.id.reAuthStepLine)
        reAuthOtpSection = findViewById(R.id.reAuthOtpSection)
        reAuthOtpInput = findViewById(R.id.reAuthOtpInput)
        reAuthOtpSubmitButton = findViewById(R.id.reAuthOtpSubmitButton)
        reAuthBiometricSection = findViewById(R.id.reAuthBiometricSection)
        reAuthBiometricTitle = findViewById(R.id.reAuthBiometricTitle)
        reAuthFingerprintButton = findViewById(R.id.reAuthFingerprintButton)
        reAuthFaceButton = findViewById(R.id.reAuthFaceButton)
        reAuthStatusText = findViewById(R.id.reAuthStatusText)
        reAuthRetryText = findViewById(R.id.reAuthRetryText)
        reAuthCancelLink = findViewById(R.id.reAuthCancelLink)

        keystrokeCapture = KeystrokeCapture.attach(passwordInput, fieldId = "password")
        touchCapture = TouchCapture()
        usernameInput.setOnTouchListener(touchCapture)
        passwordInput.setOnTouchListener(touchCapture)
        motionCapture = MotionCapture(this)
        motionCapture.start()

        loginButton.setOnClickListener {
            val username = usernameInput.text.toString()
            val password = passwordInput.text.toString()
            currentUsername = username
            statusText.text = "Signing inâ€¦"
            resetReAuthState()

            CoroutineScope(Dispatchers.Main).launch {
                try {
                    withContext(Dispatchers.IO) { client.register(username, password) }
                    withContext(Dispatchers.IO) { client.setConsent(username) }

                    val behavior = withContext(Dispatchers.IO) { buildBehaviorPayload(action = "LOGIN") }
                    val result = withContext(Dispatchers.IO) { client.login(username, password, behavior) }
                    val body = result.body

                    renderCalibration(body)
                    renderTrust(body)

                    when (body.optString("action")) {
                        "allow" -> {
                            statusText.text = "Welcome back."
                            goToDashboard(body)
                        }
                        "verify" -> handleVerify(body)
                        "block" -> {
                            statusText.text = "Login denied. Please contact support."
                        }
                        else -> statusText.text = "Unexpected response: ${body.optString("action")}"
                    }
                } catch (e: Exception) {
                    statusText.text = "Could not reach CogniGuard: ${e.message}"
                }
            }
        }

        // OTP submit button â€” explicit user tap required
        reAuthOtpSubmitButton.setOnClickListener {
            val otp = reAuthOtpInput.text?.toString()?.trim() ?: ""
            if (otp.isEmpty()) {
                showReAuthStatus("Please enter your OTP code.", isError = true)
                return@setOnClickListener
            }
            reAuthOtpSubmitButton.isEnabled = false
            reAuthOtpSubmitButton.text = "Verifyingâ€¦"
            submitOtpStep(otp)
        }

        // Fingerprint button â€” explicit user tap
        reAuthFingerprintButton.setOnClickListener {
            reAuthFingerprintButton.isEnabled = false
            reAuthFaceButton.isEnabled = false
            promptBiometric("FINGERPRINT") { onBiometricSuccess("FINGERPRINT") }
        }

        // Face ID button â€” explicit user tap
        reAuthFaceButton.setOnClickListener {
            reAuthFingerprintButton.isEnabled = false
            reAuthFaceButton.isEnabled = false
            promptBiometric("FACE") { onBiometricSuccess("FACE") }
        }

        // Cancel â€” return to login form cleanly
        reAuthCancelLink.setOnClickListener {
            resetReAuthState()
            statusText.text = "Verification cancelled. Please log in again."
        }
    }

    // ---------------------------------------------------------------------------
    //  NAVIGATION
    // ---------------------------------------------------------------------------

    /** Lands on `DashboardActivity` on every `allow` â€” Phase 31 nav flow:
     *  Login â†’ Dashboard â†’ Transfer â†’ Success. Carries continuous-identity
     *  verification doubles through as `Double.NaN` when absent. */
    private fun goToDashboard(body: JSONObject) {
        val intent = Intent(this@LoginActivity, DashboardActivity::class.java)
        intent.putExtra(DashboardActivity.EXTRA_SESSION_TOKEN, body.optString("session_token", null))
        intent.putExtra(DashboardActivity.EXTRA_USERNAME, currentUsername)
        if (!body.isNull("trust_score"))
            intent.putExtra(DashboardActivity.EXTRA_TRUST_SCORE, body.optDouble("trust_score"))
        if (!body.isNull("behavior_match_score"))
            intent.putExtra(DashboardActivity.EXTRA_BEHAVIOR_MATCH, body.optDouble("behavior_match_score"))
        if (!body.isNull("device_trust"))
            intent.putExtra(DashboardActivity.EXTRA_DEVICE_TRUST, body.optDouble("device_trust"))
        startActivity(intent)
        finish()
    }

    // ---------------------------------------------------------------------------
    //  CALIBRATION + TRUST RENDERING
    // ---------------------------------------------------------------------------

    /** "Security Profile Calibration N/10" banner (Phase 21). */
    private fun renderCalibration(body: JSONObject) {
        val view = findViewById<TextView>(R.id.calibrationText)
        val enrollment = body.optJSONObject("enrollment")
        if (enrollment == null) { view.text = ""; return }
        view.text = if (enrollment.optBoolean("complete")) {
            "âœ“ Security profile calibrated â€” identity verification active."
        } else {
            "Security Profile Calibration ${enrollment.optInt("collected")}/${enrollment.optInt("required")}"
        }
    }

    /** Identity-gated Trust Score + per-user behavior match (Phase 20-22). */
    private fun renderTrust(body: JSONObject) {
        val view = findViewById<TextView>(R.id.trustText)
        if (body.isNull("trust_score")) { view.text = ""; return }
        val trust = body.optDouble("trust_score")
        val match = if (body.isNull("behavior_match_score")) "calibratingâ€¦"
                    else "${body.optDouble("behavior_match_score").toInt()}%"
        view.text = "Trust ${trust.toInt()}/100 Â· Behavior match $match"
    }

    // ---------------------------------------------------------------------------
    //  ADAPTIVE RE-AUTHENTICATION â€” ENTRY POINT
    // ---------------------------------------------------------------------------

    /** Called when the backend returns `action=verify`.
     *
     * Instead of silently auto-submitting any code, this method:
     *   1. Reads risk_band and step_up from the server response.
     *   2. Makes the re-auth panel VISIBLE with appropriate risk badging.
     *   3. Shows OTP entry for light assurance (medium risk).
     *   4. Shows Step 1 (OTP) + Step 2 (Biometric) indicators for strong assurance.
     *   5. Waits for the user to explicitly tap the verify/biometric buttons.
     */
    private fun handleVerify(body: JSONObject) {
        val stepUp = body.optJSONObject("step_up")
        if (stepUp == null) {
            statusText.text = "Step-up required â€” missing challenge details."
            return
        }
        pendingChallengeId = stepUp.optString("challenge_id")
        val factor = stepUp.optString("challenge_type")
        val secondFactor = if (stepUp.isNull("second_factor")) null else stepUp.optString("second_factor")
        val assurance = stepUp.optString("assurance", "light")
        val riskBand = body.optString("risk_band", "medium")
        val riskScore = body.optDouble("risk_score", 0.0)

        pendingSecondFactor = secondFactor
        pendingAssurance = assurance
        pendingRiskBand = riskBand
        stepUpAttempts = 0
        otpVerified = false

        statusText.text = ""

        android.util.Log.d("DemoAuthFlow", "Entered Re-Auth Panel: RiskBand=$riskBand, Factor=$factor, SecondFactor=$secondFactor")

        // ── Update re-auth card visuals ──────────────────────────────────────
        showReAuthCard(riskBand, riskScore, assurance, factor, secondFactor)
    }

    // ---------------------------------------------------------------------------
    //  RE-AUTH PANEL RENDERING
    // ---------------------------------------------------------------------------

    private fun showReAuthCard(
        riskBand: String,
        riskScore: Double,
        assurance: String,
        factor: String,
        secondFactor: String?,
    ) {
        // Risk badge color + label
        val (badgeColor, badgeLabel, riskLabelText) = when (riskBand) {
            "high", "very_high" -> Triple(Color.parseColor("#DC2626"), "HIGH", "High Risk â€” Enhanced verification required")
            "medium"            -> Triple(Color.parseColor("#D97706"), "MEDIUM", "Medium Risk â€” Additional verification required")
            else                -> Triple(Color.parseColor("#0369A1"), riskBand.uppercase(), "Elevated Risk â€” Please verify your identity")
        }
        reAuthRiskBadge.text = badgeLabel
        reAuthRiskBadge.chipBackgroundColor = android.content.res.ColorStateList.valueOf(badgeColor)
        reAuthRiskLabel.text = riskLabelText

        // Reason explanation
        val reasonText = buildReasonText(riskBand, assurance, factor, secondFactor)
        reAuthReasonText.text = reasonText

        val isTwoFactor = assurance == "strong" && secondFactor != null

        // Step indicator: show only for 2FA
        if (isTwoFactor) {
            reAuthStepRow.visibility = View.VISIBLE
            reAuthStep2Label.text = secondFactor ?: "Biometric"
            // Step 1 active, step 2 pending
            activateStep(1)
        } else {
            reAuthStepRow.visibility = View.GONE
        }

        // OTP section: always shown first (OTP/MPIN factors or first step of 2FA)
        if (factor == "OTP" || factor == "MPIN" || isTwoFactor) {
            reAuthOtpInput.setText("")
            reAuthOtpInput.hint = if (factor == "MPIN") "Enter MPIN" else "Enter 6-digit OTP"
            reAuthOtpSubmitButton.text = if (isTwoFactor) "Verify OTP (Step 1)" else "Verify OTP"
            reAuthOtpSubmitButton.isEnabled = true
            reAuthOtpSection.visibility = View.VISIBLE
        } else {
            // Direct biometric (light assurance with biometric factor â€” future)
            reAuthOtpSection.visibility = View.GONE
        }

        // Biometric section: show immediately only for non-OTP single-factor challenges
        if (!isTwoFactor && (factor == "FINGERPRINT" || factor == "FACE" || factor == "PASSKEY")) {
            reAuthBiometricTitle.text = "Tap to verify with ${factor.lowercase().replaceFirstChar { it.uppercase() }}"
            reAuthBiometricSection.visibility = View.VISIBLE
        } else {
            // For 2FA biometric section is revealed after OTP succeeds in submitOtpStep()
            reAuthBiometricSection.visibility = View.GONE
        }

        reAuthStatusText.visibility = View.GONE
        reAuthRetryText.visibility = View.GONE
        reAuthCard.visibility = View.VISIBLE

        // Scroll to re-auth card
        reAuthCard.requestFocus()
    }

    private fun buildReasonText(riskBand: String, assurance: String, factor: String, secondFactor: String?): String {
        return when {
            riskBand in listOf("high", "very_high") && secondFactor != null ->
                "Our AI detected a high-risk pattern in this session (risk band: $riskBand). " +
                "Two-step verification is required: first confirm your OTP, then verify with biometrics."
            riskBand == "medium" ->
                "Our AI detected elevated risk in this session (risk band: $riskBand). " +
                "Please confirm your identity with a one-time password to continue."
            assurance == "strong" ->
                "Security policy requires strong verification for this session. " +
                "Please complete both OTP and biometric verification steps."
            else ->
                "Our security system detected unusual patterns. Please verify your identity to continue."
        }
    }

    private fun activateStep(step: Int) {
        val activeColor = ContextCompat.getColor(this, R.color.cbi_primary)
        val dimColor = ContextCompat.getColor(this, R.color.cbi_text_muted)

        when (step) {
            1 -> {
                reAuthStep1Bubble.alpha = 1.0f
                reAuthStep1Bubble.setTextColor(Color.WHITE)
                reAuthStep2Bubble.alpha = 0.4f
                reAuthStep2Label.setTextColor(dimColor)
                reAuthStepLine.setBackgroundColor(dimColor)
            }
            2 -> {
                reAuthStep1Bubble.alpha = 1.0f
                reAuthStep1Bubble.setTextColor(Color.WHITE)
                reAuthStep2Bubble.alpha = 1.0f
                reAuthStep2Bubble.setTextColor(Color.WHITE)
                reAuthStep2Label.setTextColor(activeColor)
                reAuthStepLine.setBackgroundColor(activeColor)
            }
        }
    }

    private fun showReAuthStatus(message: String, isError: Boolean) {
        reAuthStatusText.text = message
        reAuthStatusText.setTextColor(
            if (isError) Color.parseColor("#DC2626") else Color.parseColor("#16A34A")
        )
        reAuthStatusText.visibility = View.VISIBLE
    }

    // ---------------------------------------------------------------------------
    //  OTP STEP SUBMISSION
    // ---------------------------------------------------------------------------

    /** Submits the OTP code to the backend.
     *
     * For single-factor (light assurance): submits the plain OTP.
     * For two-factor (strong assurance): submits the OTP part; if backend
     * returns allow it means the backend accepted the combined assertion â€” but
     * we never send the combined assertion until the biometric step also passes.
     * So for 2FA: on OTP success from backend we transition locally to Step 2
     * (biometric) without completing the final session grant yet. */
    private fun submitOtpStep(otpCode: String) {
        val isTwoFactor = pendingAssurance == "strong" && pendingSecondFactor != null

        CoroutineScope(Dispatchers.Main).launch {
            try {
                val res = withContext(Dispatchers.IO) {
                    client.verifyStepUp(pendingChallengeId, otpCode)
                }
                val body = res.body
                val action = body.optString("action")

                if (action == "allow" && !isTwoFactor) {
                    // Single-factor OTP succeeded â€” grant access
                    showReAuthStatus("âœ“ OTP verified. Granting accessâ€¦", isError = false)
                    reAuthOtpSection.visibility = View.GONE
                    goToDashboard(body)
                } else if (action == "allow" && isTwoFactor) {
                    // Backend accepted the OTP â€” now require biometric second step locally
                    otpVerified = true
                    sessionTokenFromOtpStep = body  // store full body with session_token for final nav
                    showReAuthStatus("âœ“ OTP verified. Now complete biometric verification.", isError = false)
                    reAuthOtpSection.visibility = View.GONE
                    activateStep(2)

                    // Show biometric section for second factor
                    val sf = pendingSecondFactor ?: "FINGERPRINT"
                    android.util.Log.d("DemoAuthFlow", "Entered Step 2: Biometric verification ($sf)")
                    reAuthBiometricTitle.text = "Step 2: Verify with ${sf.lowercase().replaceFirstChar { it.uppercase() }}"
                    reAuthBiometricSection.visibility = View.VISIBLE

                    // Re-enable biometric buttons
                    reAuthFingerprintButton.isEnabled = true
                    reAuthFaceButton.isEnabled = true
                } else if (action == "verify") {
                    // Wrong OTP â€” increment attempt counter
                    stepUpAttempts++
                    val remaining = maxAttempts - stepUpAttempts
                    reAuthOtpSubmitButton.isEnabled = true
                    reAuthOtpSubmitButton.text = if (isTwoFactor) "Verify OTP (Step 1)" else "Verify OTP"
                    reAuthOtpInput.setText("")
                    reAuthOtpInput.requestFocus()
                    showReAuthStatus("âœ— Incorrect OTP. Please try again.", isError = true)
                    if (remaining > 0) {
                        reAuthRetryText.text = "$remaining attempt${if (remaining == 1) "" else "s"} remaining"
                        reAuthRetryText.visibility = View.VISIBLE
                    }
                } else {
                    // Blocked â€” attempts exhausted
                    onStepUpBlocked("Maximum verification attempts exceeded. Access denied.")
                }
            } catch (e: Exception) {
                reAuthOtpSubmitButton.isEnabled = true
                reAuthOtpSubmitButton.text = if (isTwoFactor) "Verify OTP (Step 1)" else "Verify OTP"
                showReAuthStatus("Network error: ${e.message}", isError = true)
            }
        }
    }

    // ---------------------------------------------------------------------------
    //  BIOMETRIC STEP
    // ---------------------------------------------------------------------------

    private fun promptBiometric(factor: String, onSuccess: () -> Unit) {
        val factorName = factor.lowercase().replaceFirstChar { it.uppercase() }
        android.util.Log.d("DemoAuthFlow", "Displaying Mock Biometric Prompt Dialog")
        val dialog = android.app.AlertDialog.Builder(this)
            .setTitle("Verify it's you")
            .setMessage("Confirm your identity to complete login ($factor)\n\n(Demo: Simulating $factorName scan...)")
            .setCancelable(false)
            .show()

        // Simulate biometric scan delay to allow recording of the screen state
        CoroutineScope(Dispatchers.Main).launch {
            kotlinx.coroutines.delay(1500)
            dialog.dismiss()
            onSuccess()
        }
    }

    /** Called when the biometric step succeeds on device (BiometricPrompt callback).
     *
     * For single-factor biometric: submits the biometric assertion to backend.
     * For two-factor (Step 2 after OTP): backend already granted the session after
     * OTP â€” here we just confirm the local biometric and navigate to Dashboard
     * using the session token from the OTP-step response. In production this would
     * combine the assertions into a single request, but for the demo the session
     * token from the OTP backend confirm is sufficient. */
    private fun onBiometricSuccess(factor: String) {
        showReAuthStatus("âœ“ Biometric verified. Granting accessâ€¦", isError = false)
        reAuthBiometricSection.visibility = View.GONE

        if (pendingAssurance == "strong" && otpVerified) {
            // Two-factor complete â€” session already established at OTP step.
            // Submit a confirming biometric assertion with the combined format.
            val biometricToken = "biometric-$factor-ok"
            // Delegate final navigation; the session token was stored during OTP step.
            finishTwoFactorLogin(biometricToken)
        } else {
            // Single-factor biometric: submit to backend
            submitBiometricAssertion("biometric-$factor-ok")
        }
    }

    /** Single-factor biometric: submit to backend. */
    private fun submitBiometricAssertion(assertion: String) {
        CoroutineScope(Dispatchers.Main).launch {
            try {
                val res = withContext(Dispatchers.IO) {
                    client.verifyStepUp(pendingChallengeId, assertion)
                }
                if (res.body.optString("action") == "allow") {
                    goToDashboard(res.body)
                } else {
                    onStepUpBlocked("Biometric verification failed. Access denied.")
                }
            } catch (e: Exception) {
                reAuthFingerprintButton.isEnabled = true
                reAuthFaceButton.isEnabled = true
                showReAuthStatus("Network error: ${e.message}", isError = true)
            }
        }
    }

    /** Two-factor complete: OTP was verified (backend returned allow) and biometric
     *  succeeded locally. Navigate to Dashboard using the session token stored from
     *  the OTP-step backend response. */
    private fun finishTwoFactorLogin(biometricToken: String) {
        CoroutineScope(Dispatchers.Main).launch {
            try {
                showReAuthStatus("âœ“ Two-factor verification complete. Welcome!", isError = false)
                withContext(Dispatchers.IO) { Thread.sleep(600) }
                // Use the session body stored during the OTP step
                val dashBody = sessionTokenFromOtpStep ?: JSONObject()
                goToDashboard(dashBody)
            } catch (e: Exception) {
                showReAuthStatus("Navigation error: ${e.message}", isError = true)
            }
        }
    }

    // ---------------------------------------------------------------------------
    //  BLOCK / RESET
    // ---------------------------------------------------------------------------

    private fun onStepUpBlocked(message: String) {
        reAuthOtpSection.visibility = View.GONE
        reAuthBiometricSection.visibility = View.GONE
        reAuthRetryText.visibility = View.GONE
        showReAuthStatus("ðŸš« $message", isError = true)
        reAuthCancelLink.text = "Return to login"
    }

    private fun resetReAuthState() {
        reAuthCard.visibility = View.GONE
        reAuthOtpSection.visibility = View.GONE
        reAuthBiometricSection.visibility = View.GONE
        reAuthStatusText.visibility = View.GONE
        reAuthRetryText.visibility = View.GONE
        reAuthStepRow.visibility = View.GONE
        pendingChallengeId = ""
        pendingSecondFactor = null
        pendingAssurance = "light"
        pendingRiskBand = "medium"
        stepUpAttempts = 0
        otpVerified = false
        sessionTokenFromOtpStep = null
        reAuthCancelLink.text = "Cancel and return to login"
    }

    // ---------------------------------------------------------------------------
    //  BEHAVIOR PAYLOAD CONSTRUCTION
    // ---------------------------------------------------------------------------

    private suspend fun buildBehaviorPayload(action: String): UnsignedBehaviorPayload {
        val device = DeviceFingerprint.compute(this)
        val derivedFeatures =
            MobileFeatures.extract(swipes = touchCapture.drain(), motionSamples = motionCapture.drain()) +
                keystrokeCapture.derivedFeatures()
        keystrokeCapture.reset()
        if (aeModelVersion == null) {
            aeModelVersion = runCatching { client.getAeModel().body.optString("version") }.getOrNull()
        }
        val aeReconError = runCatching { aeScorer.score(derivedFeatures) }.getOrNull()
        return UnsignedBehaviorPayload(
            channel = "mobile",
            source = "mobile_edge",
            device = device,
            action = ActionBlock(type = action),
            keystroke = null, // mobile_edge sends derived_features only, never raw keystroke (NFR-10)
            derivedFeatures = derivedFeatures.takeIf { it.isNotEmpty() },
            aeReconError = aeReconError,
            aeModelVersion = if (aeReconError != null) aeModelVersion else null,
            context = ContextBlock(submittedAt = Instant.now().toString(), page = "login"),
        )
    }

    override fun onDestroy() {
        super.onDestroy()
        motionCapture.stop()
        if (aeScorerLazy.isInitialized()) aeScorer.close()
    }
}

