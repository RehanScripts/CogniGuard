package com.cogniguard.demoapp

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.cogniguard.capturesdk.integrity.Signer
import com.cogniguard.capturesdk.net.CogniGuardClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Email OTP verification screen — shown after RegisterActivity submits successfully.
 *  Verifies the 6-digit OTP sent by the server, then calls setConsent and navigates
 *  to LoginActivity with a success message. */
class EmailVerifyActivity : AppCompatActivity() {

    private lateinit var client: CogniGuardClient

    private lateinit var maskedEmailText: TextView
    private lateinit var otpInput: EditText
    private lateinit var verifyButton: Button
    private lateinit var statusText: TextView
    private lateinit var attemptsText: TextView
    private lateinit var resendLink: TextView
    private lateinit var backLink: TextView

    private lateinit var challengeId: String
    private lateinit var username: String
    private lateinit var email: String
    private lateinit var password: String

    private var attempts = 0
    private val maxAttempts = 3

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)
        setContentView(R.layout.activity_email_verify)

        client = CogniGuardClient(BuildConfig.API_BASE, BuildConfig.SIGNING_SECRET)

        challengeId = intent.getStringExtra("challenge_id") ?: ""
        username = intent.getStringExtra("username") ?: ""
        email = intent.getStringExtra("email") ?: ""
        password = intent.getStringExtra("password") ?: ""

        maskedEmailText = findViewById(R.id.maskedEmailText)
        otpInput = findViewById(R.id.otpInput)
        verifyButton = findViewById(R.id.verifyOtpButton)
        statusText = findViewById(R.id.otpStatusText)
        attemptsText = findViewById(R.id.otpAttemptsText)
        resendLink = findViewById(R.id.resendOtpLink)
        backLink = findViewById(R.id.backToRegisterLink)

        maskedEmailText.text = maskEmail(email)

        verifyButton.setOnClickListener { attemptVerify() }
        resendLink.setOnClickListener { resendOtp() }
        backLink.setOnClickListener {
            startActivity(Intent(this, RegisterActivity::class.java))
            finish()
        }
    }

    private fun attemptVerify() {
        val otp = otpInput.text.toString().trim()
        if (otp.length != 6) {
            statusText.text = "Please enter the 6-digit code."
            return
        }

        verifyButton.isEnabled = false
        verifyButton.text = "Verifying…"
        statusText.text = ""

        CoroutineScope(Dispatchers.Main).launch {
            try {
                val result = withContext(Dispatchers.IO) {
                    client.verifyRegistrationEmail(challengeId, otp)
                }
                when (result.status) {
                    200 -> {
                        // Account activated — grant consent then navigate to login
                        withContext(Dispatchers.IO) { client.setConsent(username) }
                        val intent = Intent(this@EmailVerifyActivity, LoginActivity::class.java).apply {
                            putExtra("registered", true)
                            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
                        }
                        startActivity(intent)
                        finish()
                    }
                    401 -> {
                        attempts++
                        if (attempts >= maxAttempts) {
                            statusText.text = "Too many failed attempts. Please register again."
                            verifyButton.isEnabled = false
                            resendLink.isEnabled = false
                        } else {
                            statusText.text = "Incorrect OTP. Please check your email and try again."
                            attemptsText.text = "${maxAttempts - attempts} attempt(s) remaining."
                            verifyButton.isEnabled = true
                            verifyButton.text = "Verify"
                        }
                    }
                    404 -> {
                        statusText.text = "OTP expired. Please tap Resend to get a new code."
                        verifyButton.isEnabled = true
                        verifyButton.text = "Verify"
                    }
                    else -> {
                        statusText.text = "Verification failed (${result.status}). Please try again."
                        verifyButton.isEnabled = true
                        verifyButton.text = "Verify"
                    }
                }
            } catch (e: Exception) {
                statusText.text = "Connection error: ${e.message}"
                verifyButton.isEnabled = true
                verifyButton.text = "Verify"
            }
        }
    }

    private fun resendOtp() {
        resendLink.isEnabled = false
        statusText.text = "Sending new OTP…"

        CoroutineScope(Dispatchers.Main).launch {
            try {
                val result = withContext(Dispatchers.IO) {
                    client.register(username = username, password = password, email = email)
                }
                if (result.status == 201) {
                    challengeId = result.body.optString("challenge_id", challengeId)
                    attempts = 0
                    statusText.text = "A new code has been sent to your email."
                    attemptsText.text = ""
                    verifyButton.isEnabled = true
                    verifyButton.text = "Verify"
                } else if (result.status == 409) {
                    // Username already exists with pending status — the old challenge may still work
                    statusText.text = "Please wait and try the existing code, or contact support."
                } else {
                    statusText.text = "Could not resend OTP. Please try again."
                }
            } catch (e: Exception) {
                statusText.text = "Connection error: ${e.message}"
            }
            resendLink.isEnabled = true
        }
    }

    private fun maskEmail(email: String): String {
        val at = email.indexOf('@')
        if (at <= 1) return email
        val local = email.substring(0, at)
        val domain = email.substring(at)
        val masked = local.first() + "*".repeat((local.length - 2).coerceAtLeast(1)) + local.last()
        return masked + domain
    }
}
