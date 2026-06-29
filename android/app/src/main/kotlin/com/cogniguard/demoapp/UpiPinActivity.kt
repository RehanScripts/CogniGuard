package com.cogniguard.demoapp

import android.content.Intent
import android.os.Bundle
import android.util.Base64
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import com.google.android.material.card.MaterialCardView
import com.google.android.material.textfield.TextInputEditText
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
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.Instant

/**
 * Adaptive pre-UPI-PIN re-auth gate.
 *
 * Flow:
 *   1. Calls POST /behavior/ingest to read the current session risk band.
 *   2. Branches by band:
 *        low       → show PIN entry immediately
 *        medium    → biometric first, then PIN
 *        high      → biometric first, then PIN (OTP comes from scorePayment if needed)
 *        very_high → face scan (2s FaceAuthActivity), then PIN; scoring decides outcome
 *   3. On PIN submit: calls scorePayment(). If action=verify with OTP factor, shows OTP dialog
 *      and calls verifyPaymentStepUp with the entered OTP (validated against Redis otp:{id}).
 *   4. Returns RESULT_OK to TransferActivity on allow; RESULT_CANCELED on block/error.
 */
class UpiPinActivity : AppCompatActivity() {
    private lateinit var client: CogniGuardClient
    private lateinit var touchCapture: TouchCapture
    private lateinit var motionCapture: MotionCapture
    private val aeScorerLazy = lazy { AeSequenceScorer(this) }
    private val aeScorer by aeScorerLazy
    private var aeModelVersion: String? = null

    private var sessionToken: String? = null
    private var amount: Double = 0.0
    private var beneficiary: String = ""
    private var isNewPayee: Boolean = false

    private lateinit var statusText: TextView
    private lateinit var pinInput: EditText
    private lateinit var pinConfirmButton: Button

    // Payment OTP card views
    private lateinit var paymentOtpCard: MaterialCardView
    private lateinit var paymentOtpInput: TextInputEditText
    private lateinit var paymentOtpSubmitButton: com.google.android.material.button.MaterialButton
    private lateinit var paymentOtpStatusText: TextView
    private lateinit var paymentOtpCancelLink: TextView

    // Face auth launcher (very_high pre-PIN branch): scan → PIN entry
    private val faceAuthLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { _ ->
        statusText.text = "Face verified. Enter your UPI PIN to confirm ₹$amount to $beneficiary."
        showPinEntry()
    }

    // Face auth launcher (block branch): scan → show block dialog, then finish
    private val blockFaceAuthLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { _ ->
        AlertDialog.Builder(this)
            .setTitle("Transfer Blocked")
            .setMessage("CogniGuard has blocked this transfer due to critical risk signals (high-value transfer to new beneficiary). Your face verification has been recorded. Contact support if you believe this is an error.")
            .setPositiveButton("OK") { _, _ ->
                setResult(RESULT_CANCELED)
                finish()
            }
            .setCancelable(false)
            .show()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)
        setContentView(R.layout.activity_upi_pin)
        client = CogniGuardClient(BuildConfig.API_BASE, BuildConfig.SIGNING_SECRET)

        sessionToken = intent.getStringExtra(EXTRA_SESSION_TOKEN)
        amount = intent.getDoubleExtra(EXTRA_AMOUNT, 0.0)
        beneficiary = intent.getStringExtra(EXTRA_BENEFICIARY) ?: ""
        isNewPayee = intent.getBooleanExtra(EXTRA_IS_NEW_PAYEE, false)

        statusText = findViewById(R.id.upiStatusText)
        pinInput = findViewById(R.id.upiPinInput)
        pinConfirmButton = findViewById(R.id.upiPinConfirmButton)

        touchCapture = TouchCapture()
        pinInput.setOnTouchListener(touchCapture)
        motionCapture = MotionCapture(this)
        motionCapture.start()

        paymentOtpCard = findViewById(R.id.paymentOtpCard)
        paymentOtpInput = findViewById(R.id.paymentOtpInput)
        paymentOtpSubmitButton = findViewById(R.id.paymentOtpSubmitButton)
        paymentOtpStatusText = findViewById(R.id.paymentOtpStatusText)
        paymentOtpCancelLink = findViewById(R.id.paymentOtpCancelLink)
        paymentOtpCancelLink.setOnClickListener {
            statusText.text = "Transfer cancelled."
            setResult(RESULT_CANCELED)
            finish()
        }

