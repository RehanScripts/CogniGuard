package com.cogniguard.capturesdk.ml

import android.content.Context
import com.cogniguard.capturesdk.edge.BehaviorColumns

/** Per-session rolling window + on-device AE scoring. Owns the bundled
 * `AutoencoderTFLite` interpreter and a ring buffer (oldest row first) of assembled
 * 9-dim rows, left-padding to `SEQ_LEN` the same way
 * `feature_reader.py::_push_and_read_sequence` pads the web path's server-side
 * buffer -- so a session with only 1-2 real rows still produces a usable
 * (mostly-masked) reconstruction error from the very first event. The gateway always
 * receives that error, but only *acts* on it once the session has accumulated `MIN_SEQ`
 * real rows (`feature_reader.py::_resolve_ae` gates AE-as-primary behind the same
 * `MIN_SEQ` warm-up as web); until then a sparse early window biases to `verify` via the
 * IF shadow rather than letting an out-of-distribution error drive a `block`. */
class AeSequenceScorer(context: Context) {
    private val ae = AutoencoderTFLite.fromAsset(context)
    private val rows = mutableListOf<DoubleArray>()

    fun score(features: Map<String, Double>): Double {
        rows.add(BehaviorColumns.toRow(features))
        if (rows.size > AutoencoderTFLite.SEQ_LEN) rows.removeAt(0)

        val padCount = AutoencoderTFLite.SEQ_LEN - rows.size
        val window =
            Array(AutoencoderTFLite.SEQ_LEN) { i ->
                if (i < padCount) DoubleArray(AutoencoderTFLite.N_FEATURES) else rows[i - padCount]
            }
        val mask = BooleanArray(AutoencoderTFLite.SEQ_LEN) { i -> i >= padCount }
        return ae.reconstructionError(window, mask)
    }

    fun close() = ae.close()
}
