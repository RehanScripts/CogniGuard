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

/** Transaction history + beneficiaries (Phase 31, optional Dashboard sub-screen) --
 * parity with `web-app/src/pages/Transactions.tsx`, same real `/api/v1/banking/*` data. */
class TransactionHistoryActivity : AppCompatActivity() {
    private lateinit var client: CogniGuardClient
    private var sessionToken: String? = null
    private var username: String = "genuine"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_transaction_history)
        client = CogniGuardClient(BuildConfig.API_BASE, BuildConfig.SIGNING_SECRET)

        sessionToken = intent.getStringExtra(EXTRA_SESSION_TOKEN)
        username = intent.getStringExtra(EXTRA_USERNAME) ?: "genuine"

        findViewById<TextView>(R.id.headerUsername).text = username
        findViewById<LinearLayout>(R.id.headerLogoArea).setOnClickListener { finish() }
        findViewById<TextView>(R.id.backToDashboard).setOnClickListener { finish() }

        val statusText = findViewById<TextView>(R.id.historyStatusText)
        val transactionsContainer = findViewById<LinearLayout>(R.id.transactionsContainer)
        val beneficiariesContainer = findViewById<LinearLayout>(R.id.beneficiariesContainer)

        val token = sessionToken
        if (token == null) {
            statusText.text = "Session expired -- please log in again."
            return
        }

        statusText.text = "Loading..."
        CoroutineScope(Dispatchers.Main).launch {
            try {
                val txnResult = withContext(Dispatchers.IO) { client.listTransactions(token) }
                val benefResult = withContext(Dispatchers.IO) { client.listBeneficiaries(token) }

                val transactions = txnResult.body
                transactionsContainer.removeAllViews()
                if (txnResult.status == 200 && transactions.length() > 0) {
                    for (i in 0 until transactions.length()) {
                        if (i > 0) BankingViews.addDivider(this@TransactionHistoryActivity, transactionsContainer)
                        BankingViews.addTransactionRow(this@TransactionHistoryActivity, transactionsContainer, transactions.getJSONObject(i))
                    }
                } else {
                    addEmptyRow(transactionsContainer, "No transactions yet.")
                }

                val beneficiaries = benefResult.body
                beneficiariesContainer.removeAllViews()
                if (benefResult.status == 200 && beneficiaries.length() > 0) {
                    for (i in 0 until beneficiaries.length()) {
                        if (i > 0) BankingViews.addDivider(this@TransactionHistoryActivity, beneficiariesContainer)
                        BankingViews.addBeneficiaryRow(this@TransactionHistoryActivity, beneficiariesContainer, beneficiaries.getJSONObject(i))
                    }
                } else {
                    addEmptyRow(beneficiariesContainer, "No saved beneficiaries.")
                }

                statusText.text = ""
            } catch (e: Exception) {
                statusText.text = "Could not load transaction history: ${e.message}"
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

    companion object {
        const val EXTRA_SESSION_TOKEN = "session_token"
        const val EXTRA_USERNAME = "username"
    }
}
