package com.cogniguard.demoapp

import android.content.Intent
import android.os.Bundle
import android.util.Base64
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import com.google.android.material.card.MaterialCardView
import com.google.android.material.chip.ChipGroup
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
import org.json.JSONObject
import java.time.Instant

/** Demo IB app transfer screen -- parity with `web-app/src/pages/Payment.tsx`
 * (Implementation.md Phase 18): beneficiary VPA + amount, `POST /api/v1/payment/score`,
 * and interactive panels for whichever `txn_controls` fired. `coercionPanel`/
 * `manualAmountPanel` mirror `CoercionCheck.tsx`/`ManualAmountEntry.tsx`: both are resolved
 * entirely client-side against the one `scorePayment` response already received (no second
 * network call) via `coercionAnswered`/`confirmedManualAmount`, exactly like `Payment.tsx`'s
 * local React state. `cooling_until` stays a plain notice (`CoolingNotice.tsx` has no
 * confirm action either -- it's a timed hold, not a yes/no). `action == "verify"` drives a
 * real `BiometricPrompt`/demo-OTP step-up against `/api/v1/payment/step-up/verify`
 * (parity with `LoginActivity.handleVerify` and web's `StepUp.tsx` transaction branch)
 * before any `txn_controls` panel is shown. */
class TransferActivity : AppCompatActivity() {
    private lateinit var client: CogniGuardClient
    private lateinit var touchCapture: TouchCapture
    private lateinit var motionCapture: MotionCapture
    private var sessionToken: String? = null
    private var username: String = "genuine"
    private var pendingAmount: Double = 0.0
    private var pendingBeneficiary: String = ""

