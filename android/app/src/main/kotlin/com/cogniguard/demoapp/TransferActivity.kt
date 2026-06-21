package com.cogniguard.demoapp

import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.cogniguard.capturesdk.MotionCapture
import com.cogniguard.capturesdk.TouchCapture
import com.cogniguard.capturesdk.edge.MobileFeatures
import com.cogniguard.capturesdk.fingerprint.DeviceFingerprint
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
 * and a single combined notice for whichever `txn_controls` fired (this native demo's
 * simplified stand-in for the web app's three separate interactive coercion-check /
 * manual-amount-entry / cooling-period components -- see `activity_transfer.xml`). */
class TransferActivity : AppCompatActivity() {
    private lateinit var client: CogniGuardClient
    private lateinit var touchCapture: TouchCapture
    private lateinit var motionCapture: MotionCapture
    private var sessionToken: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_transfer)
        client = CogniGuardClient(BuildConfig.API_BASE, BuildConfig.SIGNING_SECRET)
        sessionToken = intent.getStringExtra(EXTRA_SESSION_TOKEN)

        val beneficiaryInput = findViewById<EditText>(R.id.beneficiaryInput)
        val amountInput = findViewById<EditText>(R.id.amountInput)
        val sendButton = findViewById<Button>(R.id.sendButton)
        val resultText = findViewById<TextView>(R.id.resultText)
        val controlsText = findViewById<TextView>(R.id.controlsText)

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

            CoroutineScope(Dispatchers.Main).launch {
                try {
                    val behavior = buildBehaviorPayload(action = "TRANSFER")
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
                    renderResult(result.body, resultText, controlsText)
                } catch (e: Exception) {
                    resultText.text = "Could not reach CogniGuard: ${e.message}"
                }
            }
        }
    }

    private fun renderResult(body: JSONObject, resultText: TextView, controlsText: TextView) {
        val action = body.optString("action")
        val riskBand = body.optString("risk_band")
        val riskScore = body.optDouble("risk_score")
        resultText.text = "action: $action  risk: $riskBand ($riskScore)"

        val controls = body.optJSONObject("txn_controls")
        controlsText.text =
            when {
                controls == null -> ""
                controls.optBoolean("coercion_check") -> "Coercion check required: are you sending this yourself?"
                controls.optBoolean("manual_amount") -> "Please re-enter the amount manually to confirm."
                !controls.isNull("cooling_until") -> "Cooling period until ${controls.optString("cooling_until")}."
                else -> ""
            }
    }

    private fun buildBehaviorPayload(action: String): UnsignedBehaviorPayload {
        val device = DeviceFingerprint.compute(this)
        val derivedFeatures =
            MobileFeatures.extract(swipes = touchCapture.drain(), motionSamples = motionCapture.drain())
        return UnsignedBehaviorPayload(
            channel = "mobile",
            source = "mobile_edge",
            device = device,
            action = ActionBlock(type = action),
            derivedFeatures = derivedFeatures.takeIf { it.isNotEmpty() },
            aeReconError = null, // wired once AutoencoderTFLite is loaded with a real model.tflite asset
            aeModelVersion = null,
            context = ContextBlock(submittedAt = Instant.now().toString(), page = "transfer"),
        )
    }

    override fun onDestroy() {
        super.onDestroy()
        motionCapture.stop()
    }

    companion object {
        const val EXTRA_SESSION_TOKEN = "session_token"
    }
}
