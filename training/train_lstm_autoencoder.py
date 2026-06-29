"""LSTM Autoencoder training pipeline (Implementation.md Phase 16): trains the
masked-MSE sequence autoencoder on pooled genuine CMU+HMOG `(16,9)` windows (the same
9-dim `BehaviorFeatures` shape Phase 5/13's Isolation Forest prior already pools),
exports both serving artifacts (ONNX for the gateway, TFLite for Android), fits the
common calibration layer's `CalibrationParams` from the trained model's own
reconstruction-error distribution on held-out genuine windows, and seeds
`calib:ae:population` in Redis so Phase 15's AE-primary routing has a real (not
default-fallback) calibration from the moment this finishes.

Runnable standalone:  python -m training.train_lstm_autoencoder

Requires `tensorflow`/`tf2onnx` (see `training/requirements.txt`) -- deliberately NOT a
gateway dependency (CLAUDE.md: no TensorFlow in the served gateway image; the gateway's
own AE inference, `app/scoring/autoencoder.py`, only ever uses the exported ONNX
artifact via `onnxruntime`). Install once inside the running container before use:
`docker compose exec gateway pip install -r training/requirements.txt`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os

import numpy as np
import tensorflow as tf
import tf2onnx
from tensorflow import keras

from app.config import settings
from app.redis_client import redis_client
from app.scoring import calibration
from app.scoring.autoencoder import MIN_SEQ, N_FEATURES, SEQ_LEN
from training import registry, s3_io
from training.datasets import cmu, hmog

logger = logging.getLogger("cogniguard.train_lstm_autoencoder")

STRIDE = 4
VAL_FRACTION = 0.2
CALIBRATION_PERCENTILE = 95.0  # anchor threshold high in the genuine distribution so
# most genuine windows calibrate well below the 0.5 midpoint -- only the tail (and
# real anomalies) cross it. Mirrors calibration.py's "anchored so raw==threshold->0.5"
# framing: genuine windows should mostly land below that anchor, not at it.


# BehaviorFeatures dims span wildly different native scales (e.g. swipe_velocity_norm
# is O(1000), hold_time_avg is O(0.1)) -- an unnormalized masked-MSE loss is dominated
# entirely by whichever dim has the largest raw variance, drowning out the other 8
# dims' gradient signal and producing a useless reconstruction-error distribution for
# calibration (a few large-scale outlier rows alone can swing the 95th percentile by
# 6+ orders of magnitude). Dims with ~zero training variance (touch_pressure_avg,
# mouse_velocity_mean are never populated by CMU/HMOG -- the same Phase 5 dataset gap
# `isolation_forest.py`'s per-user baseline already documents) get a variance floor
# rather than dividing by zero.
NORMALIZATION_VARIANCE_FLOOR = 1e-6


def feature_stats(windows: np.ndarray, masks: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-feature (mean, floored variance) over real (unmasked) rows only -- padded
    zero-fill rows would otherwise bias the estimate toward zero."""
    real_rows = windows[masks.astype(bool)]
    mean = real_rows.mean(axis=0)
    variance = np.maximum(real_rows.var(axis=0), NORMALIZATION_VARIANCE_FLOOR)
    return mean.astype(np.float32), variance.astype(np.float32)


