package com.cogniguard.demoapp

import android.content.Intent
import android.os.Bundle
import android.util.Base64
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import com.cogniguard.capturesdk.MotionCapture
import com.cogniguard.capturesdk.edge.MobileFeatures
import com.cogniguard.capturesdk.fingerprint.DeviceFingerprint
import com.cogniguard.capturesdk.ml.AeSequenceScorer
import com.cogniguard.capturesdk.model.ActionBlock
import com.cogniguard.capturesdk.model.ContextBlock
import com.cogniguard.capturesdk.model.UnsignedBehaviorPayload
import com.cogniguard.capturesdk.net.CogniGuardClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.Instant

/** Customer banking home screen (Phase 31) -- lands here after `allow`/verified login
 * instead of going straight to Transfer, mirroring `web-app/src/pages/Dashboard.tsx`'s
 * place in the nav graph: Login -> Dashboard -> Transfer -> Success, with Dashboard also
 * branching to Security Center and Transaction History. Reads the real, PII-masked
 * `/api/v1/banking` endpoints -- no risk/trust telemetry is shown here. */
class DashboardActivity : AppCompatActivity() {
    private lateinit var client: CogniGuardClient
    private lateinit var motionCapture: MotionCapture
    private val aeScorerLazy = lazy { AeSequenceScorer(this) }
    private val aeScorer by aeScorerLazy
    private var aeModelVersion: String? = null
    private var sessionToken: String? = null
    private var username: String = "genuine"
    private var trustScore: Double = Double.NaN
    private var behaviorMatch: Double = Double.NaN
    private var deviceTrust: Double = Double.NaN
    private var ingestJob: Job? = null
    private var balanceRevealed: Boolean = false
    private var cachedBalance: Double? = null
    private var cachedCurrency: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)
        setContentView(R.layout.activity_dashboard)
        client = CogniGuardClient(BuildConfig.API_BASE, BuildConfig.SIGNING_SECRET)
        motionCapture = MotionCapture(this)

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
                    val fullName = BankingViews.safeOptStringOrNull(profileResult.body, "full_name")
                    if (!fullName.isNullOrBlank()) {
                        findViewById<TextView>(R.id.welcomeText).text = "Welcome back, $fullName"
                    }
                }

                val accounts = accountsResult.body
                if (accountsResult.status == 200 && accounts.length() > 0) {
                    val account = accounts.getJSONObject(0)
                    cachedBalance = account.optDouble("balance").takeIf { !it.isNaN() }
                    cachedCurrency = BankingViews.safeOptStringOrNull(account, "currency")
                    balanceText.text = "₹ ••••••"
                    accountSummaryText.text =
                        "${BankingViews.safeOptString(account, "account_type", "Account")} · ${BankingViews.safeOptString(account, "masked_account_number")}"
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
        BankingViews.addQuickAction(this, row, "T", R.drawable.bg_tile_rounded_primary, "Transfer") { goToTransfer() }
        BankingViews.addQuickAction(this, row, "B", R.drawable.bg_tile_rounded_accent, "Balance") { toggleBalance() }
        BankingViews.addQuickAction(this, row, "H", R.drawable.bg_tile_rounded_accent, "History") { goToTransactionHistory() }
        BankingViews.addQuickAction(this, row, "S", R.drawable.bg_tile_rounded_success, "Security") { goToSecurityCenter() }
        BankingViews.addQuickAction(this, row, "P", R.drawable.bg_tile_rounded_outline, "Profile") { goToProfile() }
        BankingViews.addQuickAction(this, row, "L", R.drawable.bg_tile_rounded_outline, "Logout") { confirmLogout() }

        findViewById<com.google.android.material.floatingactionbutton.FloatingActionButton>(R.id.quickTransferFab)
            .setOnClickListener { goToTransfer() }
    }

    private fun toggleBalance() {
        val balanceText = findViewById<TextView>(R.id.balanceText)
        val token = sessionToken ?: return
        if (balanceRevealed) {
            balanceText.text = "₹ ••••••"
            balanceRevealed = false
        } else {
            if (cachedBalance != null) {
                balanceText.text = BankingViews.formatInr(cachedBalance, cachedCurrency)
                balanceRevealed = true
            } else {
                CoroutineScope(Dispatchers.Main).launch {
                    try {
                        val result = withContext(Dispatchers.IO) { client.listAccounts(token) }
                        if (result.status == 200 && result.body.length() > 0) {
                            val account = result.body.getJSONObject(0)
                            cachedBalance = account.optDouble("balance").takeIf { !it.isNaN() }
                            cachedCurrency = BankingViews.safeOptStringOrNull(account, "currency")
                            balanceText.text = BankingViews.formatInr(cachedBalance, cachedCurrency)
                            balanceRevealed = true
                        }
                    } catch (_: Exception) { /* keep masked */ }
                }
            }
        }
    }

    private fun goToTransfer() {
        val intent = Intent(this, TransferActivity::class.java)
        intent.putExtra(TransferActivity.EXTRA_SESSION_TOKEN, sessionToken)
        intent.putExtra(TransferActivity.EXTRA_USERNAME, username)
        startActivity(intent)
    }

    private fun goToProfile() {
        val intent = Intent(this, ProfileActivity::class.java)
        intent.putExtra(ProfileActivity.EXTRA_SESSION_TOKEN, sessionToken)
        intent.putExtra(ProfileActivity.EXTRA_USERNAME, username)
        if (!trustScore.isNaN()) intent.putExtra(ProfileActivity.EXTRA_TRUST_SCORE, trustScore)
        if (!behaviorMatch.isNaN()) intent.putExtra(ProfileActivity.EXTRA_BEHAVIOR_MATCH, behaviorMatch)
        if (!deviceTrust.isNaN()) intent.putExtra(ProfileActivity.EXTRA_DEVICE_TRUST, deviceTrust)
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

    override fun onResume() {
        super.onResume()
        motionCapture.start()
        val token = sessionToken ?: return
        ingestJob = CoroutineScope(Dispatchers.IO).launch {
            while (isActive) {
                delay(INGEST_INTERVAL_MS)
                try {
                    val behavior = buildIdlePayload()
                    val result = client.ingest(token, behavior)
                    val action = result.body.optString("action")
                    val reauth = result.body.optBoolean("reauth", false)
                    withContext(Dispatchers.Main) {
                        when {
                            reauth -> navigateToLogin("Your session was terminated for security reasons.")
                            action == "verify" -> showReauthDialog()
                        }
                    }
                } catch (_: Exception) { /* best-effort */ }
            }
        }
    }

    override fun onPause() {
        super.onPause()
        motionCapture.stop()
        ingestJob?.cancel()
        ingestJob = null
    }

    override fun onDestroy() {
        super.onDestroy()
        if (aeScorerLazy.isInitialized()) aeScorer.close()
    }

    private suspend fun buildIdlePayload(): UnsignedBehaviorPayload {
        val device = DeviceFingerprint.compute(this)
        val derivedFeatures = MobileFeatures.extract(swipes = emptyList(), motionSamples = motionCapture.drain())
        if (aeModelVersion == null) {
            aeModelVersion = runCatching { client.getAeModel().body.optString("version") }.getOrNull()
        }
        val aeReconError = runCatching { aeScorer.score(derivedFeatures) }.getOrNull()
        return UnsignedBehaviorPayload(
            channel = "mobile",
            source = "mobile_edge",
            device = device,
            action = ActionBlock(type = "VIEW_BALANCE"),
            derivedFeatures = derivedFeatures.takeIf { it.isNotEmpty() },
            aeReconError = aeReconError,
            aeModelVersion = if (aeReconError != null) aeModelVersion else null,
            context = ContextBlock(submittedAt = Instant.now().toString(), page = "dashboard"),
        )
    }

    private fun showReauthDialog() {
        if (isFinishing || isDestroyed) return
        AlertDialog.Builder(this)
            .setTitle("Security Check")
            .setMessage("Unusual activity detected on your session. Please verify your identity to continue.")
            .setPositiveButton("Verify with Biometric") { _, _ ->
                promptBiometric { /* verified — dismiss and continue */ }
            }
            .setNegativeButton("Log Out") { _, _ ->
                navigateToLogin("Logged out for security.")
            }
            .setCancelable(false)
            .show()
    }

    /** Real BiometricPrompt with CryptoObject for session re-auth.
     *  Signs a local timestamp nonce so the OS enforces a fresh biometric before the
     *  KeyStore key is used. The signature is not sent to the server — it proves locally
     *  that the physical user was present. Falls back to plain authenticate if key not bound. */
    private fun promptBiometric(onSuccess: () -> Unit) {
        val nonce = "reauth:${System.currentTimeMillis()}"
        val sig = BiometricEnrollmentManager.prepareSignature(nonce)
        val executor = ContextCompat.getMainExecutor(this)
        val prompt = BiometricPrompt(
            this, executor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    if (sig != null) {
                        // consume the signature to complete the CryptoObject authentication
                        runCatching { result.cryptoObject?.signature?.sign() }
                    }
                    onSuccess()
                }
                override fun onAuthenticationError(code: Int, errString: CharSequence) {
                    navigateToLogin("Verification failed — please log in again.")
                }
                override fun onAuthenticationFailed() { /* user can retry */ }
            },
        )
        val info = BiometricPrompt.PromptInfo.Builder()
            .setTitle("Verify your identity")
            .setSubtitle("CogniGuard detected unusual session activity")
            .setNegativeButtonText("Log Out")
            .build()
        if (sig != null) {
            prompt.authenticate(info, BiometricPrompt.CryptoObject(sig))
        } else {
            prompt.authenticate(info)
        }
    }

    private fun confirmLogout() {
        AlertDialog.Builder(this)
            .setTitle("Log Out")
            .setMessage("Are you sure you want to log out?")
            .setPositiveButton("Log Out") { _, _ -> logout() }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun logout() {
        val token = sessionToken ?: run { navigateToLogin("Logged out."); return }
        Thread {
            try { client.logout(token) } catch (_: Exception) {}
            runOnUiThread { navigateToLogin("You have been logged out.") }
        }.start()
    }

    private fun navigateToLogin(message: String) {
        val intent = Intent(this, LoginActivity::class.java)
        intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        intent.putExtra("logout_message", message)
        startActivity(intent)
        finish()
    }

    companion object {
        const val EXTRA_SESSION_TOKEN = "session_token"
        const val EXTRA_USERNAME = "username"
        const val EXTRA_TRUST_SCORE = "trust_score"
        const val EXTRA_BEHAVIOR_MATCH = "behavior_match"
        const val EXTRA_DEVICE_TRUST = "device_trust"
        private const val INGEST_INTERVAL_MS = 30_000L
    }
}
