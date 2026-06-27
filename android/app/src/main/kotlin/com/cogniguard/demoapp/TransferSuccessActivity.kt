package com.cogniguard.demoapp

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import java.time.Instant
import java.util.Locale
import java.util.UUID

/** Transfer confirmation screen (Phase 31) -- shown once `TransferActivity` sees a
 * cleared `allow` with no pending coercion-check/manual-amount/cooling control.
 *
 * The gateway's `/api/v1/payment/score` is a risk-decision endpoint, not a ledger
 * write (CLAUDE.md invariant 7 -- only `risk_scores`/`decisions`/`audit_logs` are
 * persisted there); this prototype has no transaction-posting endpoint to fetch a real
 * ledger id from. The reference id/timestamp shown here are generated client-side for
 * display only -- everything else on this screen (amount, beneficiary, the verified
 * decision itself) is the real response from that scoring call. */
class TransferSuccessActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)
        setContentView(R.layout.activity_transfer_success)

        val amount = intent.getDoubleExtra(EXTRA_AMOUNT, 0.0)
        val beneficiary = intent.getStringExtra(EXTRA_BENEFICIARY) ?: "--"
        val username = intent.getStringExtra(EXTRA_USERNAME) ?: "genuine"

        findViewById<TextView>(R.id.headerUsername).text = username
        findViewById<LinearLayout>(R.id.headerLogoArea).setOnClickListener { goToDashboard() }

        val reference = "TXN" + UUID.randomUUID().toString().take(10).uppercase(Locale.US).replace("-", "")
        findViewById<TextView>(R.id.successSubtitle).text = "Your money is on its way."
        findViewById<TextView>(R.id.txnIdValue).text = reference
        findViewById<TextView>(R.id.txnAmountValue).text = BankingViews.formatInr(amount, "INR")
        findViewById<TextView>(R.id.txnBeneficiaryValue).text = beneficiary
        findViewById<TextView>(R.id.txnDateValue).text = BankingViews.formatDateTime(Instant.now().toString())

        findViewById<Button>(R.id.doneButton).setOnClickListener { goToDashboard() }
    }

    /** `DashboardActivity` is `singleTop` (AndroidManifest) so `CLEAR_TOP` here reuses
     * the existing, already-loaded instance instead of recreating it -- Transfer and
     * this Success screen are simply popped off the stack. */
    private fun goToDashboard() {
        val intent = Intent(this, DashboardActivity::class.java)
        intent.flags = Intent.FLAG_ACTIVITY_CLEAR_TOP
        startActivity(intent)
        finish()
    }

    companion object {
        const val EXTRA_AMOUNT = "amount"
        const val EXTRA_BENEFICIARY = "beneficiary"
        const val EXTRA_USERNAME = "username"
    }
}
