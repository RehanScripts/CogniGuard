package com.cogniguard.capturesdk.model

/**
 * Mirrors `gateway/app/schemas/behavior.py::BehaviorPayload` field-for-field
 * (Implementation.md Phase 18), the same way `behavior-sdk/src/types.ts` does for the
 * web SDK. Kept as plain data classes (no JSON-library annotations) -- the wire
 * encoding lives entirely in `net/CogniGuardClient.kt`'s explicit
 * `JSONObject`/`JSONArray` construction, so there is exactly one place that has to
 * agree on snake_case field names with the gateway, not two.
 */
data class KeyEvent(val key: String, val down: Double, val up: Double)

data class KeystrokeBlock(val events: List<KeyEvent>, val fieldId: String)

data class MouseMove(val x: Double, val y: Double, val t: Double)

data class MouseClick(val t: Double, val dur: Double)

data class MouseBlock(val moves: List<MouseMove>, val clicks: List<MouseClick>)

data class TouchSwipe(val len: Double, val dur: Double, val vx: Double, val vy: Double)

data class TouchBlock(val swipes: List<TouchSwipe>)

data class DeviceInfo(
    val fingerprint: String,
    val ua: String = "",
    val screen: String = "",
    val timezone: String = "",
    val language: String = "",
    val platform: String = "android",
    val isRooted: Boolean = false,
    val isEmulator: Boolean = false,
)

data class ActionBlock(val type: String = "LOGIN")

data class ContextBlock(
    val submittedAt: String = "",
    val page: String = "",
    val preTxnDwellMs: Double = 0.0,
    val sessionAgeS: Double = 0.0,
    val correctionRate: Double = 0.0,
)

/** The unsigned half of `BehaviorPayload` -- mirrors `behavior-sdk/src/payload.ts`'s
 * `UnsignedPayload` (`Omit<BehaviorPayload, "nonce"|"seq"|"ts"|"integrity_sig">`).
 * `Signer.sign()` fills in the signature envelope to produce a `SignedBehaviorPayload`. */
data class UnsignedBehaviorPayload(
    val channel: String,
    val source: String = "mobile_edge",
    val device: DeviceInfo,
    val action: ActionBlock = ActionBlock(),
    val keystroke: KeystrokeBlock? = null,
    val mouse: MouseBlock? = null,
    val touch: TouchBlock? = null,
    val derivedFeatures: Map<String, Double>? = null,
    val aeReconError: Double? = null,
    val aeModelVersion: String? = null,
    val context: ContextBlock = ContextBlock(),
)

data class SignedBehaviorPayload(
    val unsigned: UnsignedBehaviorPayload,
    val nonce: String,
    val seq: Long,
    val ts: String,
    val integritySig: String,
)
