package com.cogniguard.capturesdk

import android.text.Editable
import android.text.TextWatcher
import android.widget.EditText
import com.cogniguard.capturesdk.model.KeyEvent

/**
 * Inter-key timing capture via `TextWatcher` (Implementation.md Phase 18) -- Android's
 * soft keyboard does not surface physical key-down/key-up events the way a web
 * `keydown`/`keyup` listener does, so (like most mobile biometric SDKs) this derives
 * timing from consecutive text-change callbacks instead: each character commit is one
 * `KeyEvent`, with `down`/`up` both the same callback's elapsed time (a soft keyboard
 * gives no separate physical press/release instants), and `key` is the same "x"
 * placeholder convention as the web SDK -- NEVER the real character; "Backspace"
 * tracked when the text shrinks (CLAUDE.md security rule: raw password keystroke
 * *content* is never captured, only timings).
 *
 * Never sent raw -- `derivedFeatures()` folds this into the same `typing_speed`/
 * `key_latency_avg`/`typing_rhythm_std`/`hold_time_avg` dims
 * `training/datasets/cmu.py` reduces web's raw keystroke events into, so a
 * mobile-derived window means the same thing as a server-reduced web one.
 */
class KeystrokeCapture(private val fieldId: String) {
    private val events = mutableListOf<KeyEvent>()
    private var lastLength = 0
    private val startedAtMs = System.nanoTime() / 1_000_000

    private fun elapsedMs(): Double = (System.nanoTime() / 1_000_000 - startedAtMs).toDouble()

    private val watcher =
        object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {
                lastLength = s?.length ?: 0
            }

            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}

            override fun afterTextChanged(s: Editable?) {
                val newLength = s?.length ?: 0
                val now = elapsedMs()
                val key = if (newLength < lastLength) "Backspace" else "x"
                events.add(KeyEvent(key = key, down = now, up = now))
            }
        }

    /** `field_id` -- never the field's actual content, just an identifier ("username",
     * "password", "amount", ...), same as the web SDK's `KeystrokeBlock.field_id`. */
    fun fieldId(): String = fieldId

    /** Typing-dimension derived features, computed from this capture's own buffered
     * `down` timestamps. Returns `emptyMap()` with fewer than 2 events (no interval to
     * measure yet). Does not consume the buffer -- call `reset()` separately once a
     * payload has actually been built and sent. */
    fun derivedFeatures(): Map<String, Double> {
        if (events.size < 2) return emptyMap()
        val downs = events.map { it.down }
        val intervals = downs.zipWithNext { a, b -> b - a }
        val meanInterval = intervals.average()
        val variance = intervals.map { (it - meanInterval) * (it - meanInterval) }.average()
        val holdTimes = events.map { it.up - it.down }
        val elapsedS = ((downs.last() - downs.first()) / 1000.0).coerceAtLeast(0.001)
        return mapOf(
            "typing_speed" to events.size / elapsedS,
            "key_latency_avg" to meanInterval,
            "typing_rhythm_std" to kotlin.math.sqrt(variance),
            "hold_time_avg" to holdTimes.average(),
        )
    }

    fun reset() {
        events.clear()
    }

    companion object {
        fun attach(editText: EditText, fieldId: String): KeystrokeCapture {
            val capture = KeystrokeCapture(fieldId)
            editText.addTextChangedListener(capture.watcher)
            return capture
        }
    }
}
