package com.cogniguard.capturesdk.ml

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.math.abs

/** Implementation.md Phase 18 acceptance check: on-device recon error within
 * tolerance of the ONNX server model on the same input. `ae_reference_window.json`'s
 * `expected_recon_error` is `gateway/app/scoring/autoencoder.py::reconstruction_error`
 * run against the real production `lstm_autoencoder.onnx` artifact on this exact
 * window (see that fixture's `_comment` for the cross-check against the matching
 * `.tflite` artifact). Requires `model.tflite` to be present in `assets/` (see
 * `android/README.md`) -- skips rather than fails if it's missing, the same
 * "fresh/lean checkout" tolerance `test_train_lstm_autoencoder.py`'s
 * `pytest.importorskip` uses for its own optional heavy dependency.
 */
@RunWith(AndroidJUnit4::class)
class AutoencoderTFLiteTest {
    @Test
    fun reconstructionError_isWithinToleranceOfTheOnnxServerModel() {
        val testContext = InstrumentationRegistry.getInstrumentation().context
        val targetContext = InstrumentationRegistry.getInstrumentation().targetContext

        val hasModel =
            try {
                targetContext.assets.open("model.tflite").close()
                true
            } catch (e: java.io.IOException) {
                false
            }
        if (!hasModel) return // see android/README.md -- model.tflite is gitignored, copied in manually

        val referenceText =
            testContext.assets.open("ae_reference_window.json").bufferedReader(Charsets.UTF_8).use {
                it.readText()
            }
        val reference = JSONObject(referenceText)
        val expected = reference.getDouble("expected_recon_error")
        val windowArr = reference.getJSONArray("window")
        val window =
            Array(windowArr.length()) { i ->
                val row = windowArr.getJSONArray(i)
                DoubleArray(row.length()) { j -> row.getDouble(j) }
            }

        val model = AutoencoderTFLite.fromAsset(targetContext)
        try {
            val actual = model.reconstructionError(window)
            val relativeDiff = abs(actual - expected) / expected
            assertTrue(
                "recon error $actual too far from expected $expected (relative diff $relativeDiff)",
                relativeDiff < 1e-3,
            )
        } finally {
            model.close()
        }
    }
}
