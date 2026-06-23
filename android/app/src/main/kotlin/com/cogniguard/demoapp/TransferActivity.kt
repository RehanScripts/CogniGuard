package com.cogniguard.demoapp

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
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
 * confirm action either -- it's a timed hold, not a yes/no). */
class TransferActivity : AppCompatActivity() {
    private lateinit var client: CogniGuardClient
    private lateinit var touchCapture: TouchCapture
    private lateinit var motionCapture: MotionCapture
    private var sessionToken: String? = null
    private var username: String = "genuine"
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
    private lateinit var coercionPanel: LinearLayout
    private lateinit var manualAmountPanel: LinearLayout
    private lateinit var manualAmountInput: EditText

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
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
            resultText.text = "Scoring..."
            controlsText.text = ""
            coercionPanel.visibility = View.GONE
            manualAmountPanel.visibility = View.GONE
            coercionAnswered = false
            confirmedManualAmount = false
            manualAmountInput.setText("")

            CoroutineScope(Dispatchers.Main).launch {
                try {
                    val behavior = withContext(Dispatchers.IO) { buildBehaviorPayload(action = "TRANSFER") }
                    val result =
                        withContext(Dispatchers.IO) {
                            client.scorePayment(
                                token,
                                amount,
                                beneficiaryInput.text.toString(),
                                transferType = "UPI",
                                behavior = behavior,
                            )
                        }
                    lastAmount = amount
                    lastBeneficiary = beneficiaryInput.text.toString()
                    renderResult(result.body)
                } catch (e: Exception) {
                    resultText.text = "Could not reach CogniGuard: ${e.message}"
                }
            }
        }
    }

    private fun renderResult(body: JSONObject) {
        lastBody = body
        val action = body.optString("action")
        val riskBand = body.optString("risk_band")
        val riskScore = body.optDouble("risk_score")
        resultText.text = "action: $action  risk: $riskBand ($riskScore)"

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
    }
}