def build_model(
    *,
    seq_len: int = SEQ_LEN,
    n_features: int = N_FEATURES,
    feature_mean: np.ndarray,
    feature_var: np.ndarray,
) -> tuple[keras.Model, keras.Model, keras.Model]:
    """`Input(16,9) -> Masking -> LSTM(32)->LSTM(16) -> RepeatVector ->
    LSTM(16,seq)->LSTM(32,seq) -> TimeDistributed(Dense(9))` (Implementation.md Phase
    16's architecture line), with a per-feature `Normalization` immediately after
    `Masking` (see module docstring above) so the loss is well-conditioned, and a
    paired inverse `Normalization` on the output so the model's external contract
    stays raw-in/raw-out -- unchanged from `app.scoring.autoencoder.
    reconstruction_error()`'s existing masked-MSE-in-raw-space formula. `Masking`
    makes the encoder skip left-padded cold-start rows entirely; the decoder
    reconstructs every position regardless, with the loss masked separately via
    `sample_weight` in `fit()` (Keras's `RepeatVector` doesn't propagate a mask).

    Returns `(training_model, serving_model, encoder_model)`: all three wrap the *same*
    LSTM/Dense layer instances (weights are shared, not copied), so fitting
    `training_model` updates the others too. `encoder_model` outputs the 16-dim
    bottleneck embedding (Phase F4 embedding store); `serving_model` is the full
    autoencoder for reconstruction-error scoring and ONNX/TFLite export.
    """
    norm = keras.layers.Normalization(axis=-1, mean=feature_mean, variance=feature_var)
    denorm = keras.layers.Normalization(
        axis=-1, mean=feature_mean, variance=feature_var, invert=True
    )

    inputs = keras.Input(shape=(seq_len, n_features), name="input")
    x = keras.layers.Masking(mask_value=0.0)(inputs)
    x = norm(x)
    x = keras.layers.LSTM(32, return_sequences=True)(x)
    bottleneck = keras.layers.LSTM(16, return_sequences=False)(x)  # 16-dim embedding (F4)

    x = keras.layers.RepeatVector(seq_len)(bottleneck)
    x = keras.layers.LSTM(16, return_sequences=True)(x)
    x = keras.layers.LSTM(32, return_sequences=True)(x)
    normalized_recon = keras.layers.TimeDistributed(keras.layers.Dense(n_features))(x)

    encoder_model = keras.Model(inputs, bottleneck, name="lstm_encoder")
    training_model = keras.Model(inputs, normalized_recon, name="lstm_autoencoder_training")
    training_model.compile(optimizer="adam", loss="mse")

    raw_recon = denorm(normalized_recon)
    serving_model = keras.Model(inputs, raw_recon, name="lstm_autoencoder")
    return training_model, serving_model, encoder_model


def reconstruction_errors(model: keras.Model, windows: np.ndarray, masks: np.ndarray) -> np.ndarray:
    """Masked MSE per window, batched -- mirrors `app.scoring.autoencoder.
    reconstruction_error()`'s per-window formula exactly (mask excludes padded rows
    from the error), so a calibration fit against this distribution is valid against
    what the gateway computes at inference time."""
    recon = model.predict(windows, verbose=0)
    per_row_mse = ((recon - windows) ** 2).mean(axis=2)  # (N, seq_len)
    weights = masks.astype(np.float32)
    total = weights.sum(axis=1)
    total = np.where(total > 0, total, 1.0)  # construction guarantees >=min_seq real rows
    return (per_row_mse * weights).sum(axis=1) / total


def fit_calibration(genuine_errors: np.ndarray) -> calibration.CalibrationParams:
    """Robust-z anchor fit from a held-out genuine reconstruction-error distribution:
    `threshold` = a high percentile of genuine error (so most genuine windows
    calibrate below the neutral 0.5 midpoint, only the tail and real anomalies cross
    it), `scale` = the median absolute deviation about the median (robust to the
    distribution's own long anomalous tail, unlike std)."""
    median = float(np.median(genuine_errors))
    mad = float(np.median(np.abs(genuine_errors - median))) * 1.4826
    threshold = float(np.percentile(genuine_errors, CALIBRATION_PERCENTILE))
    scale = max(mad, calibration.EPS)
    return calibration.CalibrationParams(scale=scale, threshold=threshold, temperature=1.0)


def export_onnx(
    model: keras.Model, *, seq_len: int = SEQ_LEN, n_features: int = N_FEATURES
) -> bytes:
    spec = (tf.TensorSpec((None, seq_len, n_features), tf.float32, name="input"),)
    onnx_model, _ = tf2onnx.convert.from_keras(model, input_signature=spec, opset=13)
    return onnx_model.SerializeToString()


