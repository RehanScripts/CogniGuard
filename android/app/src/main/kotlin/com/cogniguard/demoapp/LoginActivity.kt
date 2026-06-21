package com.cogniguard.demoapp

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.cogniguard.capturesdk.KeystrokeCapture
import com.cogniguard.capturesdk.MotionCapture
import com.cogniguard.capturesdk.TouchCapture
import com.cogniguard.capturesdk.edge.MobileFeatures
import com.cogniguard.capturesdk.fingerprint.DeviceFingerprint
import com.cogniguard.capturesdk.integrity.Signer
import com.cogniguard.capturesdk.model.ActionBlock
import com.cogniguard.capturesdk.model.ContextBlock
import com.cogniguard.capturesdk.model.UnsignedBehaviorPayload
import com.cogniguard.capturesdk.net.CogniGuardClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.Instant

/** Demo IB app login screen -- parity with `web-app/src/pages/Login.tsx`
 * (Implementation.md Phase 18): same register -> consent -> login sequence, same
 * allow/verify/block branching. Step-up UI is out of scope for this demo (the web
 * app's own `/step-up` route is similarly minimal) -- `verify` just surfaces a status
 * line rather than driving a real OTP/biometric challenge flow. */
class LoginActivity : AppCompatActivity() {
    private lateinit var client: CogniGuardClient
    private lateinit var keystrokeCapture: KeystrokeCapture
    private lateinit var touchCapture: TouchCapture
    private lateinit var motionCapture: MotionCapture

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_login)
        client = CogniGuardClient(BuildConfig.API_BASE, BuildConfig.SIGNING_SECRET)
        Signer.resetSequence() // fresh nonce cycle on a fresh screen, mirrors web's per-session reset

        val usernameInput = findViewById<EditText>(R.id.usernameInput)
        val passwordInput = findViewById<EditText>(R.id.passwordInput)
        val loginButton = findViewById<Button>(R.id.loginButton)
        val statusText = findViewById<TextView>(R.id.statusText)

        keystrokeCapture = KeystrokeCapture.attach(passwordInput, fieldId = "password")
        touchCapture = TouchCapture()
        usernameInput.setOnTouchListener(touchCapture)
        passwordInput.setOnTouchListener(touchCapture)
        motionCapture = MotionCapture(this)
        motionCapture.start()

        loginButton.setOnClickListener {
            val username = usernameInput.text.toString()
            val password = passwordInput.text.toString()
            statusText.text = "Signing in..."

            CoroutineScope(Dispatchers.Main).launch {
                try {
                    withContext(Dispatchers.IO) { client.register(username, password) }
                    withContext(Dispatchers.IO) { client.setConsent(username) }

                    val behavior = buildBehaviorPayload(action = "LOGIN")
                    val result = withContext(Dispatchers.IO) { client.login(username, password, behavior) }
                    val body = result.body

                    when (body.optString("action")) {
                        "allow" -> {
                            val sessionToken = body.optString("session_token", null)
                            statusText.text = "Welcome back."
                            val intent = Intent(this@LoginActivity, TransferActivity::class.java)
                            intent.putExtra(TransferActivity.EXTRA_SESSION_TOKEN, sessionToken)
                            startActivity(intent)
                        }
                        "verify" -> statusText.text = "Step-up required (not implemented in this demo)."
                        "block" -> statusText.text = "Login denied."
                        else -> statusText.text = "Unexpected response: $body"
                    }
                } catch (e: Exception) {
                    statusText.text = "Could not reach CogniGuard: ${e.message}"
                }
            }
        }
    }

    private fun buildBehaviorPayload(action: String): UnsignedBehaviorPayload {
        val device = DeviceFingerprint.compute(this)
        val derivedFeatures =
            MobileFeatures.extract(swipes = touchCapture.drain(), motionSamples = motionCapture.drain()) +
                keystrokeCapture.derivedFeatures()
        keystrokeCapture.reset()
        return UnsignedBehaviorPayload(
            channel = "mobile",
            source = "mobile_edge",
            device = device,
            action = ActionBlock(type = action),
            keystroke = null, // mobile_edge sends derived_features only, never raw keystroke (NFR-10)
            derivedFeatures = derivedFeatures.takeIf { it.isNotEmpty() },
            aeReconError = null, // wired once AutoencoderTFLite is loaded with a real model.tflite asset
            aeModelVersion = null,
            context = ContextBlock(submittedAt = Instant.now().toString(), page = "login"),
        )
    }

    override fun onDestroy() {
        super.onDestroy()
        motionCapture.stop()
    }
}
