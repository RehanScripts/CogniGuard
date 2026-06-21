package com.cogniguard.capturesdk

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import com.cogniguard.capturesdk.edge.MotionSample

/** Accelerometer sampling (Implementation.md Phase 18, NFR-10) -- raw samples never
 * leave this object; only `edge.MobileFeatures.extract`'s derived
 * `acceleration_variance` is ever sent (mirrors `derived_features`'s edge-extraction
 * contract -- the same data-minimization rule that keeps raw keystroke/touch series
 * off the wire). */
class MotionCapture(context: Context) : SensorEventListener {
    private val sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val accelerometer: Sensor? = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
    private val samples = mutableListOf<MotionSample>()

    fun start() {
        accelerometer?.let { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_UI) }
    }

    fun stop() {
        sensorManager.unregisterListener(this)
    }

    override fun onSensorChanged(event: SensorEvent?) {
        event ?: return
        samples.add(MotionSample(x = event.values[0].toDouble(), y = event.values[1].toDouble(), z = event.values[2].toDouble()))
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    fun drain(): List<MotionSample> {
        val copy = samples.toList()
        samples.clear()
        return copy
    }
}
