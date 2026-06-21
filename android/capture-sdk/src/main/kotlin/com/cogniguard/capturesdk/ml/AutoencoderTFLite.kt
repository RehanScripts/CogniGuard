package com.cogniguard.capturesdk.ml

import android.content.Context
import org.tensorflow.lite.Interpreter
import java.io.File
import java.io.FileInputStream
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.MappedByteBuffer
import java.nio.channels.FileChannel

/**
 * On-device LSTM Autoencoder inference (Implementation.md Phase 18) -- mirrors
 * `gateway/app/scoring/autoencoder.py::reconstruction_error`'s masked-MSE formula
 * exactly, over the same `(SEQ_LEN, N_FEATURES)=(16,9)` window
 * (`training/train_lstm_autoencoder.py::export_tflite`'s fixed-batch-size-1 model).
 * Sends only the **raw** reconstruction error to the gateway -- calibration always
 * happens server-side (CLAUDE.md: inference reads Redis only), same as the web path's
 * server-side AE.
 */
class AutoencoderTFLite(modelBuffer: ByteBuffer) {
    private val interpreter = Interpreter(modelBuffer)

    /** `sequence`: `(SEQ_LEN, N_FEATURES)` row-major window, oldest row first (same
     * left-padded convention as `feature_reader.py`'s rolling buffer). `mask[i] ==
     * false` marks a left-padded cold-start row -- excluded from the error the same
     * way `reconstruction_error()`'s `mask` parameter excludes it server-side. */
    fun reconstructionError(sequence: Array<DoubleArray>, mask: BooleanArray? = null): Double {
        require(sequence.size == SEQ_LEN) { "expected $SEQ_LEN rows, got ${sequence.size}" }
        val input = Array(1) { Array(SEQ_LEN) { i -> FloatArray(N_FEATURES) { j -> sequence[i][j].toFloat() } } }
        val output = Array(1) { Array(SEQ_LEN) { FloatArray(N_FEATURES) } }
        interpreter.run(input, output)

        val weights = mask ?: BooleanArray(SEQ_LEN) { true }
        var totalWeight = 0.0
        var weightedSum = 0.0
        for (i in 0 until SEQ_LEN) {
            if (!weights[i]) continue
            var rowMse = 0.0
            for (j in 0 until N_FEATURES) {
                val diff = output[0][i][j] - input[0][i][j]
                rowMse += diff * diff
            }
            rowMse /= N_FEATURES
            weightedSum += rowMse
            totalWeight += 1.0
        }
        return if (totalWeight <= 0.0) 0.0 else weightedSum / totalWeight
    }

    fun close() {
        interpreter.close()
    }

    companion object {
        const val SEQ_LEN = 16
        const val N_FEATURES = 9

        /** Loads the model bundled in `assets/model.tflite` -- a copy of Phase 16's
         * trained `lstm_autoencoder_tflite` artifact (see `android/README.md` for how
         * to place it; gitignored, same "tracked in the model registry, not git"
         * policy as `models/`). */
        fun fromAsset(context: Context, assetPath: String = "model.tflite"): AutoencoderTFLite {
            val afd = context.assets.openFd(assetPath)
            val channel = (afd.createInputStream() as FileInputStream).channel
            val buffer: MappedByteBuffer =
                channel.map(FileChannel.MapMode.READ_ONLY, afd.startOffset, afd.declaredLength)
            return AutoencoderTFLite(buffer)
        }

        /** Loads a model from an arbitrary file path -- used by `AutoencoderTFLiteTest`
         * to load a freshly-downloaded `GET /api/v1/mobile/ae-model` artifact without
         * needing it bundled at APK build time. */
        fun fromFile(path: String): AutoencoderTFLite {
            val raf = RandomAccessFile(File(path), "r")
            val buffer: MappedByteBuffer = raf.channel.map(FileChannel.MapMode.READ_ONLY, 0, raf.length())
            return AutoencoderTFLite(buffer)
        }
    }
}
