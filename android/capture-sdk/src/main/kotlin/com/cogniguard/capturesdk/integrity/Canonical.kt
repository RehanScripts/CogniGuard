package com.cogniguard.capturesdk.integrity

import com.cogniguard.capturesdk.model.UnsignedBehaviorPayload

/**
 * Mirrors `gateway/app/services/integrity.py::canonical_metrics()` and
 * `behavior-sdk/src/payload.ts`'s `canonical()`/`buildCanonicalMetricsTree()`
 * byte-for-byte (Implementation.md Phase 17/18) -- pinned against the shared golden
 * vector in `gateway/tests/fixtures/golden_canonical_mobile.json`, asserted by
 * `CanonicalTest`.
 *
 * `Num`'s `Double` already renders the way Python's `json.dumps` renders a
 * `float`-typed field (always a decimal point, e.g. `12.0` never `12`) -- unlike TS,
 * where a plain `number` covers both int- and float-shaped values and needs a
 * `pyFloat()` wrapper to disambiguate, Kotlin's `Double` vs `Long`/`Int` type
 * distinction makes that wrapper unnecessary here: every leaf that's a Pydantic
 * `float` field is simply typed `Double` in `model/Payload.kt`.
 *
 * String values are emitted via `JSONObject.quote`-equivalent escaping with no
 * `ensure_ascii` (non-ASCII passthrough, like JS's `JSON.stringify`) -- matching
 * `payload.ts`'s `canonical()`, not Python's `json.dumps` default. Every field this
 * project actually signs (device/user identifiers, page names, model versions) is
 * ASCII-only in practice, so this never diverges from the Python side for any real
 * payload; it would only matter for a hypothetical signed field containing non-ASCII
 * text, which doesn't exist on the signed set today.
 */
sealed class CanonicalValue {
    object Null : CanonicalValue()

    data class Str(val value: String) : CanonicalValue()

    data class Num(val value: Double) : CanonicalValue()

    data class Arr(val items: List<CanonicalValue>) : CanonicalValue()

    data class Obj(val entries: Map<String, CanonicalValue>) : CanonicalValue()

    companion object {
        fun of(value: String?): CanonicalValue = if (value == null) Null else Str(value)

        fun of(value: Double?): CanonicalValue = if (value == null) Null else Num(value)
    }
}

private fun escapeString(s: String): String {
    val sb = StringBuilder("\"")
    for (c in s) {
        when (c) {
            '"' -> sb.append("\\\"")
            '\\' -> sb.append("\\\\")
            '\n' -> sb.append("\\n")
            '\r' -> sb.append("\\r")
            '\t' -> sb.append("\\t")
            else -> sb.append(c)
        }
    }
    sb.append("\"")
    return sb.toString()
}

/**
 * Python `repr(float)` / `json.dumps` formatting -- NOT plain `Double.toString()`.
 *
 * Both Java and Python choose the same *shortest round-tripping* decimal digits for a
 * given double (this is the well-known convergence point of every modern
 * shortest-round-trip algorithm, Java's included), but they disagree on *presentation*:
 * Java switches to scientific notation outside `[1e-3, 1e7)`, uses an uppercase `E`, and
 * never signs/pads the exponent (`"2.46E-25"`); Python switches outside
 * `(1e-4, 1e16]`, uses lowercase `e`, and always signs the exponent with a >=2-digit pad
 * (`"2.46e-25"`). A telemetry feature that lands in the gap between those two
 * thresholds (e.g. a near-zero accelerometer-variance reading on an emulator,
 * `2.456228868932351e-25`) renders differently on each side, corrupting the HMAC the
 * gateway recomputes from its own (Python) canonicalization. Fixed by re-deriving
 * Java's chosen digits + decimal-point position from its own `toString()` output, then
 * re-rendering them with Python's notation rules instead of Java's.
 */
internal fun pythonFloatRepr(value: Double): String {
    if (value == 0.0) return if (1.0 / value < 0) "-0.0" else "0.0"
    val negative = value < 0
    val javaStr = Math.abs(value).toString()

    val digits: String
    val decpt: Int
    val eIdx = javaStr.indexOf('E')
    if (eIdx >= 0) {
        val mantissa = javaStr.substring(0, eIdx)
        val exp = javaStr.substring(eIdx + 1).toInt()
        val dotIdx = mantissa.indexOf('.')
        val intPart = mantissa.substring(0, dotIdx)
        val fracPart = mantissa.substring(dotIdx + 1)
        val allDigits = (intPart + fracPart).trimEnd('0')
        digits = allDigits.ifEmpty { "0" }
        decpt = intPart.length + exp
    } else {
        val dotIdx = javaStr.indexOf('.')
        val intPart = javaStr.substring(0, dotIdx)
        val fracPart = javaStr.substring(dotIdx + 1)
        if (intPart == "0") {
            val leadingZeros = fracPart.indexOfFirst { it != '0' }.let { if (it < 0) fracPart.length else it }
            val allDigits = fracPart.substring(leadingZeros).trimEnd('0')
            digits = allDigits.ifEmpty { "0" }
            decpt = -leadingZeros
        } else {
            val allDigits = (intPart + fracPart).trimEnd('0')
            digits = allDigits.ifEmpty { "0" }
            decpt = intPart.length
        }
    }

    val sign = if (negative) "-" else ""
    return when {
        decpt <= -4 || decpt > 16 -> {
            // Python scientific notation: lowercase `e`, always-signed, >=2-digit exponent.
            val mantissaDigits = if (digits.length == 1) digits + "0" else digits
            val mantissaStr = "${mantissaDigits[0]}.${mantissaDigits.substring(1)}"
            val exp = decpt - 1
            val expSign = if (exp < 0) "-" else "+"
            val expAbs = Math.abs(exp).toString().padStart(2, '0')
            "$sign${mantissaStr}e$expSign$expAbs"
        }
        decpt <= 0 -> "${sign}0." + "0".repeat(-decpt) + digits
        decpt >= digits.length -> "$sign$digits" + "0".repeat(decpt - digits.length) + ".0"
        else -> "$sign${digits.substring(0, decpt)}.${digits.substring(decpt)}"
    }
}