def export_tflite(
    model: keras.Model, *, seq_len: int = SEQ_LEN, n_features: int = N_FEATURES
) -> bytes:
    """TFLite's converter can't lower this architecture's LSTM ops under a dynamic
    batch dimension (`TensorListReserve` needs a static `element_shape`) -- wraps the
    trained model in a fixed `batch_size=1` model (same weights, no retraining) before
    conversion, which also matches the real on-device shape: Android scores one
    window at a time (`android/capture-sdk/ml/AutoencoderTFLite.kt`, Phase 18)."""
    fixed_inputs = keras.Input(batch_size=1, shape=(seq_len, n_features), name="input")
    fixed_model = keras.Model(fixed_inputs, model(fixed_inputs))
    converter = tf.lite.TFLiteConverter.from_keras_model(fixed_model)
    return converter.convert()


def verify_onnx_parity(
    model: keras.Model, onnx_bytes: bytes, sample: np.ndarray, *, tolerance: float
) -> float:
    import onnxruntime as ort

    sess = ort.InferenceSession(onnx_bytes, providers=["CPUExecutionProvider"])
    onnx_out = sess.run(None, {sess.get_inputs()[0].name: sample})[0]
    keras_out = model.predict(sample, verbose=0)
    max_diff = float(np.max(np.abs(keras_out - onnx_out)))
    if max_diff > tolerance:
        raise ValueError(f"ONNX export diverges from Keras: max_abs_diff={max_diff} > {tolerance}")
    return max_diff


def verify_tflite_parity(
    model: keras.Model, tflite_bytes: bytes, sample: np.ndarray, *, tolerance: float
) -> float:
    interpreter = tf.lite.Interpreter(model_content=tflite_bytes)
    interpreter.allocate_tensors()
    inp = interpreter.get_input_details()[0]
    out = interpreter.get_output_details()[0]
    interpreter.set_tensor(inp["index"], sample[:1])
    interpreter.invoke()
    tflite_out = interpreter.get_tensor(out["index"])
    keras_out = model.predict(sample[:1], verbose=0)
    max_diff = float(np.max(np.abs(keras_out - tflite_out)))
    if max_diff > tolerance:
        raise ValueError(
            f"TFLite export diverges from Keras: max_abs_diff={max_diff} > {tolerance}"
        )
    return max_diff


