package com.cogniguard.capturesdk.integrity

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test
import org.junit.runner.RunWith

/** Implementation.md Phase 18 acceptance check: the HMAC over the golden mobile
 * payload's canonical string matches the shared fixture signature exactly. */
@RunWith(AndroidJUnit4::class)
class SignerTest {
    @Test
    fun signedIntegritySig_matchesTheGoldenVectorExactly() {
        val golden = loadGoldenVector(InstrumentationRegistry.getInstrumentation().context)
        val payload = golden.getJSONObject("payload")
        val unsigned = goldenUnsignedPayload(golden)

        val signed =
            Signer.sign(
                unsigned,
                nonce = payload.getString("nonce"),
                signingSecret = golden.getString("secret"),
                ts = payload.getString("ts"),
            )

        assertEquals(golden.getString("integrity_sig"), signed.integritySig)
    }

    @Test
    fun changingAeReconError_changesTheSignature() {
        val golden = loadGoldenVector(InstrumentationRegistry.getInstrumentation().context)
        val payload = golden.getJSONObject("payload")
        val unsigned = goldenUnsignedPayload(golden)
        val tampered = unsigned.copy(aeReconError = 0.9)

        val nonce = payload.getString("nonce")
        val secret = golden.getString("secret")
        val ts = payload.getString("ts")
        val baseline = Signer.sign(unsigned, nonce, secret, ts)
        val tamperedSigned = Signer.sign(tampered, nonce, secret, ts)

        assertNotEquals(baseline.integritySig, tamperedSigned.integritySig)
    }

    @Test
    fun changingAeModelVersion_changesTheSignature() {
        val golden = loadGoldenVector(InstrumentationRegistry.getInstrumentation().context)
        val payload = golden.getJSONObject("payload")
        val unsigned = goldenUnsignedPayload(golden)
        val tampered = unsigned.copy(aeModelVersion = "lstm_autoencoder@2099-01-01")

        val nonce = payload.getString("nonce")
        val secret = golden.getString("secret")
        val ts = payload.getString("ts")
        val baseline = Signer.sign(unsigned, nonce, secret, ts)
        val tamperedSigned = Signer.sign(tampered, nonce, secret, ts)

        assertNotEquals(baseline.integritySig, tamperedSigned.integritySig)
    }
}
