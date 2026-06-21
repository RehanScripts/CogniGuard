"""Phase 16 acceptance check (Implementation.md lines 779-786): the LSTM Autoencoder
architecture trains on synthetic genuine sequences and separates anomaly-injected
windows by reconstruction error, and both serving exports (ONNX, TFLite) match the
trained Keras model within tolerance. No live infra: this exercises the pure model/
export/calibration logic with synthetic data, the same way `test_drift.py` tests
`drift_monitor`'s pure score-drift math separately from its live-infra-gated
Postgres/S3 integration. `main()`'s real-dataset + Postgres/S3/Redis registration flow
has no dedicated pytest here either, mirroring `train_isolation_forest.py`/
`train_xgboost.py` (verified by hand by actually running the module, per the phase's
acceptance check's first command) -- not a gap introduced by this phase.

Needs `tensorflow`/`tf2onnx` (`training/requirements.txt`, not a gateway dependency)
installed; skipped entirely otherwise rather than failing a fresh, lean gateway image.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("tensorflow")
pytest.importorskip("tf2onnx")

from app.scoring.calibration import calibrate_ae  # noqa: E402
from training.train_lstm_autoencoder import (  # noqa: E402
    NORMALIZATION_VARIANCE_FLOOR,
    N_FEATURES,
    SEQ_LEN,
    build_model,
    export_onnx,
    export_tflite,
    feature_stats,
    fit_calibration,
    reconstruction_errors,
    verify_onnx_parity,
    verify_tflite_parity,
)

SEED = 0
N_SEQUENCES = 200
EPOCHS = 40


def _synthetic_genuine(rng: np.random.Generator, n: int = N_SEQUENCES) -> np.ndarray:
    """Each "subject" is a fixed per-feature sine wave plus small noise -- a learnable
    manifold an autoencoder can actually compress, unlike pure random noise. Features
    are deliberately given different amplitudes/offsets (not just different phases) so
    these tests also exercise per-feature normalization, not just a uniform-scale
    special case."""
    t = np.arange(SEQ_LEN)
    phases = rng.uniform(0, 2 * np.pi, size=N_FEATURES)
    amplitudes = np.array([1.0, 50.0, 0.01, 5.0, 200.0, 1.0, 0.5, 20.0, 2.0])
    offsets = np.array([0.0, 100.0, 0.0, -3.0, 500.0, 0.0, 0.2, 0.0, -1.0])
    return np.stack(
        [
            np.stack(
                [
                    offsets[f]
                    + amplitudes[f]
                    * np.sin(0.3 * t + phases[f] + rng.normal(0, 0.05, size=SEQ_LEN))
                    for f in range(N_FEATURES)
                ],
                axis=1,
            )
            for _ in range(n)
        ]
    ).astype(np.float32)


def _fit(windows: np.ndarray, masks: np.ndarray, *, epochs: int = EPOCHS):
    feature_mean, feature_var = feature_stats(windows, masks)
    training_model, serving_model = build_model(feature_mean=feature_mean, feature_var=feature_var)
    normalized_targets = (windows - feature_mean) / np.sqrt(feature_var)
    training_model.fit(
        windows, normalized_targets, sample_weight=masks, epochs=epochs, batch_size=32, verbose=0
    )
    return training_model, serving_model


@pytest.fixture(scope="module")
def trained_model_and_data():
    import tensorflow as tf

    tf.random.set_seed(SEED)
    rng = np.random.default_rng(SEED)
    genuine = _synthetic_genuine(rng)
    masks = np.ones((len(genuine), SEQ_LEN), dtype=np.float32)
    _training_model, serving_model = _fit(genuine, masks)
    return serving_model, genuine, masks, rng


def test_feature_stats_ignores_padded_rows():
    windows = np.zeros((4, SEQ_LEN, N_FEATURES), dtype=np.float32)
    windows[:, :4, 0] = 999.0  # padded prefix, would wildly skew the mean if counted
    windows[:, 4:, 0] = np.array([1.0, 2.0, 3.0, 4.0] * 3)[: SEQ_LEN - 4]
    masks = np.zeros((4, SEQ_LEN), dtype=np.float32)
    masks[:, 4:] = 1.0

    mean, _variance = feature_stats(windows, masks)
    assert mean[0] < 10.0  # nowhere near the padded 999.0 sentinel


def test_feature_stats_floors_zero_variance_dims():
    windows = np.zeros((10, SEQ_LEN, N_FEATURES), dtype=np.float32)
    windows[:, :, 0] = np.arange(10 * SEQ_LEN).reshape(10, SEQ_LEN)  # dim 0 has real variance
    masks = np.ones((10, SEQ_LEN), dtype=np.float32)

    _mean, variance = feature_stats(windows, masks)
    assert variance[0] > NORMALIZATION_VARIANCE_FLOOR
    assert variance[1] == pytest.approx(NORMALIZATION_VARIANCE_FLOOR)


def test_build_model_has_expected_io_shape():
    mean = np.zeros(N_FEATURES, dtype=np.float32)
    var = np.ones(N_FEATURES, dtype=np.float32)
    training_model, serving_model = build_model(feature_mean=mean, feature_var=var)
    assert training_model.input_shape == (None, SEQ_LEN, N_FEATURES)
    assert training_model.output_shape == (None, SEQ_LEN, N_FEATURES)
    assert serving_model.input_shape == (None, SEQ_LEN, N_FEATURES)
    assert serving_model.output_shape == (None, SEQ_LEN, N_FEATURES)


def test_training_reduces_loss_on_synthetic_genuine_sequences():
    """80 epochs (not the fixture's 40) and a generous threshold -- convergence speed
    on 64 samples varies run-to-run with the random weight init, confirmed across 5
    seeds to reliably clear ratio<0.1 by 80 epochs (vs. a 0.156-0.249 spread at 40)."""
    import tensorflow as tf

    tf.random.set_seed(SEED)
    rng = np.random.default_rng(SEED)
    genuine = _synthetic_genuine(rng, n=64)
    masks = np.ones((len(genuine), SEQ_LEN), dtype=np.float32)
    feature_mean, feature_var = feature_stats(genuine, masks)
    training_model, _serving_model = build_model(feature_mean=feature_mean, feature_var=feature_var)
    normalized_targets = (genuine - feature_mean) / np.sqrt(feature_var)
    history = training_model.fit(
        genuine, normalized_targets, sample_weight=masks, epochs=80, batch_size=32, verbose=0
    )
    assert history.history["loss"][-1] < history.history["loss"][0] * 0.1


def test_anomaly_injected_windows_score_higher_recon_error(trained_model_and_data):
    model, genuine, masks, rng = trained_model_and_data
    anomalous = genuine + rng.normal(0, 1.5, size=genuine.shape).astype(np.float32) * genuine.std(
        axis=(0, 1), keepdims=True
    )

    genuine_errors = reconstruction_errors(model, genuine, masks)
    anomalous_errors = reconstruction_errors(model, anomalous, masks)

    assert anomalous_errors.mean() > genuine_errors.mean() * 10


def test_anomaly_injected_windows_calibrate_above_genuine(trained_model_and_data):
    """End-to-end through the real calibration layer (Phase 13): fit params on a
    held-out genuine split, then check the calibrated Behavior_Score actually
    separates genuine from anomalous in [0,1] space, not just in raw recon-error
    units."""
    model, genuine, masks, rng = trained_model_and_data
    held_out = genuine[:50]
    held_out_masks = masks[:50]
    genuine_errors = reconstruction_errors(model, held_out, held_out_masks)
    params = fit_calibration(genuine_errors)

    noise_scale = genuine.std(axis=(0, 1), keepdims=True)
    anomalous = (
        genuine[50:80]
        + rng.normal(0, 1.5, size=genuine[50:80].shape).astype(np.float32) * noise_scale
    )
    anomalous_errors = reconstruction_errors(model, anomalous, masks[50:80])

    genuine_scores = [calibrate_ae(e, params) for e in genuine_errors]
    anomalous_scores = [calibrate_ae(e, params) for e in anomalous_errors]

    assert np.median(genuine_scores) < 0.5
    assert np.median(anomalous_scores) > 0.5


def test_onnx_export_matches_keras_within_tolerance(trained_model_and_data):
    model, genuine, _masks, _rng = trained_model_and_data
    onnx_bytes = export_onnx(model)
    max_diff = verify_onnx_parity(model, onnx_bytes, genuine[:8], tolerance=1e-2)
    assert max_diff < 1e-2


def test_tflite_export_matches_keras_within_tolerance(trained_model_and_data):
    model, genuine, _masks, _rng = trained_model_and_data
    tflite_bytes = export_tflite(model)
    max_diff = verify_tflite_parity(model, tflite_bytes, genuine[:8], tolerance=1e-2)
    assert max_diff < 1e-2


def test_tflite_export_matches_onnx_within_tolerance(trained_model_and_data):
    import onnxruntime as ort
    import tensorflow as tf

    model, genuine, _masks, _rng = trained_model_and_data
    onnx_bytes = export_onnx(model)
    tflite_bytes = export_tflite(model)

    sample = genuine[:1]
    sess = ort.InferenceSession(onnx_bytes, providers=["CPUExecutionProvider"])
    onnx_out = sess.run(None, {sess.get_inputs()[0].name: sample})[0]

    interpreter = tf.lite.Interpreter(model_content=tflite_bytes)
    interpreter.allocate_tensors()
    inp = interpreter.get_input_details()[0]
    out = interpreter.get_output_details()[0]
    interpreter.set_tensor(inp["index"], sample)
    interpreter.invoke()
    tflite_out = interpreter.get_tensor(out["index"])

    assert np.max(np.abs(onnx_out - tflite_out)) < 1e-2
