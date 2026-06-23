package com.cogniguard.demoapp

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
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
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.time.Instant

/** Demo IB app login screen -- parity with `web-app/src/pages/Login.tsx`
 * (Implementation.md Phase 18/24): same register -> consent -> login sequence, same
 * allow/verify/block branching. Surfaces the "Security Profile Calibration N/10"
 * enrollment banner (Phase 21) + the identity-gated Trust Score (Phase 20-22), and
 * drives `verify` through a real Android `BiometricPrompt` for phishing-resistant
 * factors (FINGERPRINT/FACE/PASSKEY), or the demo OTP/MPIN code otherwise. */
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

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_login)
        client = CogniGuardClient(BuildConfig.API_BASE, BuildConfig.SIGNING_SECRET)
        Signer.resetSequence() // fresh nonce cycle on a fresh screen, mirrors web's per-session reset

        val usernameInput = findViewById<EditText>(R.id.usernameInput)
        val passwordInput = findViewById<EditText>(R.id.passwordInput)
        val loginButton = findViewById<Button>(R.id.loginButton)
        statusText = findViewById(R.id.statusText)

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
            statusText.text = "Signing in..."

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
                        "block" -> statusText.text = "Login denied."
                        else -> statusText.text = "Unexpected response: $body"
                    }
                } catch (e: Exception) {
                    statusText.text = "Could not reach CogniGuard: ${e.message}"
                }
            }
        }
    }

    /** Lands on `DashboardActivity` (not `TransferActivity` directly) on every `allow` --
     * Phase 31 nav flow is Login -> Dashboard -> Transfer -> Success. Carries the
     * continuous-identity-verification doubles (Phase 20-22) through as `Double.NaN` when
     * absent so `SecurityCenterActivity` can render "Calibrating" instead of a stale value. */
    private fun goToDashboard(body: JSONObject) {
        val intent = Intent(this@LoginActivity, DashboardActivity::class.java)
        intent.putExtra(DashboardActivity.EXTRA_SESSION_TOKEN, body.optString("session_token", null))
        intent.putExtra(DashboardActivity.EXTRA_USERNAME, currentUsername)
        if (!body.isNull("trust_score")) {
            intent.putExtra(DashboardActivity.EXTRA_TRUST_SCORE, body.optDouble("trust_score"))
        }
        if (!body.isNull("behavior_match_score")) {
            intent.putExtra(DashboardActivity.EXTRA_BEHAVIOR_MATCH, body.optDouble("behavior_match_score"))
        }
        if (!body.isNull("device_trust")) {
            intent.putExtra(DashboardActivity.EXTRA_DEVICE_TRUST, body.optDouble("device_trust"))
        }
        startActivity(intent)
        finish()
    }

    /** "Security Profile Calibration N/10" banner (Phase 21) -- progress accrues over the
     * first ~N genuine app-opens; the baseline is auto-generated on the cycle that hits N. */
    private fun renderCalibration(body: JSONObject) {
        val view = findViewById<TextView>(R.id.calibrationText)
        val enrollment = body.optJSONObject("enrollment")
        if (enrollment == null) {
            view.text = ""
            return
        }
        view.text =
            if (enrollment.optBoolean("complete")) {
                "✓ Security profile calibrated — identity verification active."
            } else {
                "Security Profile Calibration ${enrollment.optInt("collected")}/" +
                    "${enrollment.optInt("required")}"
            }
    }

    /** Identity-gated Trust Score + per-user behavior match (Phase 20-22). */
    private fun renderTrust(body: JSONObject) {
        val view = findViewById<TextView>(R.id.trustText)
        if (body.isNull("trust_score")) {
            view.text = ""
            return
        }
        val trust = body.optDouble("trust_score")
        val match =
            if (body.isNull("behavior_match_score")) "calibrating…"
            else "${body.optDouble("behavior_match_score").toInt()}%"
        view.text = "Trust ${trust.toInt()}/100 · Behavior match $match"
    }

    /** `verify` (Phase 24): phishing-resistant factors go through a real BiometricPrompt;
     * OTP/MPIN/VOICE_READBACK fall back to the demo code the gateway accepts. */
    private fun handleVerify(body: JSONObject) {
        val stepUp = body.optJSONObject("step_up")
        if (stepUp == null) {
            statusText.text = "Step-up required."
            return
        }
        val challengeId = stepUp.optString("challenge_id")
        val factor = stepUp.optString("challenge_type")
        statusText.text = "Step-up required: $factor"
        if (factor == "FINGERPRINT" || factor == "FACE" || factor == "PASSKEY") {
            promptBiometric(factor) { submitStepUp(challengeId, "biometric-$factor-ok") }
        } else {
            // Demo OTP/MPIN code (gateway accepts "123456"); see web StepUp parity.
            submitStepUp(challengeId, "123456")
        }
    }

    private fun promptBiometric(factor: String, onSuccess: () -> Unit) {
        val executor = ContextCompat.getMainExecutor(this)
        val prompt =
            BiometricPrompt(
                this,
                executor,
                object : BiometricPrompt.AuthenticationCallback() {
                    override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                        onSuccess()
                    }

                    override fun onAuthenticationError(code: Int, errString: CharSequence) {
                        statusText.text = "Step-up failed: $errString"
                    }
                },
            )
        val info =
            BiometricPrompt.PromptInfo.Builder()
                .setTitle("Verify it's you")
                .setSubtitle("Confirm your identity to continue ($factor)")
                .setNegativeButtonText("Cancel")
                .build()
        prompt.authenticate(info)
    }

    private fun submitStepUp(challengeId: String, assertion: String) {
        CoroutineScope(Dispatchers.Main).launch {
            try {
                val res = withContext(Dispatchers.IO) { client.verifyStepUp(challengeId, assertion) }
                if (res.body.optString("action") == "allow") {
                    statusText.text = "Verified."
                    goToDashboard(res.body)
                } else {
                    statusText.text = "Step-up failed, try again."
                }
            } catch (e: Exception) {
                statusText.text = "Could not reach CogniGuard: ${e.message}"
            }
        }
    }

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
