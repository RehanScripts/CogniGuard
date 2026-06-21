package com.cogniguard.capturesdk.integrity

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.cogniguard.capturesdk.model.ActionBlock
import com.cogniguard.capturesdk.model.ContextBlock
import com.cogniguard.capturesdk.model.DeviceInfo
import com.cogniguard.capturesdk.model.UnsignedBehaviorPayload
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

/** Implementation.md Phase 18 acceptance check: `canonical_metrics()` output for the
 * golden mobile payload matches the shared fixture string exactly -- same vector
 * `gateway/tests/test_integrity_mobile.py` and `behavior-sdk/src/payload.test.ts`
 * assert against. */
@RunWith(AndroidJUnit4::class)
class CanonicalTest {
    @Test
    fun canonicalMetricsTree_matchesTheGoldenVectorExactly() {
        val golden = loadGoldenVector(InstrumentationRegistry.getInstrumentation().context)
        val unsigned = goldenUnsignedPayload(golden)

        val canonicalStr = canonical(buildCanonicalMetricsTree(unsigned))
        assertEquals(golden.getString("canonical"), canonicalStr)
    }
}

internal fun loadGoldenVector(context: android.content.Context): JSONObject {
    val text =
        context.assets.open("golden_canonical_mobile.json").bufferedReader(Charsets.UTF_8).use { it.readText() }
    return JSONObject(text)
}

internal fun goldenUnsignedPayload(golden: JSONObject): UnsignedBehaviorPayload {
    val payload = golden.getJSONObject("payload")
    val derived = payload.getJSONObject("derived_features")
    val context = payload.getJSONObject("context")
    return UnsignedBehaviorPayload(
        channel = payload.getString("channel"),
        source = payload.getString("source"),
        device = DeviceInfo(fingerprint = payload.getJSONObject("device").getString("fingerprint")),
        action = ActionBlock(type = payload.getJSONObject("action").getString("type")),
        keystroke = null,
        mouse = null,
        touch = null,
        derivedFeatures = derived.keys().asSequence().associateWith { derived.getDouble(it) },
        aeReconError = payload.getDouble("ae_recon_error"),
        aeModelVersion = payload.getString("ae_model_version"),
        context =
            ContextBlock(
                submittedAt = context.getString("submitted_at"),
                page = context.getString("page"),
                preTxnDwellMs = context.getDouble("pre_txn_dwell_ms"),
                sessionAgeS = context.getDouble("session_age_s"),
                correctionRate = context.getDouble("correction_rate"),
            ),
    )
}
