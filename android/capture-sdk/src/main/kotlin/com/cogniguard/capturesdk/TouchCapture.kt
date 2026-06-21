package com.cogniguard.capturesdk

import android.view.MotionEvent
import android.view.View
import com.cogniguard.capturesdk.model.TouchSwipe
import kotlin.math.hypot

/** Swipe capture via `View.OnTouchListener` (Implementation.md Phase 18) -- mirrors
 * the web SDK's pointer-drag swipe summary (`len`,`dur`,`vx`,`vy`) field-for-field,
 * feeding `edge.MobileFeatures.extract`'s `swipe_velocity_norm`/`swipe_angle_dev`. */
class TouchCapture : View.OnTouchListener {
    private val swipes = mutableListOf<TouchSwipe>()
    private var startX = 0f
    private var startY = 0f
    private var startTimeMs = 0L

    override fun onTouch(v: View?, event: MotionEvent?): Boolean {
        event ?: return false
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                startX = event.rawX
                startY = event.rawY
                startTimeMs = event.eventTime
            }
            MotionEvent.ACTION_UP -> {
                val dx = (event.rawX - startX).toDouble()
                val dy = (event.rawY - startY).toDouble()
                val durMs = (event.eventTime - startTimeMs).toDouble()
                if (durMs > 0) {
                    val len = hypot(dx, dy)
                    swipes.add(TouchSwipe(len = len, dur = durMs, vx = dx / durMs, vy = dy / durMs))
                }
            }
        }
        return false // never consume -- the underlying view still needs normal touch handling
    }

    fun drain(): List<TouchSwipe> {
        val copy = swipes.toList()
        swipes.clear()
        return copy
    }
}
