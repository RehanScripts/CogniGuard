"""Transformer Encoder autoencoder — benchmark and research model (UPGRADE_PLAN Phase A1).

DEPLOYMENT STATUS: research / benchmark only. Registered at stage `staging`.
It is evaluated head-to-head against the LSTM Autoencoder in benchmark.py to provide
comprehensive comparison evidence. It does NOT replace the production stack unless a
human reviewer explicitly approves promotion after verifying simultaneous improvement
in EER, FAR/FRR, latency, memory footprint, and TFLite deployment suitability.

Production behavioral stack (locked):
  Primary  — LSTM Autoencoder  (lstm_autoencoder  @ production)
  Fallback — Isolation Forest  (isolation_forest  @ production)
  Decision — XGBoost           (xgboost_txn       @ production)

Architecture:
    Input(16, 9) → Masking → Normalization → Dense(D_MODEL) + SinusoidalPositionalEncoding
    → [MultiHeadAttention(NUM_HEADS, key_dim=D_MODEL//NUM_HEADS) + FFN(FF_DIM)] × 2
      (residual, LayerNorm) → Dense(n_features) → Denormalization → reconstruct (16, 9).

Same (16, 9) window / mask / calibration / ONNX contract as train_lstm_autoencoder.py
so the two models are directly comparable in the benchmark harness.

Runnable standalone:  python -m training.train_transformer
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
from app.scoring import calibration
from app.scoring.autoencoder import MIN_SEQ, N_FEATURES, SEQ_LEN
from training import registry, s3_io
from training.datasets import cmu, hmog
from training.train_lstm_autoencoder import (
    STRIDE,
    VAL_FRACTION,
    export_onnx,
    feature_stats,
    fit_calibration,
    reconstruction_errors,
    verify_onnx_parity,
)

logger = logging.getLogger("cogniguard.train_transformer")

D_MODEL = 32
NUM_HEADS = 4
FF_DIM = 64


class _SinusoidalPositionalEncoding(keras.layers.Layer):
    """Fixed sinusoidal positional encoding — ONNX-safe (constant tensor, no variables).

    Uses the standard Vaswani et al. scheme: PE(pos, 2i) = sin(pos/10000^(2i/d_model)),
    PE(pos, 2i+1) = cos(pos/10000^(2i/d_model)).
    """

    def __init__(self, seq_len: int, d_model: int, **kwargs):
        super().__init__(trainable=False, **kwargs)
        self._seq_len = seq_len
        self._d_model = d_model
        pos = np.arange(seq_len)[:, None]
        i = np.arange(d_model)[None, :]
        angle_rates = 1.0 / np.power(10000.0, (2 * (i // 2)) / d_model)
        angles = pos * angle_rates
        pe = np.where(i % 2 == 0, np.sin(angles), np.cos(angles))
        self._pe = tf.constant(pe[None], dtype=tf.float32)  # (1, seq_len, d_model)

    def call(self, x: tf.Tensor) -> tf.Tensor:
        return x + self._pe

    def get_config(self) -> dict:
        cfg = super().get_config()
        cfg.update({"seq_len": self._seq_len, "d_model": self._d_model})
        return cfg


def _transformer_block(
    x: tf.Tensor,
    *,
    num_heads: int,
    key_dim: int,
    ff_dim: int,
    d_model: int,
    name_prefix: str,
) -> tf.Tensor:
    attn = keras.layers.MultiHeadAttention(
        num_heads=num_heads,
        key_dim=key_dim,
        name=f"{name_prefix}_mha",
    )(x, x)
    x = keras.layers.LayerNormalization(epsilon=1e-6, name=f"{name_prefix}_ln1")(x + attn)
    ff = keras.layers.Dense(ff_dim, activation="relu", name=f"{name_prefix}_ff1")(x)
    ff = keras.layers.Dense(d_model, name=f"{name_prefix}_ff2")(ff)
    return keras.layers.LayerNormalization(epsilon=1e-6, name=f"{name_prefix}_ln2")(x + ff)


def build_model(
    *,
    seq_len: int = SEQ_LEN,
    n_features: int = N_FEATURES,
    feature_mean: np.ndarray,
    feature_var: np.ndarray,
    d_model: int = D_MODEL,
    num_heads: int = NUM_HEADS,
    ff_dim: int = FF_DIM,
) -> tuple[keras.Model, keras.Model]:
    """Returns (training_model, serving_model) with shared weights.

    training_model outputs in normalized space (loss target must also be normalized).
    serving_model adds the inverse normalization back so external contract is
    raw-in / raw-out — identical to build_model() in train_lstm_autoencoder.py.
    """
    norm = keras.layers.Normalization(
        axis=-1, mean=feature_mean, variance=feature_var, name="norm"
    )
    denorm = keras.layers.Normalization(
        axis=-1, mean=feature_mean, variance=feature_var, invert=True, name="denorm"
    )

    inputs = keras.Input(shape=(seq_len, n_features), name="input")
    x = keras.layers.Masking(mask_value=0.0, name="mask")(inputs)
    x = norm(x)
    x = keras.layers.Dense(d_model, name="proj_in")(x)
    x = _SinusoidalPositionalEncoding(seq_len, d_model, name="pos_enc")(x)
    x = _transformer_block(
        x, num_heads=num_heads, key_dim=d_model // num_heads,
        ff_dim=ff_dim, d_model=d_model, name_prefix="blk1",
    )
    x = _transformer_block(
        x, num_heads=num_heads, key_dim=d_model // num_heads,
        ff_dim=ff_dim, d_model=d_model, name_prefix="blk2",
    )
    normalized_recon = keras.layers.Dense(n_features, name="proj_out")(x)

    training_model = keras.Model(
        inputs, normalized_recon, name="transformer_encoder_training"
    )
    training_model.compile(optimizer="adam", loss="mse")

    raw_recon = denorm(normalized_recon)
    serving_model = keras.Model(inputs, raw_recon, name="transformer_encoder")
    return training_model, serving_model


def main(
    *,
    stage: str = "staging",
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
    training_model, serving_model = build_model(feature_mean=feature_mean, feature_var=feature_var)
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
    sample = val_windows[: min(8, len(val_windows))]
    onnx_diff = verify_onnx_parity(serving_model, onnx_bytes, sample, tolerance=tolerance)

    version = f"transformer_encoder@{dt.date.today().isoformat()}"
    onnx_uri = s3_io.write_bytes(
        onnx_bytes,
        f"models/transformer_encoder/{version}/model.onnx",
        local_path=os.path.join(
            settings.model_dir, "transformer_encoder", version, "model.onnx"
        ),
    )
    calib_payload = {
        "scale": calib_params.scale,
        "threshold": calib_params.threshold,
        "temperature": calib_params.temperature,
    }
    s3_io.write_bytes(
        json.dumps(calib_payload).encode(),
        f"models/transformer_encoder/{version}/calibration.json",
    )

    metrics = {
        "n_train": int(len(train_windows)),
        "n_val": int(len(val_windows)),
        "recon_error_median": float(np.median(val_errors)),
        "recon_error_p95": float(np.percentile(val_errors, 95)),
        "onnx_max_abs_diff": onnx_diff,
        "calibration": calib_payload,
    }
    registry.register_model(
        model_name="transformer_encoder",
        model_type="keras.TransformerEncoder(onnx)",
        version=version,
        artifact_uri=onnx_uri,
        metrics=metrics,
        stage=stage,
    )
    logger.info(
        "transformer_encoder trained: n_train=%d n_val=%d recon_p95=%.4f onnx_diff=%.2e",
        metrics["n_train"],
        metrics["n_val"],
        metrics["recon_error_p95"],
        onnx_diff,
    )
    return {"version": version, "onnx_artifact_uri": onnx_uri, **metrics}


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=["staging", "production"],
        default="staging",
        help="model registry stage (default: staging — Phase A does not promote to production)",
    )
    parser.add_argument("--epochs", type=int, default=20)
    args = parser.parse_args()
    result = main(stage=args.stage, epochs=args.epochs)
    for key, value in result.items():
        print(f"{key}: {value}")