        assessRiskAndProceed()
    }

    private fun assessRiskAndProceed() {
        val token = sessionToken ?: run { setResult(RESULT_CANCELED); finish(); return }
        statusText.text = "Verifying session security..."
        pinInput.isEnabled = false
        pinConfirmButton.isEnabled = false

        CoroutineScope(Dispatchers.Main).launch {
            try {
                val behavior = withContext(Dispatchers.IO) { buildPayload("TRANSFER") }
                val result = withContext(Dispatchers.IO) { client.ingest(token, behavior) }
                handleRiskBand(result.body.optString("risk_band", "medium"))
            } catch (_: Exception) {
                statusText.text = "Security check required."
                promptBiometric("FINGERPRINT") { showPinEntry() }
            }
        }
    }

    private fun handleRiskBand(riskBand: String) {
        // High-value transfer to a new beneficiary always requires face auth,
        // regardless of the behavioural session risk band.
        if (isNewPayee && amount >= HUGE_AMOUNT_THRESHOLD) {
            statusText.text = "High-value transfer to new beneficiary detected. Face verification required."
            faceAuthLauncher.launch(Intent(this, FaceAuthActivity::class.java))
            return
        }
        when (riskBand) {
            "low" -> {
                statusText.text = "Enter your UPI PIN to confirm ₹$amount to $beneficiary."
                showPinEntry()
            }
            "medium", "high", "very_high" -> {
                statusText.text = "Please verify your identity before entering your UPI PIN."
                promptBiometric("FINGERPRINT") {
                    statusText.text = "Identity verified. Enter your UPI PIN to confirm ₹$amount to $beneficiary."
                    showPinEntry()
                }
            }
            else -> {
                statusText.text = "Enter your UPI PIN to confirm ₹$amount to $beneficiary."
                showPinEntry()
            }
        }
    }

    private fun showPinEntry() {
        pinInput.isEnabled = true
        pinConfirmButton.isEnabled = true
        pinConfirmButton.setOnClickListener { submitWithPin() }
    }

    /** Real BiometricPrompt with CryptoObject. */
    private fun promptBiometric(factor: String, onSuccess: () -> Unit) {
        val nonce = "upi-pre:${amount}_$beneficiary"
        val sig = BiometricEnrollmentManager.prepareSignature(nonce)
        val executor = ContextCompat.getMainExecutor(this)
        val prompt = BiometricPrompt(
            this, executor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    if (sig != null) {
                        runCatching { result.cryptoObject?.signature?.sign() }
                    }
                    onSuccess()
                }
                override fun onAuthenticationError(code: Int, errString: CharSequence) {
                    statusText.text = "Verification failed: $errString"
                    setResult(RESULT_CANCELED)
                    finish()
                }
                override fun onAuthenticationFailed() { /* user can retry */ }
            },
        )
        val info = BiometricPrompt.PromptInfo.Builder()
            .setTitle("Verify your identity")
            .setSubtitle("Biometric required to authorise ₹$amount UPI transfer")
            .setNegativeButtonText("Cancel")
            .build()
        if (sig != null) {
            prompt.authenticate(info, BiometricPrompt.CryptoObject(sig))
        } else {
            prompt.authenticate(info)
        }
    }

    private fun submitWithPin() {
        val token = sessionToken ?: return
        val pin = pinInput.text.toString()
        if (pin.length < 4) {
            statusText.text = "PIN must be 4–6 digits."
            return
        }
        statusText.text = "Processing payment..."
        pinInput.isEnabled = false
        pinConfirmButton.isEnabled = false

        CoroutineScope(Dispatchers.Main).launch {
            try {
                val behavior = withContext(Dispatchers.IO) { buildPayload("TRANSFER") }
                val scoreResult = withContext(Dispatchers.IO) {
                    client.scorePayment(token, amount, beneficiary, transferType = "UPI", behavior = behavior)
                }
                val body = scoreResult.body
                val scoreAction = body.optString("action")
                when (scoreAction) {
                    "allow" -> {
                        setResult(RESULT_OK)
                        finish()
                    }
                    "verify" -> {
                        val stepUp = body.optJSONObject("step_up")
                        val challengeId = stepUp?.optString("challenge_id") ?: ""
                        val challengeType = stepUp?.optString("challenge_type") ?: ""

                        if (challengeType.equals("OTP", ignoreCase = true) && challengeId.isNotEmpty()) {
                            // Show OTP dialog — user enters the code from their email.
                            // verifyPaymentStepUp sends the OTP to the gateway which validates
                            // it against Redis otp:{challengeId} and consumes it on success.
                            showPaymentOtpDialog(challengeId)
                        } else {
                            // Non-OTP step-up (MPIN / biometric): send pin as assertion
                            val assertion = "MPIN:$pin"
                            val verifyResult = withContext(Dispatchers.IO) {
                                client.verifyPaymentStepUp(challengeId, assertion)
                            }
                            handleVerifyResult(verifyResult.body.optString("action"))
                        }
                    }
                    else -> {
                        AlertDialog.Builder(this@UpiPinActivity)
                            .setTitle("Transfer Blocked")
                            .setMessage("CogniGuard has blocked this transfer due to critical risk signals. Contact support if you believe this is an error.")
                            .setPositiveButton("OK") { _, _ ->
                                setResult(RESULT_CANCELED)
                                finish()
                            }
                            .setCancelable(false)
                            .show()
                    }
                }
            } catch (e: Exception) {
                statusText.text = "Could not reach CogniGuard: ${e.message}"
                pinInput.isEnabled = true
                pinConfirmButton.isEnabled = true
            }
        }
    }

    private fun showPaymentOtpDialog(challengeId: String) {
        statusText.text = "OTP sent to your registered email."
        paymentOtpCard.visibility = View.VISIBLE
        paymentOtpInput.setText("")
        paymentOtpStatusText.visibility = View.GONE
        paymentOtpSubmitButton.isEnabled = true
        paymentOtpSubmitButton.text = "Verify OTP"

        paymentOtpSubmitButton.setOnClickListener {
            val enteredOtp = paymentOtpInput.text.toString().trim()
            if (enteredOtp.isEmpty()) {
                paymentOtpStatusText.text = "Please enter the OTP."
                paymentOtpStatusText.visibility = View.VISIBLE
                return@setOnClickListener
            }
            paymentOtpSubmitButton.isEnabled = false
            paymentOtpSubmitButton.text = "Verifying…"
            paymentOtpStatusText.visibility = View.GONE
            CoroutineScope(Dispatchers.Main).launch {
                try {
                    val verifyResult = withContext(Dispatchers.IO) {
                        client.verifyPaymentStepUp(challengeId, enteredOtp)
                    }
                    val action = verifyResult.body.optString("action")
                    if (action == "allow") {
                        paymentOtpCard.visibility = View.GONE
                        handleVerifyResult(action)
                    } else {
                        paymentOtpStatusText.text = "✗ Incorrect OTP. Please try again."
                        paymentOtpStatusText.visibility = View.VISIBLE
                        paymentOtpSubmitButton.isEnabled = true
                        paymentOtpSubmitButton.text = "Verify OTP"
                        paymentOtpInput.setText("")
                    }
                } catch (e: Exception) {
                    paymentOtpStatusText.text = "Network error: ${e.message}"
                    paymentOtpStatusText.visibility = View.VISIBLE
                    paymentOtpSubmitButton.isEnabled = true
                    paymentOtpSubmitButton.text = "Verify OTP"
                }
            }
        }
    }

    private fun handleVerifyResult(action: String) {
        if (action == "allow") {
            setResult(RESULT_OK)
            finish()
        } else {
            statusText.text = "Verification failed. Please check your OTP or PIN and try again."
            pinInput.isEnabled = true
            pinConfirmButton.isEnabled = true
        }
    }

    private suspend fun buildPayload(action: String): UnsignedBehaviorPayload {
        val device = DeviceFingerprint.compute(this)
        val derivedFeatures = MobileFeatures.extract(
            swipes = touchCapture.drain(),
            motionSamples = motionCapture.drain(),
        )
        if (aeModelVersion == null) {
            aeModelVersion = runCatching { client.getAeModel().body.optString("version") }.getOrNull()
        }
        val aeReconError = runCatching { aeScorer.score(derivedFeatures) }.getOrNull()
        return UnsignedBehaviorPayload(
            channel = "mobile",
            source = "mobile_edge",
            device = device,
            action = ActionBlock(type = action),
            derivedFeatures = derivedFeatures.takeIf { it.isNotEmpty() },
            aeReconError = aeReconError,
            aeModelVersion = if (aeReconError != null) aeModelVersion else null,
            context = ContextBlock(submittedAt = Instant.now().toString(), page = "upi_pin"),
        )
    }

    override fun onDestroy() {
        super.onDestroy()
        motionCapture.stop()
        if (aeScorerLazy.isInitialized()) aeScorer.close()
    }

    companion object {
        const val EXTRA_SESSION_TOKEN = "session_token"
        const val EXTRA_AMOUNT = "amount"
        const val EXTRA_BENEFICIARY = "beneficiary"
        const val EXTRA_IS_NEW_PAYEE = "is_new_payee"
        const val REQUEST_CODE = 1001
        private const val HUGE_AMOUNT_THRESHOLD = 25_000.0  // ₹25k+ to new payee → face auth
    }
}
