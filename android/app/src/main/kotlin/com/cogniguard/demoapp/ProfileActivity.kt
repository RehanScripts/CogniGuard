package com.cogniguard.demoapp

import android.content.Intent
import android.widget.LinearLayout
import android.widget.TextView
import android.os.Bundle
import androidx.core.content.ContextCompat
import com.cogniguard.capturesdk.net.CogniGuardClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Customer profile screen (Phase 31) -- parity with web-app/src/pages/Profile.tsx.
 * Shows avatar initials, personal info, linked accounts, and a security-settings
 * navigation shortcut. Reads /api/v1/banking/profile + /api/v1/banking/accounts. */
class ProfileActivity : MonitoredSessionActivity() {
    override val monitoredPage = "profile"

    companion object {
        const val EXTRA_SESSION_TOKEN = "session_token"
        const val EXTRA_USERNAME = "username"
        const val EXTRA_TRUST_SCORE = "trust_score"
        const val EXTRA_BEHAVIOR_MATCH = "behavior_match"
        const val EXTRA_DEVICE_TRUST = "device_trust"
    }

    private lateinit var client: CogniGuardClient
    private var sessionToken: String? = null
    private var username: String = "genuine"
    private var trustScore: Double = Double.NaN
    private var behaviorMatch: Double = Double.NaN
    private var deviceTrust: Double = Double.NaN

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)
        setContentView(R.layout.activity_profile)
        client = CogniGuardClient(BuildConfig.API_BASE, BuildConfig.SIGNING_SECRET)

        sessionToken = intent.getStringExtra(EXTRA_SESSION_TOKEN)
        username = intent.getStringExtra(EXTRA_USERNAME) ?: "genuine"
        trustScore = intent.getDoubleExtra(EXTRA_TRUST_SCORE, Double.NaN)
        behaviorMatch = intent.getDoubleExtra(EXTRA_BEHAVIOR_MATCH, Double.NaN)
        deviceTrust = intent.getDoubleExtra(EXTRA_DEVICE_TRUST, Double.NaN)

        findViewById<TextView>(R.id.headerUsername).text = username
        findViewById<TextView>(R.id.backToDashboard).setOnClickListener { finish() }
        findViewById<com.google.android.material.card.MaterialCardView>(R.id.securitySettingsRow)
            .setOnClickListener { goToSecurityCenter() }

        loadProfile()
    }

    private fun loadProfile() {
        val token = sessionToken
        val statusText = findViewById<TextView>(R.id.profileStatusText)
        if (token == null) {
            statusText.text = "Session expired -- please log in again."
            return
        }
        statusText.text = "Loading profile..."
        CoroutineScope(Dispatchers.Main).launch {
            try {
                val profileResult = withContext(Dispatchers.IO) { client.getProfile(token) }
                val accountsResult = withContext(Dispatchers.IO) { client.listAccounts(token) }

                statusText.text = ""

                if (profileResult.status == 200) {
                    val body = profileResult.body
                    val fullName = BankingViews.safeOptStringOrNull(body, "full_name")
                        ?.ifBlank { null } ?: username
                    val email = BankingViews.safeOptStringOrNull(body, "email")
                    val customerRef = BankingViews.safeOptStringOrNull(body, "customer_ref")
                    val kycLevel = BankingViews.safeOptStringOrNull(body, "kyc_level")
                    val accountStatus = BankingViews.safeOptString(body, "account_status", "active")

                    // Avatar initials (up to 2 chars)
                    val initials = fullName.split(" ")
                        .mapNotNull { it.firstOrNull()?.uppercaseChar()?.toString() }
                        .take(2)
                        .joinToString("")
                        .ifBlank { fullName.take(1).uppercase() }
                    findViewById<TextView>(R.id.avatarText).text = initials
                    findViewById<TextView>(R.id.profileFullName).text = fullName

                    // KYC badge
                    if (!kycLevel.isNullOrBlank()) {
                        val badge = findViewById<TextView>(R.id.profileKycBadge)
                        badge.text = "${kycLevel.uppercase()} VERIFIED"
                        badge.visibility = android.view.View.VISIBLE
                    }

                    // Account status chip
                    val statusChip = findViewById<TextView>(R.id.profileAccountStatus)
                    statusChip.text = accountStatus.replaceFirstChar { it.uppercaseChar() }
                    val isActive = accountStatus.lowercase() == "active"
                    statusChip.setTextColor(
                        ContextCompat.getColor(this@ProfileActivity, if (isActive) R.color.success_green else R.color.cbi_accent)
                    )

                    // Personal info rows
                    findViewById<TextView>(R.id.profileInfoName).text = fullName
                    if (!email.isNullOrBlank()) {
                        val atIdx = email.indexOf('@')
                        val masked = if (atIdx > 2) "${email.take(3)}***${email.substring(atIdx)}" else email
                        findViewById<TextView>(R.id.profileInfoEmail).text = masked
                    }
                    findViewById<TextView>(R.id.profileInfoUsername).text = customerRef ?: username
                    findViewById<TextView>(R.id.profileInfoCustomerRef).text = customerRef ?: "--"
                } else {
                    statusText.text = "Could not load profile (${profileResult.status})."
                    // still show username as fallback
                    val initials = username.take(2).uppercase()
                    findViewById<TextView>(R.id.avatarText).text = initials
                    findViewById<TextView>(R.id.profileFullName).text = username
                    findViewById<TextView>(R.id.profileInfoUsername).text = username
                }

                // Linked accounts
                val accountsContainer = findViewById<LinearLayout>(R.id.profileAccountsContainer)
                accountsContainer.removeAllViews()
                if (accountsResult.status == 200 && accountsResult.body.length() > 0) {
                    for (i in 0 until accountsResult.body.length()) {
                        val acc = accountsResult.body.getJSONObject(i)
                        if (i > 0) BankingViews.addDivider(this@ProfileActivity, accountsContainer)
                        addAccountRow(accountsContainer, acc)
                    }
                } else {
                    val empty = TextView(this@ProfileActivity)
                    empty.text = "No linked accounts found."
                    empty.textSize = 13f
                    empty.setTextColor(ContextCompat.getColor(this@ProfileActivity, R.color.cbi_text_muted))
                    accountsContainer.addView(empty)
                }
            } catch (e: Exception) {
                findViewById<TextView>(R.id.profileStatusText).text = "Could not load profile: ${e.message}"
            }
        }
    }

    private fun addAccountRow(container: LinearLayout, acc: org.json.JSONObject) {
        val row = LinearLayout(this)
        row.orientation = LinearLayout.HORIZONTAL
        row.gravity = android.view.Gravity.CENTER_VERTICAL
        val rowParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        )
        rowParams.topMargin = BankingViews.dp(this, 4)
        rowParams.bottomMargin = BankingViews.dp(this, 4)
        row.layoutParams = rowParams

        // Icon
        val icon = TextView(this)
        icon.text = "&#9829;".let { "♥" }
        icon.setBackgroundResource(R.drawable.bg_badge_circle_primary)
        icon.setTextColor(ContextCompat.getColor(this, R.color.white))
        icon.textSize = 14f
        icon.gravity = android.view.Gravity.CENTER
        val iconParams = LinearLayout.LayoutParams(BankingViews.dp(this, 40), BankingViews.dp(this, 40))
        iconParams.marginEnd = BankingViews.dp(this, 12)
        icon.layoutParams = iconParams

        // Text column
        val textCol = LinearLayout(this)
        textCol.orientation = LinearLayout.VERTICAL
        textCol.layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)

        val accType = BankingViews.safeOptString(acc, "account_type", "Account")
        val masked = BankingViews.safeOptString(acc, "masked_account_number", "--")
        val typeLabel = TextView(this)
        typeLabel.text = "${accType.replaceFirstChar { it.uppercaseChar() }} Account"
        typeLabel.textSize = 14f
        typeLabel.setTextColor(ContextCompat.getColor(this, R.color.cbi_text))
        typeLabel.setTypeface(typeLabel.typeface, android.graphics.Typeface.BOLD)
        val maskedLabel = TextView(this)
        maskedLabel.text = masked
        maskedLabel.textSize = 12f
        maskedLabel.typeface = android.graphics.Typeface.MONOSPACE
        maskedLabel.setTextColor(ContextCompat.getColor(this, R.color.cbi_text_muted))
        textCol.addView(typeLabel)
        textCol.addView(maskedLabel)

        // Balance
        val amount = BankingViews.formatInr(
            acc.optDouble("balance").takeIf { !it.isNaN() },
            BankingViews.safeOptStringOrNull(acc, "currency")
        )
        val balanceView = TextView(this)
        balanceView.text = amount
        balanceView.textSize = 15f
        balanceView.setTextColor(ContextCompat.getColor(this, R.color.cbi_primary))
        balanceView.setTypeface(balanceView.typeface, android.graphics.Typeface.BOLD)
        val balParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        balParams.marginStart = BankingViews.dp(this, 8)
        balanceView.layoutParams = balParams

        row.addView(icon)
        row.addView(textCol)
        row.addView(balanceView)
        container.addView(row)
    }

    private fun goToSecurityCenter() {
        val intent = Intent(this, SecurityCenterActivity::class.java)
        intent.putExtra(SecurityCenterActivity.EXTRA_SESSION_TOKEN, sessionToken)
        intent.putExtra(SecurityCenterActivity.EXTRA_USERNAME, username)
        if (!trustScore.isNaN()) intent.putExtra(SecurityCenterActivity.EXTRA_TRUST_SCORE, trustScore)
        if (!behaviorMatch.isNaN()) intent.putExtra(SecurityCenterActivity.EXTRA_BEHAVIOR_MATCH, behaviorMatch)
        if (!deviceTrust.isNaN()) intent.putExtra(SecurityCenterActivity.EXTRA_DEVICE_TRUST, deviceTrust)
        startActivity(intent)
    }
}