fun canonical(value: CanonicalValue): String =
    when (value) {
        is CanonicalValue.Null -> "null"
        is CanonicalValue.Str -> escapeString(value.value)
        is CanonicalValue.Num -> pythonFloatRepr(value.value)
        is CanonicalValue.Arr -> "[" + value.items.joinToString(",") { canonical(it) } + "]"
        is CanonicalValue.Obj -> {
            val sortedKeys = value.entries.keys.sorted()
            "{" +
                sortedKeys.joinToString(",") { k -> "${escapeString(k)}:${canonical(value.entries.getValue(k))}" } +
                "}"
        }
    }

/** Same field order/shape as `payload.ts::buildCanonicalMetricsTree` and
 * `integrity.py::canonical_metrics` -- order is irrelevant to the output (every
 * `Obj` is key-sorted before emission), but keeping it identical makes the two
 * implementations easy to diff by eye. */
fun buildCanonicalMetricsTree(p: UnsignedBehaviorPayload): CanonicalValue.Obj {
    val keystroke =
        p.keystroke?.let { ks ->
            CanonicalValue.Obj(
                mapOf(
                    "events" to
                        CanonicalValue.Arr(
                            ks.events.map { e ->
                                CanonicalValue.Obj(
                                    mapOf(
                                        "key" to CanonicalValue.of(e.key),
                                        "down" to CanonicalValue.of(e.down),
                                        "up" to CanonicalValue.of(e.up),
                                    ),
                                )
                            },
                        ),
                    "field_id" to CanonicalValue.of(ks.fieldId),
                ),
            )
        } ?: CanonicalValue.Null

    val mouse =
        p.mouse?.let { m ->
            CanonicalValue.Obj(
                mapOf(
                    "moves" to
                        CanonicalValue.Arr(
                            m.moves.map { mv ->
                                CanonicalValue.Obj(
                                    mapOf(
                                        "x" to CanonicalValue.of(mv.x),
                                        "y" to CanonicalValue.of(mv.y),
                                        "t" to CanonicalValue.of(mv.t),
                                    ),
                                )
                            },
                        ),
                    "clicks" to
                        CanonicalValue.Arr(
                            m.clicks.map { c ->
                                CanonicalValue.Obj(
                                    mapOf(
                                        "t" to CanonicalValue.of(c.t),
                                        "dur" to CanonicalValue.of(c.dur),
                                    ),
                                )
                            },
                        ),
                ),
            )
        } ?: CanonicalValue.Null

    val touch =
        p.touch?.let { t ->
            CanonicalValue.Obj(
                mapOf(
                    "swipes" to
                        CanonicalValue.Arr(
                            t.swipes.map { s ->
                                CanonicalValue.Obj(
                                    mapOf(
                                        "len" to CanonicalValue.of(s.len),
                                        "dur" to CanonicalValue.of(s.dur),
                                        "vx" to CanonicalValue.of(s.vx),
                                        "vy" to CanonicalValue.of(s.vy),
                                    ),
                                )
                            },
                        ),
                ),
            )
        } ?: CanonicalValue.Null

    val derivedFeatures =
        p.derivedFeatures?.let { df ->
            CanonicalValue.Obj(df.mapValues { (_, v) -> CanonicalValue.of(v) })
        } ?: CanonicalValue.Null

    return CanonicalValue.Obj(
        mapOf(
            "channel" to CanonicalValue.of(p.channel),
            "source" to CanonicalValue.of(p.source),
            "action" to CanonicalValue.Obj(mapOf("type" to CanonicalValue.of(p.action.type))),
            "keystroke" to keystroke,
            "mouse" to mouse,
            "touch" to touch,
            "derived_features" to derivedFeatures,
            "ae_recon_error" to CanonicalValue.of(p.aeReconError),
            "ae_model_version" to CanonicalValue.of(p.aeModelVersion),
            "context" to
                CanonicalValue.Obj(
                    mapOf(
                        "submitted_at" to CanonicalValue.of(p.context.submittedAt),
                        "page" to CanonicalValue.of(p.context.page),
                        "pre_txn_dwell_ms" to CanonicalValue.of(p.context.preTxnDwellMs),
                        "session_age_s" to CanonicalValue.of(p.context.sessionAgeS),
                        "correction_rate" to CanonicalValue.of(p.context.correctionRate),
                    ),
                ),
        ),
    )
}
