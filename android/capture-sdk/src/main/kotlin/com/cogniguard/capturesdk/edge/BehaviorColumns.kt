package com.cogniguard.capturesdk.edge

/** Mirrors `training/datasets/behavior_columns.py::BEHAVIOR_COLUMNS` exactly -- the
 * column order the LSTM Autoencoder was trained on, and the same order
 * `gateway/app/services/feature_reader.py` assembles server-side for the web path's
 * AE sequence buffer. Dims this channel doesn't capture are 0.0. */
object BehaviorColumns {
    val ORDER =
        listOf(
            "typing_speed",
            "key_latency_avg",
            "typing_rhythm_std",
            "hold_time_avg",
            "swipe_velocity_norm",
            "swipe_angle_dev",
            "touch_pressure_avg",
            "acceleration_variance",
            "mouse_velocity_mean",
        )

    fun toRow(features: Map<String, Double>): DoubleArray = DoubleArray(ORDER.size) { i -> features[ORDER[i]] ?: 0.0 }
}
