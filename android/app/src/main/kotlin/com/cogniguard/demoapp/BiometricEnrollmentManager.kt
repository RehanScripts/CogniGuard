package com.cogniguard.demoapp

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.cogniguard.capturesdk.net.CogniGuardClient
import java.math.BigInteger
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.Signature
import java.security.spec.RSAKeyGenParameterSpec

/**
 * KeyStore-backed RSA-2048 keypair with setUserAuthenticationRequired(true) (Phase C3).
 *
 * Every private-key use MUST go through a fresh BiometricPrompt.CryptoObject — calling
 * Signature.sign() outside a CryptoObject auth throws UserNotAuthenticatedException.
 *
 * Enrollment flow:
 *   1. generateKeyIfAbsent()  — key generation requires no biometric.
 *   2. fetchEnrollChallenge() — get server nonce + device_id.
 *   3. prepareSignature(nonce) → wrap in CryptoObject, show BiometricPrompt.
 *   4. onAuthenticationSucceeded → result.cryptoObject?.signature?.sign() → POST bind-biometric.
 *
 * Step-up flow:
 *   1. prepareSignature(challengeId) → wrap in CryptoObject, show BiometricPrompt.
 *   2. onAuthenticationSucceeded → result.cryptoObject?.signature?.sign() → "keystore-sig:$b64".
 */
object BiometricEnrollmentManager {

    private const val KEY_ALIAS = "cogniguard_device_key_v2"
    private const val ANDROID_KEYSTORE = "AndroidKeyStore"

    data class EnrollChallenge(val nonce: String, val deviceId: String)

    /** True if a v2 key pair exists in the KeyStore (best-effort; false on any error). */
    fun isKeyBound(): Boolean = runCatching {
        val ks = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        ks.containsAlias(KEY_ALIAS)
    }.getOrDefault(false)

    /**
     * Generate an RSA-2048 keypair in the hardware-backed KeyStore if absent.
     * Key generation does not require biometric — only subsequent signing operations do.
     * Returns true if a key now exists, false on error.
     * Must be called from a background thread.
     */
    fun generateKeyIfAbsent(): Boolean = runCatching {
        if (isKeyBound()) return true
        val kpg = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_RSA, ANDROID_KEYSTORE)
        val spec = KeyGenParameterSpec.Builder(
            KEY_ALIAS,
            KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY,
        )
            .setAlgorithmParameterSpec(RSAKeyGenParameterSpec(2048, BigInteger.valueOf(65537)))
            .setDigests(KeyProperties.DIGEST_SHA256)
            .setSignaturePaddings(KeyProperties.SIGNATURE_PADDING_RSA_PKCS1)
            .setUserAuthenticationRequired(true)
            .build()
        kpg.initialize(spec)
        kpg.generateKeyPair()
        true
    }.getOrDefault(false)

    /**
     * Fetch the server enrollment nonce and device_id.
     * Must be called from a background thread.
     */
    fun fetchEnrollChallenge(client: CogniGuardClient, token: String): EnrollChallenge? =
        runCatching {
            val res = client.getEnrollChallenge(token)
            if (res.status != 200) return null
            EnrollChallenge(
                nonce = res.body.getString("enrollment_nonce"),
                deviceId = res.body.getString("device_id"),
            )
        }.getOrNull()

    /**
     * Initialise a Signature with the bound private key and pre-load [dataToSign].
     * Returns the Signature ready to be wrapped in BiometricPrompt.CryptoObject.
     * Returns null if no key is bound or on any initialisation error.
     *
     * IMPORTANT: do NOT call .sign() on the returned object directly — the key has
     * setUserAuthenticationRequired(true), so signing is only permitted inside the
     * BiometricPrompt.AuthenticationCallback.onAuthenticationSucceeded callback via
     * result.cryptoObject?.signature?.sign().
     */
    fun prepareSignature(dataToSign: String): Signature? = runCatching {
        val ks = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        if (!ks.containsAlias(KEY_ALIAS)) return null
        val privateKey = ks.getKey(KEY_ALIAS, null) as PrivateKey
        val sig = Signature.getInstance("SHA256withRSA")
        sig.initSign(privateKey)
        sig.update(dataToSign.toByteArray(Charsets.UTF_8))
        sig
    }.getOrNull()

    /**
     * Export the public key as a PEM string for server binding.
     * Returns null if no key is bound or on error.
     */
    fun getPublicKeyPem(): String? = runCatching {
        val ks = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        if (!ks.containsAlias(KEY_ALIAS)) return null
        val cert = ks.getCertificate(KEY_ALIAS) ?: return null
        val b64 = Base64.encodeToString(cert.publicKey.encoded, Base64.NO_WRAP)
        "-----BEGIN PUBLIC KEY-----\n$b64\n-----END PUBLIC KEY-----"
    }.getOrNull()
}
