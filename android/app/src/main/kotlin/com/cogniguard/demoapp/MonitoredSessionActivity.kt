package com.cogniguard.demoapp

import android.content.Intent
import android.os.Bundle
import android.view.MotionEvent
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import com.cogniguard.capturesdk.MotionCapture
import com.cogniguard.capturesdk.TouchCapture
import com.cogniguard.capturesdk.edge.MobileFeatures
import com.cogniguard.capturesdk.fingerprint.DeviceFingerprint
import com.cogniguard.capturesdk.ml.AeSequenceScorer
import com.cogniguard.capturesdk.model.ActionBlock
import com.cogniguard.capturesdk.model.ContextBlock
import com.cogniguard.capturesdk.model.UnsignedBehaviorPayload
import com.cogniguard.capturesdk.net.CogniGuardClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.Instant

/** Base for authenticated screens -- the client half of `behavior_flow.ingest`'s
 * continuous mid-session re-scoring (Architecture §6.4, Implementation.md Phase 9).
 * Captures every swipe on the screen via [dispatchTouchEvent] (children never see a
 * consumed event, an activity-level listener would) plus accelerometer motion, and
 * POSTs a signed `/behavior/ingest` payload every [INGEST_INTERVAL_MS] while
 * foregrounded. Gateway `verify` -> biometric re-auth dialog; `reauth` (session
 * terminated + JWT denylisted server-side) -> back to login. Subclasses that also do
 * event-triggered scoring (e.g. Transfer's `scorePayment`) keep their own captures --
 * the buffers here are independent and `Signer`'s seq counter is process-global, so
 * the two paths never collide. */
abstract class MonitoredSessionActivity : AppCompatActivity() {

    /** `context.page` value for this screen's ingest payloads. */
    protected abstract val monitoredPage: String

    private val monitorClient by lazy { CogniGuardClient(BuildConfig.API_BASE, BuildConfig.SIGNING_SECRET) }
    private val monitorTouch = TouchCapture()
    private lateinit var monitorMotion: MotionCapture
    private val monitorAeLazy = lazy { AeSequenceScorer(this) }
    private val monitorAe by monitorAeLazy
    private var monitorAeModelVersion: String? = null
    private var monitorJob: Job? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        monitorMotion = MotionCapture(this)
    }

    override fun dispatchTouchEvent(ev: MotionEvent): Boolean {
        monitorTouch.onTouch(null, ev)
        return super.dispatchTouchEvent(ev)
    }

    override fun onResume() {
        super.onResume()
        monitorMotion.start()
        val token = intent.getStringExtra(EXTRA_SESSION_TOKEN) ?: return
        monitorJob = CoroutineScope(Dispatchers.IO).launch {
            while (isActive) {
                delay(INGEST_INTERVAL_MS)
                try {
                    val behavior = buildMonitorPayload()
                    val result = monitorClient.ingest(token, behavior)
                    val action = result.body.optString("action")
                    val reauth = result.body.optBoolean("reauth", false)
                    withContext(Dispatchers.Main) {
                        when {
                            reauth -> navigateToLogin("Your session was terminated for security reasons.")
                            action == "verify" -> showSessionReauthDialog()
                        }
                    }
                } catch (_: Exception) { /* best-effort */ }
            }
        }
    }

    override fun onPause() {
        super.onPause()
        monitorMotion.stop()
        monitorJob?.cancel()
        monitorJob = null
    }

    override fun onDestroy() {
        super.onDestroy()
        if (monitorAeLazy.isInitialized()) monitorAe.close()
    }

    private suspend fun buildMonitorPayload(): UnsignedBehaviorPayload {
        val device = DeviceFingerprint.compute(this)
        val derivedFeatures =
            MobileFeatures.extract(swipes = monitorTouch.drain(), motionSamples = monitorMotion.drain())
        if (monitorAeModelVersion == null) {
            monitorAeModelVersion = runCatching { monitorClient.getAeModel().body.optString("version") }.getOrNull()
        }
        val aeReconError = runCatching { monitorAe.score(derivedFeatures) }.getOrNull()
        return UnsignedBehaviorPayload(
            channel = "mobile",
            source = "mobile_edge",
            device = device,
            action = ActionBlock(type = "VIEW_BALANCE"),
            derivedFeatures = derivedFeatures.takeIf { it.isNotEmpty() },
            aeReconError = aeReconError,
            aeModelVersion = if (aeReconError != null) monitorAeModelVersion else null,
            context = ContextBlock(submittedAt = Instant.now().toString(), page = monitoredPage),
        )
    }

    private fun showSessionReauthDialog() {
        if (isFinishing || isDestroyed) return
        AlertDialog.Builder(this)
            .setTitle("Security Check")
            .setMessage("Unusual activity detected on your session. Please verify your identity to continue.")
            .setPositiveButton("Verify with Biometric") { _, _ ->
                promptSessionBiometric { /* verified — dismiss and continue */ }
            }
            .setNegativeButton("Log Out") { _, _ ->
                navigateToLogin("Logged out for security.")
            }
            .setCancelable(false)
            .show()
    }

    /** Real BiometricPrompt with CryptoObject for session re-auth.
     *  Signs a local timestamp nonce so the OS enforces a fresh biometric before the
     *  KeyStore key is used. The signature is not sent to the server — it proves locally
     *  that the physical user was present. Falls back to plain authenticate if key not bound. */
    private fun promptSessionBiometric(onSuccess: () -> Unit) {
        val nonce = "reauth:${System.currentTimeMillis()}"
        val sig = BiometricEnrollmentManager.prepareSignature(nonce)
        val executor = ContextCompat.getMainExecutor(this)
        val prompt = BiometricPrompt(
            this, executor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    if (sig != null) {
                        // consume the signature to complete the CryptoObject authentication
                        runCatching { result.cryptoObject?.signature?.sign() }
                    }
                    onSuccess()
                }
                override fun onAuthenticationError(code: Int, errString: CharSequence) {
                    navigateToLogin("Verification failed — please log in again.")
                }
                override fun onAuthenticationFailed() { /* user can retry */ }
            },
        )
        val info = BiometricPrompt.PromptInfo.Builder()
            .setTitle("Verify your identity")
            .setSubtitle("CogniGuard detected unusual session activity")
            .setNegativeButtonText("Log Out")
            .build()
        if (sig != null) {
            prompt.authenticate(info, BiometricPrompt.CryptoObject(sig))
        } else {
            prompt.authenticate(info)
        }
    }

    protected fun navigateToLogin(message: String) {
        val intent = Intent(this, LoginActivity::class.java)
        intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        intent.putExtra("logout_message", message)
        startActivity(intent)
        finish()
    }

    companion object {
        // Every authenticated screen passes its JWT under this same extra key.
        private const val EXTRA_SESSION_TOKEN = "session_token"
        // 10s so a mid-session hijack is caught within seconds on any screen.
        private const val INGEST_INTERVAL_MS = 10_000L
    }
}
