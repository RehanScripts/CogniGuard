package com.cogniguard.capturesdk.edge

import com.cogniguard.capturesdk.model.TouchSwipe
import kotlin.math.atan2
import kotlin.math.hypot
import kotlin.math.sqrt

data class MotionSample(val x: Double, val y: Double, val z: Double)

private fun mean(values: List<Double>): Double = values.sum() / values.size

/** Population variance/stdev (denominator N, not N-1) -- matches
 * `gateway/app/services/feature_reader.py`'s `statistics.pvariance`/`pstdev` and
 * `behavior-sdk/src/edge.ts`'s identical helper (Implementation.md Phase 18). */
private fun pvariance(values: List<Double>): Double {
    val m = mean(values)
    return mean(values.map { (it - m) * (it - m) })
}

private fun pstdev(values: List<Double>): Double = sqrt(pvariance(values))

private fun magnitude3(x: Double, y: Double, z: Double): Double = sqrt(x * x + y * y + z * z)

/**
 * Mobile edge feature extraction (NFR-10): raw touch/sensor streams never leave the
 * device -- only this derived feature vector is sent, folding into `derived_features`.
 * Mirrors `behavior-sdk/src/edge.ts::extractMobileFeatures` exactly (Implementation.md
 * Phase 18) -- `MobileFeaturesTest` pins both to the same reference values.
 */
object MobileFeatures {
    fun extract(
        swipes: List<TouchSwipe>,
        pressureSamples: List<Double> = emptyList(),
        motionSamples: List<MotionSample> = emptyList(),
    ): Map<String, Double> {
        val features = mutableMapOf<String, Double>()

        if (swipes.isNotEmpty()) {
            features["swipe_velocity_norm"] = mean(swipes.map { hypot(it.vx, it.vy) })
            if (swipes.size > 1) {
                features["swipe_angle_dev"] = pstdev(swipes.map { atan2(it.vy, it.vx) })
            }
        }

        if (pressureSamples.isNotEmpty()) {
            features["touch_pressure_avg"] = mean(pressureSamples)
        }

        if (motionSamples.isNotEmpty()) {
            val magnitudes = motionSamples.map { magnitude3(it.x, it.y, it.z) }
            features["acceleration_variance"] = pvariance(magnitudes)
        }

        return features
    }
}
