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

    /** Regression: plain `Double.toString()` renders scientific notation differently
     * from Python's `json.dumps` (uppercase `E`, different fixed/scientific threshold,
     * unsigned/unpadded exponent) -- a near-zero accelerometer-variance reading on an
     * emulator (`2.456228868932351e-25`) hits exactly this gap and silently corrupts
     * the HMAC the gateway recomputes from its own (Python) canonicalization. Expected
     * strings below are `json.dumps(v)` computed against the live gateway's Python. */
    @Test
    fun pythonFloatRepr_matchesPythonJsonDumpsAcrossNotationBoundaries() {
        val cases = mapOf(
            2.456228868932351e-25 to "2.456228868932351e-25",
            0.0001 to "0.0001",
            0.00001 to "1e-05",
            1e16 to "1e+16",
            1e15 to "1000000000000000.0",
            1e17 to "1e+17",
            -2.5e-30 to "-2.5e-30",
            123.456 to "123.456",
            0.0 to "0.0",
            -0.0 to "-0.0",
            4.2 to "4.2",
            812.5 to "812.5",
            0.0731 to "0.0731",
            350.0 to "350.0",
            12.0 to "12.0",
            289244.7756872493 to "289244.7756872493",
            1.0 to "1.0",
            100.0 to "100.0",
            -42.5 to "-42.5",
            5e-5 to "5e-05",
            9999999999999998.0 to "9999999999999998.0",
        )
        for ((input, expected) in cases) {
            assertEquals("pythonFloatRepr($input)", expected, pythonFloatRepr(input))
        }
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
