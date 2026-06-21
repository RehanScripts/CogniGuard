package com.cogniguard.capturesdk.fingerprint

import android.content.Context
import android.os.Build
import android.provider.Settings
import com.cogniguard.capturesdk.model.DeviceInfo
import com.cogniguard.capturesdk.security.RootDetection
import java.security.MessageDigest
import java.util.Locale
import java.util.TimeZone

/**
 * Mirrors `behavior-sdk/src/fingerprint.ts::computeFingerprint` (Implementation.md
 * Phase 18) -- same `SHA-256(ua|screen|timezone|language|<entropy>)` shape, with
 * Android's `Settings.Secure.ANDROID_ID` standing in for the web canvas hash as the
 * "stable per-install entropy" component (a canvas fingerprint has no Android
 * equivalent; `ANDROID_ID` is the platform's own stable-per-install identifier).
 */
object DeviceFingerprint {
    private fun sha256Hex(input: String): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(input.toByteArray(Charsets.UTF_8))
        // See Signer.kt's hmacSha256Hex for why the mask is required: an unmasked
        // signed Byte >= 0x80 sign-extends under "%02x", corrupting the hex output.
        return digest.joinToString("") { "%02x".format(it.toInt() and 0xFF) }
    }

    fun compute(context: Context): DeviceInfo {
        val ua = "cogniguard-android/${Build.VERSION.RELEASE}"
        val metrics = context.resources.displayMetrics
        val screen = "${metrics.widthPixels}x${metrics.heightPixels}"
        val timezone = TimeZone.getDefault().id
        val language = Locale.getDefault().toLanguageTag()
        val androidId =
            try {
                Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID) ?: ""
            } catch (e: Exception) {
                ""
            }

        val fingerprint = sha256Hex(listOf(ua, screen, timezone, language, androidId).joinToString("|"))

        return DeviceInfo(
            fingerprint = fingerprint,
            ua = ua,
            screen = screen,
            timezone = timezone,
            language = language,
            platform = "android",
            isRooted = RootDetection.isRooted(context),
            isEmulator = RootDetection.isEmulator(),
        )
    }
}
