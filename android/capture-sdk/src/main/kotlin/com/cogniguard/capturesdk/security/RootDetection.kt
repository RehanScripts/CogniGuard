package com.cogniguard.capturesdk.security

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import java.io.File

/**
 * Best-effort heuristic root/emulator detection (Implementation.md Phase 18) -- feeds
 * `DeviceInfo.is_rooted`/`is_emulator`, which the decision engine already folds into
 * device trust (Phase 6/7). Heuristic, not a hard security boundary: a sufficiently
 * determined attacker can hide root from any userspace check -- the same caveat
 * `behavior-sdk/src/fingerprint.ts::detectRooted`'s web stub already documents; this
 * is that stub's real implementation, now that a native shell actually exists.
 */
object RootDetection {
    private val ROOT_INDICATOR_PATHS =
        listOf(
            "/system/app/Superuser.apk",
            "/sbin/su",
            "/system/bin/su",
            "/system/xbin/su",
            "/data/local/xbin/su",
            "/data/local/bin/su",
            "/system/sd/xbin/su",
            "/system/bin/failsafe/su",
            "/data/local/su",
            "/su/bin/su",
        )

    private val ROOT_MANAGEMENT_PACKAGES =
        listOf(
            "com.noshufou.android.su",
            "com.koushikdutta.superuser",
            "eu.chainfire.supersu",
            "com.topjohnwu.magisk",
        )

    fun isRooted(context: Context? = null): Boolean {
        return checkRootIndicatorPaths() ||
            checkTestKeysBuildTag() ||
            checkSuOnPath() ||
            (context != null && checkRootManagementApps(context))
    }

    private fun checkRootIndicatorPaths(): Boolean = ROOT_INDICATOR_PATHS.any { File(it).exists() }

    private fun checkTestKeysBuildTag(): Boolean = Build.TAGS?.contains("test-keys") == true

    private fun checkSuOnPath(): Boolean =
        try {
            val process = Runtime.getRuntime().exec(arrayOf("which", "su"))
            process.inputStream.bufferedReader().readLine() != null
        } catch (e: Exception) {
            false
        }

    private fun checkRootManagementApps(context: Context): Boolean {
        val pm = context.packageManager
        return ROOT_MANAGEMENT_PACKAGES.any { pkg ->
            try {
                pm.getPackageInfo(pkg, 0)
                true
            } catch (e: PackageManager.NameNotFoundException) {
                false
            }
        }
    }

    /** Standard build-fingerprint/hardware heuristics for the AOSP and Genymotion
     * emulators -- the same checks most Android biometric/fraud SDKs use. */
    fun isEmulator(): Boolean {
        val fingerprint = Build.FINGERPRINT ?: ""
        val model = Build.MODEL ?: ""
        val manufacturer = Build.MANUFACTURER ?: ""
        val brand = Build.BRAND ?: ""
        val product = Build.PRODUCT ?: ""
        val hardware = Build.HARDWARE ?: ""

        return fingerprint.startsWith("generic") ||
            fingerprint.startsWith("unknown") ||
            model.contains("google_sdk") ||
            model.contains("Emulator") ||
            model.contains("Android SDK built for x86") ||
            manufacturer.contains("Genymotion") ||
            (brand.startsWith("generic") && product.startsWith("sdk")) ||
            product == "google_sdk" ||
            product.contains("sdk_gphone") ||
            hardware.contains("goldfish") ||
            hardware.contains("ranchu")
    }
}
