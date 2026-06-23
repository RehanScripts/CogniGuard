package com.cogniguard.capturesdk.net

import com.cogniguard.capturesdk.integrity.Signer
import com.cogniguard.capturesdk.model.SignedBehaviorPayload
import com.cogniguard.capturesdk.model.UnsignedBehaviorPayload
import org.json.JSONArray
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

/**
 * Thin HTTP client mirroring `web-app/src/api.ts` field-for-field (Implementation.md
 * Phase 18) -- the native app's only network surface; activities never open an
 * `HttpURLConnection` directly (same "centralize API calls" convention CLAUDE.md
 * states for the web SDK's `api.ts`).
 *
 * `JSONObject.put(key, null)` removes/omits the key rather than writing JSON `null` --
 * harmless here because every nullable `BehaviorPayload` field defaults to `None`
 * server-side when its key is absent (Pydantic `Optional[...] = None`), the same
 * effective contract as sending an explicit `null`.
 */
class CogniGuardClient(private val apiBase: String, private val signingSecret: String) {
    data class ApiResult(val status: Int, val body: JSONObject)

    private fun request(path: String, method: String, body: JSONObject?, token: String? = null): ApiResult {
        val url = URL("$apiBase$path")
        val conn = url.openConnection() as HttpURLConnection
        try {
            conn.requestMethod = method
            conn.setRequestProperty("Content-Type", "application/json")
            token?.let { conn.setRequestProperty("Authorization", "Bearer $it") }
            conn.doInput = true
            if (body != null) {
                conn.doOutput = true
                OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { it.write(body.toString()) }
            }
            val status = conn.responseCode
            val stream = if (status in 200..299) conn.inputStream else conn.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: "{}"
            return ApiResult(status, JSONObject(text))
        } finally {
            conn.disconnect()
        }
    }

    fun fetchNonce(): String {
        val result = request("/api/v1/auth/nonce", "GET", null)
        return result.body.getString("nonce")
    }

    fun register(username: String, password: String): ApiResult {
        val body = JSONObject().put("username", username).put("password", password)
        return request("/api/v1/auth/register", "POST", body)
    }

    fun setConsent(username: String, action: String = "GRANT", consentVersion: String = "v1"): ApiResult {
        val body =
            JSONObject()
                .put("username", username)
                .put("action", action)
                .put("consent_version", consentVersion)
        return request("/api/v1/auth/consent", "POST", body)
    }

    fun signBehavior(partial: UnsignedBehaviorPayload): JSONObject {
        val nonce = fetchNonce()
        val signed = Signer.sign(partial, nonce, signingSecret)
        return toJson(signed)
    }

    fun login(username: String, password: String, behavior: UnsignedBehaviorPayload): ApiResult {
        val body =
            JSONObject()
                .put("username", username)
                .put("password", password)
                .put("behavior", signBehavior(behavior))
        return request("/api/v1/auth/login", "POST", body)
    }

    /** Step-up verify (Phase 24): OTP/MPIN demo code or a biometric/passkey assertion.
     * Mirrors `web-app/src/api.ts` `verifyStepUp`. */
    fun verifyStepUp(challengeId: String, otpOrAssertion: String): ApiResult {
        val body =
            JSONObject().put("challenge_id", challengeId).put("otp_or_assertion", otpOrAssertion)
        return request("/api/v1/auth/step-up/verify", "POST", body)
    }

    fun ingest(token: String, behavior: UnsignedBehaviorPayload): ApiResult =
        request("/api/v1/behavior/ingest", "POST", signBehavior(behavior), token = token)

    fun scorePayment(
        token: String,
        amount: Double,
        beneficiaryVpa: String?,
        transferType: String,
        behavior: UnsignedBehaviorPayload,
    ): ApiResult {
        val body =
            JSONObject()
                .put("amount", amount)
                .put("beneficiary_vpa", beneficiaryVpa)
                .put("transfer_type", transferType)
                .put("channel", "mobile")
                .put("behavior", signBehavior(behavior))
        return request("/api/v1/payment/score", "POST", body, token = token)
    }

    fun getAeModel(): ApiResult = request("/api/v1/mobile/ae-model", "GET", null)

    fun getAeCalib(userId: String): ApiResult = request("/api/v1/mobile/ae-calib/$userId", "GET", null)

    companion object {
        fun toJson(signed: SignedBehaviorPayload): JSONObject {
            val p = signed.unsigned
            val json = JSONObject()
            json.put("channel", p.channel)
            json.put("source", p.source)
            json.put("nonce", signed.nonce)
            json.put("seq", signed.seq)
            json.put("ts", signed.ts)
            json.put("integrity_sig", signed.integritySig)

            val device =
                JSONObject()
                    .put("fingerprint", p.device.fingerprint)
                    .put("ua", p.device.ua)
                    .put("screen", p.device.screen)
                    .put("timezone", p.device.timezone)
                    .put("language", p.device.language)
                    .put("platform", p.device.platform)
                    .put("is_rooted", p.device.isRooted)
                    .put("is_emulator", p.device.isEmulator)
            json.put("device", device)

            json.put("action", JSONObject().put("type", p.action.type))

            json.put(
                "keystroke",
                p.keystroke?.let { ks ->
                    JSONObject()
                        .put("field_id", ks.fieldId)
                        .put(
                            "events",
                            JSONArray(
                                ks.events.map { e ->
                                    JSONObject().put("key", e.key).put("down", e.down).put("up", e.up)
                                },
                            ),
                        )
                },
            )
            json.put(
                "mouse",
                p.mouse?.let { m ->
                    JSONObject()
                        .put(
                            "moves",
                            JSONArray(m.moves.map { JSONObject().put("x", it.x).put("y", it.y).put("t", it.t) }),
                        )
                        .put(
                            "clicks",
                            JSONArray(m.clicks.map { JSONObject().put("t", it.t).put("dur", it.dur) }),
                        )
                },
            )
            json.put(
                "touch",
                p.touch?.let { t ->
                    JSONObject().put(
                        "swipes",
                        JSONArray(
                            t.swipes.map {
                                JSONObject().put("len", it.len).put("dur", it.dur).put("vx", it.vx).put("vy", it.vy)
                            },
                        ),
                    )
                },
            )
            json.put(
                "derived_features",
                p.derivedFeatures?.let { df ->
                    val obj = JSONObject()
                    df.forEach { (k, v) -> obj.put(k, v) }
                    obj
                },
            )
            json.put("ae_recon_error", p.aeReconError)
            json.put("ae_model_version", p.aeModelVersion)

            json.put(
                "context",
                JSONObject()
                    .put("submitted_at", p.context.submittedAt)
                    .put("page", p.context.page)
                    .put("pre_txn_dwell_ms", p.context.preTxnDwellMs)
                    .put("session_age_s", p.context.sessionAgeS)
                    .put("correction_rate", p.context.correctionRate),
            )
            return json
        }
    }
}
