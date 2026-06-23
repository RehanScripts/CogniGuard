package com.cogniguard.demoapp

import android.content.Intent
import android.os.Bundle
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.cogniguard.capturesdk.net.CogniGuardClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Customer banking home screen (Phase 31) -- lands here after `allow`/verified login
 * instead of going straight to Transfer, mirroring `web-app/src/pages/Dashboard.tsx`'s
 * place in the nav graph: Login -> Dashboard -> Transfer -> Success, with Dashboard also
 * branching to Security Center and Transaction History. Reads the real, PII-masked
 * `/api/v1/banking` endpoints -- no risk/trust telemetry is shown here. */
class DashboardActivity : AppCompatActivity() {
    private lateinit var client: CogniGuardClient
    private var sessionToken: String? = null
    private var username: String = "genuine"
    private var trustScore: Double = Double.NaN
    private var behaviorMatch: Double = Double.NaN
    private var deviceTrust: Double = Double.NaN

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_dashboard)
        client = CogniGuardClient(BuildConfig.API_BASE, BuildConfig.SIGNING_SECRET)

        sessionToken = intent.getStringExtra(EXTRA_SESSION_TOKEN)
        username = intent.getStringExtra(EXTRA_USERNAME) ?: "genuine"
        trustScore = intent.getDoubleExtra(EXTRA_TRUST_SCORE, Double.NaN)
        behaviorMatch = intent.getDoubleExtra(EXTRA_BEHAVIOR_MATCH, Double.NaN)
        deviceTrust = intent.getDoubleExtra(EXTRA_DEVICE_TRUST, Double.NaN)

        findViewById<TextView>(R.id.headerUsername).text = username
        findViewById<TextView>(R.id.welcomeText).text = "Welcome back, $username"

        val statusText = findViewById<TextView>(R.id.dashboardStatusText)
        val balanceText = findViewById<TextView>(R.id.balanceText)
        val accountSummaryText = findViewById<TextView>(R.id.accountSummaryText)
        val recentTransactionsContainer = findViewById<LinearLayout>(R.id.recentTransactionsContainer)

        setupQuickActions()

        findViewById<TextView>(R.id.viewAllTransactionsLink).setOnClickListener { goToTransactionHistory() }

        val token = sessionToken
        if (token == null) {
            statusText.text = "Session expired -- please log in again."
            return
        }

        statusText.text = "Loading account details..."
        CoroutineScope(Dispatchers.Main).launch {
            try {
                val profileResult = withContext(Dispatchers.IO) { client.getProfile(token) }
                val accountsResult = withContext(Dispatchers.IO) { client.listAccounts(token) }
                val transactionsResult = withContext(Dispatchers.IO) { client.listTransactions(token, limit = 5) }

                if (profileResult.status == 200) {
                    val fullName = profileResult.body.optString("full_name", null)
                    if (!fullName.isNullOrBlank()) {
                        findViewById<TextView>(R.id.welcomeText).text = "Welcome back, $fullName"
                    }
                }

                val accounts = accountsResult.body
                if (accountsResult.status == 200 && accounts.length() > 0) {
                    val account = accounts.getJSONObject(0)
                    balanceText.text =
                        BankingViews.formatInr(
                            account.optDouble("balance").takeIf { !it.isNaN() },
                            account.optString("currency", null),
                        )
                    accountSummaryText.text =
                        "${account.optString("account_type", "Account")} · ${account.optString("masked_account_number", "")}"
                } else {
                    balanceText.text = "--"
                    accountSummaryText.text = "No accounts found."
                }

                val transactions = transactionsResult.body
                recentTransactionsContainer.removeAllViews()
                if (transactionsResult.status == 200 && transactions.length() > 0) {
                    for (i in 0 until transactions.length()) {
                        if (i > 0) BankingViews.addDivider(this@DashboardActivity, recentTransactionsContainer)
                        BankingViews.addTransactionRow(this@DashboardActivity, recentTransactionsContainer, transactions.getJSONObject(i))
                    }
                } else {
                    val empty = TextView(this@DashboardActivity)
                    empty.text = "No transactions yet."
                    empty.textSize = 13f
                    empty.setTextColor(resources.getColor(R.color.cbi_text_muted, theme))
                    recentTransactionsContainer.addView(empty)
                }

                statusText.text = ""
            } catch (e: Exception) {
                statusText.text = "Could not load account details: ${e.message}"
            }
        }
    }

    private fun setupQuickActions() {
        val row = findViewById<LinearLayout>(R.id.quickActionsRow)
        BankingViews.addQuickAction(this, row, "T", R.drawable.bg_badge_circle_primary, "Transfer") { goToTransfer() }
        BankingViews.addQuickAction(this, row, "B", R.drawable.bg_badge_circle_accent, "Beneficiaries") { goToTransactionHistory() }
        BankingViews.addQuickAction(this, row, "S", R.drawable.bg_badge_circle_success, "Security") { goToSecurityCenter() }
        BankingViews.addQuickAction(this, row, "H", R.drawable.bg_badge_circle_primary, "History") { goToTransactionHistory() }
    }

    private fun goToTransfer() {
        val intent = Intent(this, TransferActivity::class.java)
        intent.putExtra(TransferActivity.EXTRA_SESSION_TOKEN, sessionToken)
        intent.putExtra(TransferActivity.EXTRA_USERNAME, username)
        startActivity(intent)
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

    private fun goToTransactionHistory() {
        val intent = Intent(this, TransactionHistoryActivity::class.java)
        intent.putExtra(TransactionHistoryActivity.EXTRA_SESSION_TOKEN, sessionToken)
        intent.putExtra(TransactionHistoryActivity.EXTRA_USERNAME, username)
        startActivity(intent)
    }

    companion object {
        const val EXTRA_SESSION_TOKEN = "session_token"
        const val EXTRA_USERNAME = "username"
        const val EXTRA_TRUST_SCORE = "trust_score"
        const val EXTRA_BEHAVIOR_MATCH = "behavior_match"
        const val EXTRA_DEVICE_TRUST = "device_trust"
    }
}
