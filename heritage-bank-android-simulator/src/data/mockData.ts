import { Beneficiary, Transaction, Account } from '../types';

export const MOCK_BENEFICIARIES: Beneficiary[] = [
  {
    id: 'b1',
    name: 'Rohan S.',
    vpa: 'rohan.saxena@okheritage',
    avatar: 'https://lh3.googleusercontent.com/aida-public/AB6AXuC2sKMfgG0BS7c-LJP-8cxBenmee6d8uNcUY6IVyf45YNRzEKe5cHhUpzC4JcmFTy7qE02sTXeIaPNLUChCDXAZIrhHutk28Yj_HZ3V_0vGjOTbJte7wPxKZWY35hN8-c5SiJuS-TT6I8yMDYQmlHgfQlG9UjBE82xiVyQfHncR9T8N6xZKLGBVj9jdJ6CAbMjRDneaCSrPG0Se4HT3Fmyn7AnXY6cZCsqO3Osa7MW7PntRy4ms9-BER8hW3zC8klKqDV3EvhosPUM',
    initials: 'RS'
  },
  {
    id: 'b2',
    name: 'Meera K.',
    vpa: 'meera.krishnan@okheritage',
    avatar: 'https://lh3.googleusercontent.com/aida-public/AB6AXuB-WxZj-xpiVHoh2fwQ_qYSjbqnMxUufs35xeOg1QilbqgiK79W3LrUXuDDUBaj_rx62mGyqAlHJjoShvCD7TBm0cEs9-7Pj0Lpqg0ygWVW0o4q7HvRa9vklnLu84KgIXyqb23_55f7LMHQkBKPa9ofNDuTlFlJZd50lSm-CU6GFtT_YYCbTC8xbqDA8YuJE6kfpNPjfA6pHMBhgup5DEoUby-LAteJD8t1YygMpGnGHUW0U3wZTKIGd2Q8TUKqW0V0Cdg_cYdCmds',
    initials: 'MK'
  },
  {
    id: 'b3',
    name: 'Amit V.',
    vpa: 'amit.verma@okheritage',
    avatar: 'https://lh3.googleusercontent.com/aida-public/AB6AXuDjYbnVYbpHcj7JoPJetucbHLzrkRG23jv1onlSHVozsHULDWoCRbfT-jkwGATu-nkXYeIN_droflhMb_eQ_2_YFX3neeyQ54quoajkCeDT-4MYYn2A4VaU8qk6hddDsFXxrD82DuvqNdmjwXvk2GAz9EFRmT-TR6X3U8b9Nnrb2T5dr68mdnBHZyeMsu-ZKgX-d4ODAANfT71eWK2RvlyE8emMbiAqe7V2VrHyJoa5gFQyVekMufvApmh_ev4UxaobIAkzzu-BFfo',
    initials: 'AV'
  },
  {
    id: 'b4',
    name: 'Priya L.',
    vpa: 'priya.lal@okheritage',
    avatar: 'https://lh3.googleusercontent.com/aida-public/AB6AXuCz7V-4tyc-69j0fqE8X_UnuE8nrRes45fIKUzR9KhZRMAAWvD_G7qJWXDVAj-7yHK6RqR0cJO9ikSMNxH0cwlXrgpWzNaoRzXx1x9Q3LL_yjzVxapV02RcguT8_nGRXFu3R---0Rj14yUeCf8yZtWzsco_MvyX8sgLaD6yxcr2zlLoerqa41IJo3c4Ung5L8IN2YJIziz7iBZGT7p5W22IYLo2fuU2Qje1bs2fP73o7mAWlg10pifV2Ummi5JYiK17lZkFdh7GP_I',
    initials: 'PL'
  }
];

export const MOCK_ACCOUNTS: Account[] = [
  {
    id: 'a1',
    type: 'Savings Account',
    accountNo: '•••• 8821',
    balance: 124560.80,
    currency: '₹'
  }
];