    private val upiPinLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            if (result.resultCode == RESULT_OK) {
                knownBeneficiaries.add(pendingBeneficiary)
                goToSuccess(pendingAmount, pendingBeneficiary)
            } else {
                resultText.text = "UPI transfer cancelled."
            }
        }
    private val aeScorerLazy = lazy { AeSequenceScorer(this) }
    private val aeScorer by aeScorerLazy
    private var aeModelVersion: String? = null

    private var lastBody: JSONObject? = null
    private var lastAmount: Double = 0.0
    private var lastBeneficiary: String = ""
    private var coercionAnswered: Boolean = false
    private var confirmedManualAmount: Boolean = false

    private lateinit var resultText: TextView
    private lateinit var controlsText: TextView
    private lateinit var coercionPanel: MaterialCardView
    private lateinit var manualAmountPanel: MaterialCardView
    private lateinit var manualAmountInput: EditText
    private lateinit var transferTypeChipGroup: ChipGroup

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)
        setContentView(R.layout.activity_transfer)
        client = CogniGuardClient(BuildConfig.API_BASE, BuildConfig.SIGNING_SECRET)
        sessionToken = intent.getStringExtra(EXTRA_SESSION_TOKEN)
        username = intent.getStringExtra(EXTRA_USERNAME) ?: "genuine"

        val beneficiaryInput = findViewById<EditText>(R.id.beneficiaryInput)
        val amountInput = findViewById<EditText>(R.id.amountInput)
        val sendButton = findViewById<Button>(R.id.sendButton)
        resultText = findViewById(R.id.resultText)
        controlsText = findViewById(R.id.controlsText)
        coercionPanel = findViewById(R.id.coercionPanel)
        manualAmountPanel = findViewById(R.id.manualAmountPanel)
        manualAmountInput = findViewById(R.id.manualAmountInput)
        transferTypeChipGroup = findViewById(R.id.transferTypeChipGroup)

        findViewById<TextView>(R.id.coercionPrompt).text = ""
        findViewById<Button>(R.id.coercionConfirmButton).setOnClickListener {
            coercionAnswered = true
            lastBody?.let { renderResult(it) }
        }
        findViewById<Button>(R.id.coercionCancelButton).setOnClickListener {
            // Mirrors Payment.tsx's onCancel={() => setResponse(null)} -- drop the result
            // entirely rather than proceeding; a coerced customer should land back on a
            // blank form, not a half-resolved transfer.
            lastBody = null
            coercionPanel.visibility = View.GONE
            manualAmountPanel.visibility = View.GONE
            resultText.text = "Transfer cancelled. If someone is instructing you to do this, contact your branch before retrying."
            controlsText.text = ""
        }
        findViewById<Button>(R.id.confirmAmountButton).setOnClickListener {
            val typed = manualAmountInput.text.toString().toDoubleOrNull()
            if (typed != null && typed == lastAmount) {
                confirmedManualAmount = true
                lastBody?.let { renderResult(it) }
            } else {
                controlsText.text = "Amount doesn't match -- please re-type it exactly."
            }
        }

        touchCapture = TouchCapture()
        beneficiaryInput.setOnTouchListener(touchCapture)
        amountInput.setOnTouchListener(touchCapture)
        motionCapture = MotionCapture(this)
        motionCapture.start()

        sendButton.setOnClickListener {
            val token = sessionToken
            if (token == null) {
                resultText.text = "Session expired -- please log in again."
                return@setOnClickListener
            }
            val amount = amountInput.text.toString().toDoubleOrNull()
            if (amount == null) {
                resultText.text = "Enter a valid amount."
                return@setOnClickListener
            }
            val beneficiary = beneficiaryInput.text.toString()
            val transferType = selectedTransferType()

            resultText.text = "Scoring..."
            controlsText.text = ""
            coercionPanel.visibility = View.GONE
            manualAmountPanel.visibility = View.GONE
            coercionAnswered = false
            confirmedManualAmount = false
            manualAmountInput.setText("")

            // UPI payments go through the adaptive pre-PIN re-auth gate (Phase B3).
            if (transferType == "UPI") {
                pendingAmount = amount
                pendingBeneficiary = beneficiary
                val intent = Intent(this, UpiPinActivity::class.java).apply {
                    putExtra(UpiPinActivity.EXTRA_SESSION_TOKEN, token)
                    putExtra(UpiPinActivity.EXTRA_AMOUNT, amount)
                    putExtra(UpiPinActivity.EXTRA_BENEFICIARY, beneficiary)
                    val handle = beneficiary.substringBefore("@").lowercase()
                    val isNew = beneficiary !in knownBeneficiaries && handle !in trustedHandles
                    putExtra(UpiPinActivity.EXTRA_IS_NEW_PAYEE, isNew)
                }
                upiPinLauncher.launch(intent)
                return@setOnClickListener
            }

            CoroutineScope(Dispatchers.Main).launch {
                try {
                    val behavior = withContext(Dispatchers.IO) { buildBehaviorPayload(action = "TRANSFER") }
                    val result =
                        withContext(Dispatchers.IO) {
                            client.scorePayment(
                                token,
                                amount,
                                beneficiary,
                                transferType = transferType,
                                behavior = behavior,
                            )
                        }
                    lastAmount = amount
                    lastBeneficiary = beneficiary
                    renderResult(result.body)
                } catch (e: Exception) {
                    resultText.text = "Could not reach CogniGuard: ${e.message}"
                }
            }
        }
    }

    private fun selectedTransferType(): String =
        when (transferTypeChipGroup.checkedChipId) {
            R.id.chipNeft -> "NEFT"
            R.id.chipRtgs -> "RTGS"
            R.id.chipUpi -> "UPI"
            else -> "IMPS"
        }

    private fun renderResult(body: JSONObject) {
        lastBody = body
        val action = body.optString("action")
        val riskBand = body.optString("risk_band")
        val riskScore = body.optDouble("risk_score")
        resultText.text = "action: $action  risk: $riskBand ($riskScore)"

        // Identity assurance (OTP/Fingerprint/Face) resolves before the transaction-
        // fraud-layer controls below -- those only make sense once the transfer is
        // actually authenticated.
        if (action == "verify") {
            handleVerify(body)
            return
        }

        val controls = body.optJSONObject("txn_controls")
        val needsCoercionCheck = controls?.optBoolean("coercion_check") == true && !coercionAnswered
        val needsManualAmount = controls?.optBoolean("manual_amount") == true && !confirmedManualAmount
        val isCooling = controls != null && !controls.isNull("cooling_until")

        coercionPanel.visibility = if (needsCoercionCheck) View.VISIBLE else View.GONE
        manualAmountPanel.visibility = if (!needsCoercionCheck && needsManualAmount) View.VISIBLE else View.GONE
        if (needsCoercionCheck) {
            findViewById<TextView>(R.id.coercionPrompt).text =
                "You're sending ₹$lastAmount to a payee added a short while ago. Is someone instructing you to do this right now?"
        }

        controlsText.text =
            when {
                needsCoercionCheck || needsManualAmount -> ""
                isCooling -> "Cooling period until ${controls?.optString("cooling_until")}."
                else -> ""
            }

        // Clean allow with no pending coercion-check/manual-amount/cooling control -> the
        // transfer is genuinely done; show the production-style success screen instead of
        // leaving the customer on the raw risk/controls text above. Resolved purely against
        // this same response (no re-call to scorePayment), exactly like Payment.tsx.
        if (action == "allow" && !needsCoercionCheck && !needsManualAmount && !isCooling) {
            goToSuccess(lastAmount, lastBeneficiary)
        }
    }

    /** `verify` on a transfer (parity with `LoginActivity.handleVerify`): phishing-
     * resistant factors go through a real BiometricPrompt (fingerprint sensor or face
     * unlock -- whichever the device has enrolled, the gateway only knows "FINGERPRINT"/
     * "PASSKEY"); OTP/MPIN/VOICE_READBACK fall back to the demo code the gateway
     * accepts. The resolved response feeds back into `renderResult` so any still-
     * pending coercion/manual-amount/cooling controls continue exactly as before. */
    private fun handleVerify(body: JSONObject) {
        val stepUp = body.optJSONObject("step_up")
        if (stepUp == null) {
            resultText.text = "Step-up required."
            return
        }
        val challengeId = stepUp.optString("challenge_id")
        val factor = stepUp.optString("challenge_type")
        resultText.text = "Verify it's you to continue: $factor"
        if (factor == "FINGERPRINT" || factor == "FACE" || factor == "PASSKEY") {
            promptBiometric(factor, challengeId) { assertion -> submitPaymentStepUp(challengeId, assertion) }
        } else {
            // Demo OTP/MPIN code (gateway accepts "123456"); see web StepUp parity.
            submitPaymentStepUp(challengeId, "123456")
        }
    }

    /** Real BiometricPrompt with CryptoObject: the KeyStore private key (setUserAuthenticationRequired=true)
     *  is used to sign [nonceToSign] (the payment challenge_id). The OS enforces a fresh biometric scan
     *  before the key can complete the signature. Falls back to plain authenticate if key not yet bound. */
    private fun promptBiometric(factor: String, nonceToSign: String, onSuccess: (assertion: String) -> Unit) {
        val sig = if (nonceToSign.isNotEmpty()) BiometricEnrollmentManager.prepareSignature(nonceToSign) else null
        val executor = ContextCompat.getMainExecutor(this)
        val prompt = BiometricPrompt(
            this, executor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    val assertion = if (sig != null) {
                        runCatching {
                            val bytes = result.cryptoObject?.signature?.sign()
                            "keystore-sig:" + Base64.encodeToString(bytes, Base64.NO_WRAP)
                        }.getOrElse { "biometric-$factor-ok" }
                    } else {
                        "biometric-$factor-ok"
                    }
                    onSuccess(assertion)
                }
                override fun onAuthenticationError(code: Int, errString: CharSequence) {
                    resultText.text = "Step-up failed: $errString"
                }
                override fun onAuthenticationFailed() {
                    resultText.text = "Biometric not recognised — try again."
                }
            },
        )
        val info = BiometricPrompt.PromptInfo.Builder()
            .setTitle("Verify it's you")
            .setSubtitle("Confirm your identity to continue ($factor)")
            .setNegativeButtonText("Cancel")
            .build()
        if (sig != null) {
            prompt.authenticate(info, BiometricPrompt.CryptoObject(sig))
        } else {
            prompt.authenticate(info)
        }
    }

    private fun submitPaymentStepUp(challengeId: String, assertion: String) {
        CoroutineScope(Dispatchers.Main).launch {
            try {
                val res = withContext(Dispatchers.IO) { client.verifyPaymentStepUp(challengeId, assertion) }
                when (res.body.optString("action")) {
                    "allow" -> renderResult(res.body)
                    "block" -> resultText.text = "Verification failed -- transfer denied."
                    else -> resultText.text = "Incorrect code, try again."
                }
            } catch (e: Exception) {
                resultText.text = "Could not reach CogniGuard: ${e.message}"
            }
        }
    }

    private fun goToSuccess(amount: Double, beneficiary: String) {
        val intent = Intent(this, TransferSuccessActivity::class.java)
        intent.putExtra(TransferSuccessActivity.EXTRA_AMOUNT, amount)
        intent.putExtra(TransferSuccessActivity.EXTRA_BENEFICIARY, beneficiary)
        intent.putExtra(TransferSuccessActivity.EXTRA_USERNAME, username)
        startActivity(intent)
        finish()
    }

    private suspend fun buildBehaviorPayload(action: String): UnsignedBehaviorPayload {
        val device = DeviceFingerprint.compute(this)
        val derivedFeatures =
            MobileFeatures.extract(swipes = touchCapture.drain(), motionSamples = motionCapture.drain())
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
            context = ContextBlock(submittedAt = Instant.now().toString(), page = "transfer"),
        )
    }

    override fun onDestroy() {
        super.onDestroy()
        motionCapture.stop()
        if (aeScorerLazy.isInitialized()) aeScorer.close()
    }

    companion object {
        const val EXTRA_SESSION_TOKEN = "session_token"
        const val EXTRA_USERNAME = "username"
        // Beneficiaries the user has successfully paid before in this session → known payee
        val knownBeneficiaries: MutableSet<String> = mutableSetOf()
        // Trusted payee handles (name before @) that are always treated as known — demo seed
        private val trustedHandles: Set<String> = setOf("ojas")
    }
}
