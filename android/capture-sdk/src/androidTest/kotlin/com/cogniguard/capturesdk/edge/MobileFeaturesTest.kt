package com.cogniguard.capturesdk.edge

import androidx.test.ext.junit.runners.AndroidJUnit4
import com.cogniguard.capturesdk.model.TouchSwipe
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.math.PI
import kotlin.math.sqrt

/** Implementation.md Phase 18 acceptance check: matches
 * `behavior-sdk/src/edge.test.ts`'s reference values exactly -- same inputs, same
 * expected outputs, both files. */
@RunWith(AndroidJUnit4::class)
class MobileFeaturesTest {
    @Test
    fun swipeVelocityNorm_isTheMeanOfHypotVxVy() {
        val swipes =
            listOf(
                TouchSwipe(len = 0.0, dur = 0.0, vx = 3.0, vy = 4.0), // hypot = 5
                TouchSwipe(len = 0.0, dur = 0.0, vx = 0.0, vy = 1.0), // hypot = 1
            )
        val features = MobileFeatures.extract(swipes)
        assertEquals(3.0, features.getValue("swipe_velocity_norm"), 1e-5) // (5+1)/2
    }

    @Test
    fun swipeAngleDev_isPopulationStdevOfAtan2_onlyWhenMoreThanOneSwipe() {
        val single = listOf(TouchSwipe(len = 0.0, dur = 0.0, vx = 1.0, vy = 0.0))
        assertNull(MobileFeatures.extract(single)["swipe_angle_dev"])

        val swipes =
            listOf(
                TouchSwipe(len = 0.0, dur = 0.0, vx = 1.0, vy = 0.0), // angle 0
                TouchSwipe(len = 0.0, dur = 0.0, vx = 0.0, vy = 1.0), // angle pi/2
            )
        val angles = listOf(0.0, PI / 2)
        val m = (angles[0] + angles[1]) / 2
        val expected = sqrt(((angles[0] - m) * (angles[0] - m) + (angles[1] - m) * (angles[1] - m)) / 2)
        assertEquals(expected, MobileFeatures.extract(swipes).getValue("swipe_angle_dev"), 1e-10)
    }

    @Test
    fun touchPressureAvg_isTheMeanOfPressureSamples() {
        val features = MobileFeatures.extract(emptyList(), listOf(0.2, 0.4, 0.6))
        assertEquals(0.4, features.getValue("touch_pressure_avg"), 1e-10)
    }

    @Test
    fun accelerationVariance_isThePopulationVarianceOfMotionMagnitude() {
        val features =
            MobileFeatures.extract(
                emptyList(),
                emptyList(),
                listOf(MotionSample(1.0, 0.0, 0.0), MotionSample(3.0, 0.0, 0.0)),
            )
        // magnitudes [1,3], mean=2, pvariance = ((1-2)^2+(3-2)^2)/2 = 1
        assertEquals(1.0, features.getValue("acceleration_variance"), 1e-10)
    }

    @Test
    fun omitsDimsItHasNoSamplesFor_ratherThanDefaultingToZero() {
        val features = MobileFeatures.extract(emptyList())
        assertEquals(emptyMap<String, Double>(), features)
    }
}