def main(
    *,
    stage: str = "production",
    epochs: int = 20,
    batch_size: int = 64,
    seed: int = 42,
    tolerance: float = 1e-3,
) -> dict:
    cmu_behavior = s3_io.read_parquet("training/cmu/behavior.parquet")
    hmog_cleaned = s3_io.read_parquet("training/hmog/behavior.parquet")
    hmog_behavior = hmog.behavior_frame(hmog_cleaned).dropna(
        subset=["swipe_velocity_norm", "swipe_angle_dev", "acceleration_variance"]
    )

    cmu_windows, cmu_masks = cmu.sequence_frames(
        cmu_behavior, seq_len=SEQ_LEN, stride=STRIDE, min_seq=MIN_SEQ
    )
    hmog_windows, hmog_masks = hmog.sequence_frames(
        hmog_behavior, seq_len=SEQ_LEN, stride=STRIDE, min_seq=MIN_SEQ
    )
    windows = np.concatenate([cmu_windows, hmog_windows], axis=0)
    masks = np.concatenate([cmu_masks, hmog_masks], axis=0)

    rng = np.random.default_rng(seed)
    order = rng.permutation(len(windows))
    windows, masks = windows[order], masks[order]
    n_val = max(1, int(len(windows) * VAL_FRACTION))
    train_windows, val_windows = windows[n_val:], windows[:n_val]
    train_masks, val_masks = masks[n_val:], masks[:n_val]

    feature_mean, feature_var = feature_stats(train_windows, train_masks)
    normalized_targets = (train_windows - feature_mean) / np.sqrt(feature_var)

    tf.random.set_seed(seed)
    training_model, serving_model, encoder_model = build_model(feature_mean=feature_mean, feature_var=feature_var)
    training_model.fit(
        train_windows,
        normalized_targets,
        sample_weight=train_masks.astype(np.float32),
        epochs=epochs,
        batch_size=batch_size,
        verbose=0,
    )

    val_errors = reconstruction_errors(serving_model, val_windows, val_masks)
    calib_params = fit_calibration(val_errors)

    onnx_bytes = export_onnx(serving_model)
    tflite_bytes = export_tflite(serving_model)
    encoder_onnx_bytes = export_onnx(encoder_model)
    sample = val_windows[: min(8, len(val_windows))]
    onnx_diff = verify_onnx_parity(serving_model, onnx_bytes, sample, tolerance=tolerance)
    tflite_diff = verify_tflite_parity(serving_model, tflite_bytes, sample, tolerance=tolerance)

    version = f"lstm_autoencoder@{dt.date.today().isoformat()}"
    onnx_uri = s3_io.write_bytes(
        onnx_bytes,
        f"models/lstm_autoencoder/{version}/model.onnx",
        local_path=os.path.join(settings.model_dir, "lstm_autoencoder", version, "model.onnx"),
    )
    tflite_uri = s3_io.write_bytes(
        tflite_bytes,
        f"models/lstm_autoencoder_tflite/{version}/model.tflite",
        local_path=os.path.join(
            settings.model_dir, "lstm_autoencoder_tflite", version, "model.tflite"
        ),
    )
    encoder_uri = s3_io.write_bytes(
        encoder_onnx_bytes,
        f"models/lstm_encoder/{version}/encoder.onnx",
        local_path=os.path.join(settings.model_dir, "lstm_encoder", version, "encoder.onnx"),
    )
    calib_payload = {
        "scale": calib_params.scale,
        "threshold": calib_params.threshold,
        "temperature": calib_params.temperature,
    }
    s3_io.write_bytes(
        json.dumps(calib_payload).encode(), f"models/lstm_autoencoder/{version}/calibration.json"
    )

    metrics = {
        "n_train": int(len(train_windows)),
        "n_val": int(len(val_windows)),
        "recon_error_median": float(np.median(val_errors)),
        "recon_error_p95": float(np.percentile(val_errors, 95)),
        "onnx_max_abs_diff": onnx_diff,
        "tflite_max_abs_diff": tflite_diff,
        "calibration": calib_payload,
    }
    registry.register_model(
        model_name="lstm_autoencoder",
        model_type="keras.LSTMAutoencoder(onnx)",
        version=version,
        artifact_uri=onnx_uri,
        metrics=metrics,
        stage=stage,
    )
    registry.register_model(
        model_name="lstm_autoencoder_tflite",
        model_type="keras.LSTMAutoencoder(tflite)",
        version=version,
        artifact_uri=tflite_uri,
        metrics=metrics,
        stage=stage,
    )
    registry.register_model(
        model_name="lstm_encoder",
        model_type="keras.LSTMEncoder(onnx)",
        version=version,
        artifact_uri=encoder_uri,
        metrics={"embedding_dim": 16, **metrics},
        stage=stage,
    )

    redis_client.set(calibration.POPULATION_CALIBRATION_KEY, json.dumps(calib_payload))

    return {
        "version": version,
        "onnx_artifact_uri": onnx_uri,
        "tflite_artifact_uri": tflite_uri,
        "encoder_artifact_uri": encoder_uri,
        **metrics,
    }


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=["staging", "production"],
        default="production",
        help="register the trained model as a challenger (staging) or champion (production)",
    )
    parser.add_argument("--epochs", type=int, default=20)
    args = parser.parse_args()
    result = main(stage=args.stage, epochs=args.epochs)
    for key, value in result.items():
        print(f"{key}: {value}")
