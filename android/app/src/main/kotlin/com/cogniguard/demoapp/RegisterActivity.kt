package com.cogniguard.demoapp

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.cogniguard.capturesdk.KeystrokeCapture
import com.cogniguard.capturesdk.integrity.Signer
import com.cogniguard.capturesdk.net.CogniGuardClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Sign-up screen — collects Full Name, Email, Username, Password, DPDP consent.
 *  On submit: calls initiate_registration (POST /api/v1/auth/register) which creates
 *  a pending account and sends an email OTP. Navigates to EmailVerifyActivity.
 *  Biometric enrollment is NOT prompted here; it happens post first-login in LoginActivity. */
class RegisterActivity : AppCompatActivity() {

    private lateinit var client: CogniGuardClient
    private lateinit var keystrokeCapture: KeystrokeCapture

    private lateinit var fullNameInput: EditText
    private lateinit var emailInput: EditText
    private lateinit var usernameInput: EditText
    private lateinit var passwordInput: EditText
    private lateinit var confirmPasswordInput: EditText
    private lateinit var consentCheckbox: CheckBox
    private lateinit var registerButton: Button
    private lateinit var statusText: TextView
    private lateinit var signInLink: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)
        setContentView(R.layout.activity_register)

        client = CogniGuardClient(BuildConfig.API_BASE, BuildConfig.SIGNING_SECRET)
        Signer.resetSequence()

        fullNameInput = findViewById(R.id.fullNameInput)
        emailInput = findViewById(R.id.emailInput)
        usernameInput = findViewById(R.id.regUsernameInput)
        passwordInput = findViewById(R.id.regPasswordInput)
        confirmPasswordInput = findViewById(R.id.regConfirmPasswordInput)
        consentCheckbox = findViewById(R.id.consentCheckbox)
        registerButton = findViewById(R.id.registerButton)
        statusText = findViewById(R.id.registerStatusText)
        signInLink = findViewById(R.id.signInLink)

        keystrokeCapture = KeystrokeCapture.attach(passwordInput, fieldId = "reg_password")

        registerButton.setOnClickListener { attemptRegister() }

        signInLink.setOnClickListener {
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
        }
    }

    private fun attemptRegister() {
        val fullName = fullNameInput.text.toString().trim()
        val email = emailInput.text.toString().trim()
        val username = usernameInput.text.toString().trim()
        val password = passwordInput.text.toString()
        val confirm = confirmPasswordInput.text.toString()

        if (email.isEmpty() || username.isEmpty() || password.isEmpty()) {
            statusText.text = "Email, username, and password are required."
            return
        }
        if (!android.util.Patterns.EMAIL_ADDRESS.matcher(email).matches()) {
            statusText.text = "Please enter a valid email address."
            return
        }
        if (password.length < 8) {
            statusText.text = "Password must be at least 8 characters."
            return
        }
        if (password != confirm) {
            statusText.text = "Passwords do not match."
            return
        }
        if (!consentCheckbox.isChecked) {
            statusText.text = "Please consent to behavioral data processing to continue."
            return
        }

        registerButton.isEnabled = false
        registerButton.text = "Creating account…"
        statusText.text = ""

        CoroutineScope(Dispatchers.Main).launch {
            try {
                val result = withContext(Dispatchers.IO) {
                    client.register(
                        username = username,
                        password = password,
                        email = email,
                        fullName = fullName.ifEmpty { null },
                    )
                }
                when (result.status) {
                    201 -> {
                        val challengeId = result.body.optString("challenge_id", "")
                        val intent = Intent(this@RegisterActivity, EmailVerifyActivity::class.java).apply {
                            putExtra("challenge_id", challengeId)
                            putExtra("username", username)
                            putExtra("email", email)
                            putExtra("password", password)
                        }
                        startActivity(intent)
                        finish()
                    }
                    409 -> {
                        statusText.text = "Username already taken. Please choose another."
                        registerButton.isEnabled = true
                        registerButton.text = "Create Account"
                    }
                    else -> {
                        statusText.text = "Registration failed (${result.status}). Please try again."
                        registerButton.isEnabled = true
                        registerButton.text = "Create Account"
                    }
                }
            } catch (e: Exception) {
                statusText.text = "Could not connect to server: ${e.message}"
                registerButton.isEnabled = true
                registerButton.text = "Create Account"
            }
        }
    }
}
