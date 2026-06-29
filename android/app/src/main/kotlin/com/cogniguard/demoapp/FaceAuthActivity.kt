package com.cogniguard.demoapp

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.CameraSelector
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

/**
 * Dummy face-auth screen for very_high risk: opens the front camera for ~2 seconds,
 * shows an overlay ("Verifying your identity…"), then auto-closes with RESULT_OK.
 * No image is captured, stored, or transmitted — privacy-safe dummy biometric gate.
 * On camera permission denied, closes immediately with RESULT_OK (still proceeds to PIN).
 */
class FaceAuthActivity : AppCompatActivity() {

    companion object {
        private const val CAMERA_PERMISSION_REQUEST = 101
        private const val SCAN_DURATION_MS = 2000L
    }

    private val closeHandler = Handler(Looper.getMainLooper())
    private val closeRunnable = Runnable {
        setResult(RESULT_OK)
        finish()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)
        setContentView(R.layout.activity_face_auth)

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            == PackageManager.PERMISSION_GRANTED
        ) {
            startCamera()
        } else {
            ActivityCompat.requestPermissions(
                this,
                arrayOf(Manifest.permission.CAMERA),
                CAMERA_PERMISSION_REQUEST,
            )
        }
    }

    private fun startCamera() {
        val previewView = findViewById<PreviewView>(R.id.facePreviewView)
        val statusText = findViewById<TextView>(R.id.faceStatusText)
        statusText.text = "Verifying your identity…"

        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)
        cameraProviderFuture.addListener({
            val cameraProvider = cameraProviderFuture.get()
            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(previewView.surfaceProvider)
            }
            val cameraSelector = CameraSelector.DEFAULT_FRONT_CAMERA
            try {
                cameraProvider.unbindAll()
                cameraProvider.bindToLifecycle(this, cameraSelector, preview)
            } catch (_: Exception) {
                // camera unavailable — proceed to PIN anyway
            }
            closeHandler.postDelayed(closeRunnable, SCAN_DURATION_MS)
        }, ContextCompat.getMainExecutor(this))
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == CAMERA_PERMISSION_REQUEST && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
            startCamera()
        } else {
            // Permission denied — skip face step, proceed to PIN
            setResult(RESULT_OK)
            finish()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        closeHandler.removeCallbacks(closeRunnable)
    }
}
