package com.cogniguard.demoapp

import android.os.Bundle
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.cogniguard.capturesdk.net.CogniGuardClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Customer-facing Security Center (Phase 31) -- showcases CogniGuard's value
 * proposition with qualitative protection status only. Deliberately never renders a
 * model name, raw score, or AE/IF metric: [trustScore]/[behaviorMatch]/[deviceTrust]
 * (passed in from the login decision) are only ever mapped to a coarse good/neutral
 * label, never printed as numbers, on this screen. */
class SecurityCenterActivity : AppCompatActivity() {
    private lateinit var client: CogniGuardClient
    private var sessionToken: String? = null
    private var username: String = "genuine"
    private var trustScore: Double = Double.NaN
    private var behaviorMatch: Double = Double.NaN
    private var deviceTrust: Double = Double.NaN

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)
        setContentView(R.layout.activity_security_center)
        client = CogniGuardClient(BuildConfig.API_BASE, BuildConfig.SIGNING_SECRET)

        sessionToken = intent.getStringExtra(EXTRA_SESSION_TOKEN)
        username = intent.getStringExtra(EXTRA_USERNAME) ?: "genuine"
        trustScore = intent.getDoubleExtra(EXTRA_TRUST_SCORE, Double.NaN)
        behaviorMatch = intent.getDoubleExtra(EXTRA_BEHAVIOR_MATCH, Double.NaN)
        deviceTrust = intent.getDoubleExtra(EXTRA_DEVICE_TRUST, Double.NaN)

        findViewById<TextView>(R.id.headerUsername).text = username
        findViewById<LinearLayout>(R.id.headerLogoArea).setOnClickListener { finish() }
        findViewById<TextView>(R.id.backToDashboard).setOnClickListener { finish() }

        renderStatusRows()

        val statusText = findViewById<TextView>(R.id.securityStatusText)
        val lastLoginText = findViewById<TextView>(R.id.lastLoginText)
        val trustedDevicesContainer = findViewById<LinearLayout>(R.id.trustedDevicesContainer)
        val activeSessionsContainer = findViewById<LinearLayout>(R.id.activeSessionsContainer)
        lastLoginText.text = "This device · Just now"

        val token = sessionToken
        if (token == null) {
            statusText.text = "Session expired -- please log in again."
            return
        }

        CoroutineScope(Dispatchers.Main).launch {
            try {
                val result = withContext(Dispatchers.IO) { client.getSecuritySettings(token) }
                if (result.status == 200) {
                    val devices = result.body.optJSONArray("trusted_devices")
                    trustedDevicesContainer.removeAllViews()
                    if (devices != null && devices.length() > 0) {
                        for (i in 0 until devices.length()) {
                            if (i > 0) BankingViews.addDivider(this@SecurityCenterActivity, trustedDevicesContainer)
                            BankingViews.addDeviceRow(this@SecurityCenterActivity, trustedDevicesContainer, devices.getJSONObject(i))
                        }
                    } else {
                        addEmptyRow(trustedDevicesContainer, "No trusted devices yet.")
                    }

                    val sessions = result.body.optJSONArray("active_sessions")
                    activeSessionsContainer.removeAllViews()
                    if (sessions != null && sessions.length() > 0) {
                        for (i in 0 until sessions.length()) {
                            if (i > 0) BankingViews.addDivider(this@SecurityCenterActivity, activeSessionsContainer)
                            BankingViews.addSessionRow(this@SecurityCenterActivity, activeSessionsContainer, sessions.getJSONObject(i))
                        }
                        val first = sessions.getJSONObject(0)
                        lastLoginText.text =
                            "${BankingViews.safeOptString(first, "device_label", "This device")} · ${BankingViews.safeOptString(first, "location", "Unknown location")} · " +
                                BankingViews.formatDateTime(BankingViews.safeOptStringOrNull(first, "started_at"))
                    } else {
                        addEmptyRow(activeSessionsContainer, "No active sessions.")
                    }
                }
                statusText.text = ""
            } catch (e: Exception) {
                statusText.text = "Could not load security details: ${e.message}"
            }
        }
    }

    private fun addEmptyRow(container: LinearLayout, message: String) {
        val tv = TextView(this)
        tv.text = message
        tv.textSize = 13f
        tv.setTextColor(resources.getColor(R.color.cbi_text_muted, theme))
        container.addView(tv)
    }

    /** Maps raw decision-layer signals to coarse, customer-facing labels only -- the
     * numeric thresholds here are display-bucketing, not security policy (the gateway's
     * actual `verify`/`block` decision already happened before this screen renders). */
    private fun renderStatusRows() {
        val container = findViewById<LinearLayout>(R.id.statusRowsContainer)

        val deviceGood = !deviceTrust.isNaN() && deviceTrust >= 60.0
        BankingViews.addStatusRow(
            this, container, "Device trust",
            if (deviceTrust.isNaN()) "Checking" else if (deviceGood) "Trusted" else "Unrecognized",
            deviceGood,
        )

        val behaviorGood = !behaviorMatch.isNaN() && behaviorMatch >= 50.0
        BankingViews.addStatusRow(
            this, container, "Behavioral verification",
            if (behaviorMatch.isNaN()) "Calibrating" else if (behaviorGood) "Active" else "Reviewing",
            behaviorGood,
        )

        val identityGood = !trustScore.isNaN() && trustScore >= 60.0
        BankingViews.addStatusRow(
            this, container, "Continuous identity verification",
            if (trustScore.isNaN()) "Calibrating" else if (identityGood) "Verified" else "Monitoring",
            identityGood,
        )
    }

    companion object {
        const val EXTRA_SESSION_TOKEN = "session_token"
        const val EXTRA_USERNAME = "username"
        const val EXTRA_TRUST_SCORE = "trust_score"
        const val EXTRA_BEHAVIOR_MATCH = "behavior_match"
        const val EXTRA_DEVICE_TRUST = "device_trust"
    }
}