export const MOCK_TRANSACTIONS: Transaction[] = [
  {
    id: 'tx1',
    beneficiary: 'Swiggy',
    category: 'food',
    amount: 450.00,
    timestamp: 'Today, 12:45 PM',
    type: 'debit',
    status: 'success',
    paymentMethod: 'UPI'
  },
  {
    id: 'tx2',
    beneficiary: 'Electricity Bill',
    category: 'utilities',
    amount: 2840.00,
    timestamp: '18 Oct, 10:20 AM',
    type: 'debit',
    status: 'success',
    paymentMethod: 'NEFT'
  },
  {
    id: 'tx3',
    beneficiary: 'Internal Transfer',
    category: 'transfer',
    amount: 15000.00,
    timestamp: '16 Oct, 09:15 PM',
    type: 'credit',
    status: 'success',
    paymentMethod: 'IMPS',
    remarks: 'Self Transfer'
  }
];

export const KOTLIN_CODE_SNIPPETS = {
  LoginActivity: `package com.cogniguard.demoapp

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.cogniguard.sdk.CogniGuardClient
import com.cogniguard.sdk.model.Behavior
import com.cogniguard.sdk.model.LoginResult
import kotlinx.android.synthetic.main.activity_login.*

class LoginActivity : AppCompatActivity() {

    private val client = CogniGuardClient(this)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_login)

        // Present biometric consent dialog on first run
        showConsentBottomSheetIfNeeded()

        btnLogin.setOnClickListener {
            val username = etUsername.text.toString()
            val password = etPassword.text.toString()

            // Populating behavioral parameters from on-device TFLite autoencoder
            val behavior = Behavior(
                source = "mobile_edge",
                derived_features = client.getOnDeviceFeatures(),
                ae_recon_error = client.getTFLiteReconstructionError()
            )

            // Make secure network call via client SDK
            client.login(username, password, behavior) { result ->
                when (result.action) {
                    "allow" -> {
                        // Pass scores to DashboardActivity as intent extras
                        val intent = Intent(this, DashboardActivity::class.java).apply {
                            putExtra("trust_score", result.trust_score)
                            putExtra("behavior_match_score", result.behavior_match_score)
                            putExtra("device_trust", result.device_trust)
                        }
                        startActivity(intent)
                        finish()
                    }
                    "verify" -> {
                        // Present Step-Up biometric verification in-place (no separate activity)
                        showInPlaceBiometricPrompt { success ->
                            if (success) {
                                client.verifyStepUp(result.session_token) { stepUpResult ->
                                    if (stepUpResult.isSuccessful) {
                                        navigateToDashboard(result)
                                    } else {
                                        showError("Verification failed")
                                    }
                                }
                            }
                        }
                    }
                    "deny" -> {
                        showError("Access denied. Blocked by behavioral profile anomaly.")
                    }
                }
            }
        }
    }

    private fun showConsentBottomSheetIfNeeded() {
        // Bottom sheet asking user for behavioral profiling consent
        ConsentBottomSheet { consented ->
            client.setConsent(consented)
        }.show(supportFragmentManager, "Consent")
    }
}`,

  DashboardActivity: `package com.cogniguard.demoapp

import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import com.cogniguard.sdk.CogniGuardClient
import kotlinx.android.synthetic.main.activity_dashboard.*

class DashboardActivity : AppCompatActivity() {

    private val client = CogniGuardClient(this)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_dashboard)

        // Retrieve risk scores from Login Intent Extras
        val trustScore = intent.getFloatExtra("trust_score", 1.0f)
        val behaviorMatchScore = intent.getFloatExtra("behavior_match_score", 1.0f)

        // Render profile, balance and accounts
        client.getProfile { profile ->
            txtWelcome.text = "Namaste, \${profile.firstName}"
        }

        client.listAccounts { accounts ->
            // Update balance UI mapping
            val primaryAccount = accounts.firstOrNull()
            txtBalance.text = "₹" + String.format("%,.2f", primaryAccount?.balance ?: 0.0)
            txtAccountNo.text = "Savings \${primaryAccount?.accountNo}"
        }

        btnTransfer.setOnClickListener {
            startActivity(Intent(this, TransferActivity::class.java))
        }

        btnSecurity.setOnClickListener {
            startActivity(Intent(this, SecurityCenterActivity::class.java))
        }

        btnHistory.setOnClickListener {
            startActivity(Intent(this, TransactionHistoryActivity::class.java))
        }
    }
}`,

  TransferActivity: `package com.cogniguard.demoapp

import android.content.Intent
import android.os.Bundle
import android.view.View
import androidx.appcompat.app.AppCompatActivity
import com.cogniguard.sdk.CogniGuardClient
import com.cogniguard.sdk.model.Behavior
import kotlinx.android.synthetic.main.activity_transfer.*

class TransferActivity : AppCompatActivity() {

    private val client = CogniGuardClient(this)
    private var currentTxnControls: TxnControls? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_transfer)

        // UI Initialization
        btnSendMoney.setOnClickListener {
            val amount = etAmount.text.toString().toDouble()
            val vpa = etVpa.text.toString()

            // Channel is strictly hardcoded to "mobile" inside client for scorePayment
            val behavior = Behavior(
                source = "mobile_edge",
                ae_recon_error = client.getTFLiteReconstructionError()
            )

            client.scorePayment(
                token = client.getSessionToken(),
                amount = amount,
                beneficiaryVpa = vpa,
                transferType = getSelectedType(),
                behavior = behavior
            ) { result ->
                // Check E5 txn_controls state machine
                if (result.txn_controls != null) {
                    currentTxnControls = result.txn_controls
                    resolveTxnControls(result.txn_controls)
                } else if (result.action == "allow") {
                    navigateToSuccess(amount, vpa)
                } else {
                    showDenialState()
                }
            }
        }
    }

    private fun resolveTxnControls(controls: TxnControls) {
        // Handle coercion or manual approval state machine
        // DO NOT trigger secondary network calls - resolve via local view states
        if (controls.coercion_warning_required) {
            coercionPanel.visibility = View.VISIBLE
            txtCoercionWarning.text = "Warning: Active Call Detected. Are you being coerced into this transfer?"
            
            btnCoercionAcknowledge.setOnClickListener {
                coercionPanel.visibility = View.GONE
                // Proceed with stored state, no extra network score call needed
                navigateToSuccess(
                    etAmount.text.toString().toDouble(),
                    etVpa.text.toString()
                )
            }
        } else if (controls.manual_approval_required) {
            manualAmountPanel.visibility = View.VISIBLE
            txtManualWarning.text = "Transfer limit restriction: Max ₹\${controls.limit_coercion_amount}"
            
            btnManualConfirm.setOnClickListener {
                manualAmountPanel.visibility = View.GONE
                navigateToSuccess(controls.limit_coercion_amount ?: 1000.0, etVpa.text.toString())
            }
        }
    }

    private fun navigateToSuccess(amount: Double, vpa: String) {
        val intent = Intent(this, TransferSuccessActivity::class.java).apply {
            putExtra("amount", amount)
            putExtra("vpa", vpa)
            putExtra("timestamp", System.currentTimeMillis())
        }
        startActivity(intent)
        finish()
    }
}`,

  TransferSuccessActivity: `package com.cogniguard.demoapp

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import kotlinx.android.synthetic.main.activity_transfer_success.*
import java.text.SimpleDateFormat
import java.util.*

class TransferSuccessActivity : AppCompatActivity() {

    // Pure display screen - NO extra network fetch is performed
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_transfer_success)

        val amount = intent.getDoubleExtra("amount", 0.0)
        val vpa = intent.getStringExtra("vpa") ?: ""
        val timestamp = intent.getLongExtra("timestamp", System.currentTimeMillis())

        // Render fields directly from the already-received response
        txtSuccessAmount.text = "₹" + String.format("%,.2f", amount)
        txtSuccessBeneficiary.text = vpa
        
        val sdf = SimpleDateFormat("dd MMM yyyy, hh:mm a", Locale.getDefault())
        txtSuccessTime.text = sdf.format(Date(timestamp))

        // Renders client-generated display reference locally
        txtReferenceId.text = "REF" + (100000000000 + Random().nextInt(900000000))

        btnBackToHome.setOnClickListener {
            finish()
        }
    }
}`,

  SecurityCenterActivity: `package com.cogniguard.demoapp

import android.os.Bundle
import android.view.View
import androidx.appcompat.app.AppCompatActivity
import com.cogniguard.sdk.CogniGuardClient
import kotlinx.android.synthetic.main.activity_security_center.*

class SecurityCenterActivity : AppCompatActivity() {

    private val client = CogniGuardClient(this)

    // QUALITATIVE-ONLY - Per security guidelines, do not surface raw scores or 
    // model names here, even if they are visible elsewhere in the logs or SDK.
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_security_center)

        client.getSecuritySettings { response ->
            // Intentionally only derives a human-readable qualitative state:
            // "Protected" or "Needs attention" style qualitative state
            val trustScore = response.overall_trust_score
            val isTFLiteCalibrated = response.on_device_calibrated

            if (trustScore >= 0.85f && isTFLiteCalibrated) {
                txtSecurityStatus.text = "Protected"
                iconShield.setImageResource(R.drawable.ic_shield_secure)
                txtStatusDesc.text = "Your on-device behavioral lock is active and calibrated. No threats detected."
                layoutNeedsAttention.visibility = View.GONE
            } else {
                txtSecurityStatus.text = "Needs attention"
                iconShield.setImageResource(R.drawable.ic_shield_warning)
                txtStatusDesc.text = "On-device profile calibration is in progress, or behavioral match is low."
                layoutNeedsAttention.visibility = View.VISIBLE
            }
        }
    }
}`,

  TransactionHistoryActivity: `package com.cogniguard.demoapp

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import com.cogniguard.sdk.CogniGuardClient
import kotlinx.android.synthetic.main.activity_transaction_history.*

class TransactionHistoryActivity : AppCompatActivity() {

    private val client = CogniGuardClient(this)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_transaction_history)

        setupRecyclerViews()

        // Same mapping as web Dashboard, plus a beneficiary list panel.
        client.listTransactions { transactions ->
            transactionAdapter.setItems(transactions)
        }

        client.listBeneficiaries { beneficiaries ->
            beneficiaryAdapter.setItems(beneficiaries)
        }
    }

    private fun setupRecyclerViews() {
        rvTransactions.layoutManager = LinearLayoutManager(this)
        rvTransactions.adapter = transactionAdapter

        rvBeneficiaries.layoutManager = LinearLayoutManager(this, LinearLayoutManager.HORIZONTAL, false)
        rvBeneficiaries.adapter = beneficiaryAdapter
    }
}`,

  CogniGuardClient: `package com.cogniguard.sdk

import android.content.Context
import com.cogniguard.sdk.model.*

/**
 * CogniGuard Mobile Edge Security SDK Client.
 * Encapsulates the on-device TFLite behavioral autoencoder and secure API endpoints.
 */
class CogniGuardClient(private val context: Context) {

    // Returns on-device keystroke / swipe timing features
    fun getOnDeviceFeatures(): Map<String, Float> {
        return mapOf(
            "typing_speed" to 142.5f,
            "flight_time_var" to 18.2f,
            "tremor_index" to 0.04f,
            "screen_pressure_avg" to 0.58f
        )
    }

    // Fetches the reconstruction error from the local TFLite neural net model.
    // Low values (< 2.5) mean the typing pattern matches the owner (Rohan).
    // High values (> 3.5) indicate potential takeover, stress, or coercion.
    fun getTFLiteReconstructionError(): Float {
        val sharedPrefs = context.getSharedPreferences("CogniGuardPrefs", Context.MODE_PRIVATE)
        return sharedPrefs.getFloat("simulated_ae_recon_error", 1.25f)
    }

    fun login(username: String, password: String, behavior: Behavior, callback: (LoginResult) -> Unit) {
        // Triggers POST /api/v1/auth/login with behavior payload
        // behavior.source is set to "mobile_edge"
    }

    fun verifyStepUp(sessionToken: String, callback: (StepUpResult) -> Unit) {
        // Triggers POST /api/v1/auth/step-up
    }

    fun scorePayment(
        token: String,
        amount: Double,
        beneficiaryVpa: String,
        transferType: String,
        behavior: Behavior,
        callback: (PaymentScoreResult) -> Unit
    ) {
        // channel is strictly hardcoded "mobile" in request body
        // Evaluates trust score & returns txn_controls rules if anomalous
    }

    fun setConsent(consented: Boolean) {
        // Stores consent state on-device
    }

    fun getSecuritySettings(callback: (SecuritySettingsResponse) -> Unit) {
        // Returns overall security profile telemetry
    }
}`
};
