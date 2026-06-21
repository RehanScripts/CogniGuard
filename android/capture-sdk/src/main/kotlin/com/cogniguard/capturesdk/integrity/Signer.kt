package com.cogniguard.capturesdk.integrity

import com.cogniguard.capturesdk.model.SignedBehaviorPayload
import com.cogniguard.capturesdk.model.UnsignedBehaviorPayload
import java.security.MessageDigest
import java.time.Instant
import java.util.concurrent.atomic.AtomicLong
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * `key = sha256(signingSecret + nonce)`, `msg = nonce + canonical(metrics) +
 * fingerprint + ts` -- mirrors `gateway/app/services/integrity.py::compute_signature`
 * and `behavior-sdk/src/payload.ts::signPayload` exactly (Implementation.md Phase
 * 17/18). `ts` uses `Instant.now().toString()` (`...Z` suffix, ISO-8601), the same
 * format `new Date().toISOString()` already produces on the web side and that the
 * gateway's `datetime.fromisoformat` (Python 3.11+) already parses successfully.
 */
object Signer {
    private val seqCounter = AtomicLong(0)

    /** Resets the monotonic seq counter -- call on a fresh login/session (a fresh
     * nonce cycle), matching the server's per-binding Redis floor starting back at 0
     * (mirrors `behavior-sdk/src/payload.ts::resetSequence`). */
    fun resetSequence() {
        seqCounter.set(0)
    }

    private fun sha256(bytes: ByteArray): ByteArray = MessageDigest.getInstance("SHA-256").digest(bytes)

    private fun hmacSha256Hex(signingSecret: String, nonce: String, msg: String): String {
        val keyBytes = sha256((signingSecret + nonce).toByteArray(Charsets.UTF_8))
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(keyBytes, "HmacSHA256"))
        val sig = mac.doFinal(msg.toByteArray(Charsets.UTF_8))
        // Byte is signed in Kotlin/Java -- formatting it directly with "%02x" lets
        // Java's Formatter sign-extend any byte >= 0x80 to a 4-byte int (e.g. -1 ->
        // "ffffffff" instead of "ff"), silently producing an 8-hex-char run instead of
        // 2 and corrupting every digest byte with its high bit set. Mask to the low 8
        // bits first.
        return sig.joinToString("") { "%02x".format(it.toInt() and 0xFF) }
    }

    fun sign(
        partial: UnsignedBehaviorPayload,
        nonce: String,
        signingSecret: String,
        ts: String = Instant.now().toString(),
    ): SignedBehaviorPayload {
        val seq = seqCounter.incrementAndGet()
        val canonicalStr = canonical(buildCanonicalMetricsTree(partial))
        val msg = nonce + canonicalStr + partial.device.fingerprint + ts
        val sig = hmacSha256Hex(signingSecret, nonce, msg)
        return SignedBehaviorPayload(unsigned = partial, nonce = nonce, seq = seq, ts = ts, integritySig = sig)
    }
}
