"""LSTM Autoencoder -> reconstruction error -> Behavior_Score (Implementation.md Phase
13). Mirrors `isolation_forest.py`'s shape: a pure function over an injected model
object (here an `onnxruntime.InferenceSession` rather than a loaded sklearn estimator),
so both are equally unit-testable with stubs and equally swappable via
`registry.get(...)`. Nothing calls `behavior_score()` from `stack.py` yet -- that wiring
is Phase 15's job; this module is inert until then.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from . import calibration
from .calibration import CalibrationParams

# (16, 9): 16 = rolling window length (Phase 14's behavior:{session_id}:seq ring
# buffer), 9 = training.train_isolation_forest.BEHAVIOR_COLUMNS order -- the same 9-dim
# vector isolation_forest.py and schemas/features.py already use, so the AE's window is
# dimension-for-dimension consistent with what's already captured per event.
SEQ_LEN = 16
N_FEATURES = 9

# Fewer real (unmasked) rows than this in a session's rolling window means there isn't
# enough signal yet to trust the AE -- feature_reader.py's ae_cold_start gate (Phase 14).
MIN_SEQ = 4


def reconstruction_error(
    sequence: Sequence[Sequence[float]], *, model: Any, mask: Sequence[bool] | None = None
) -> float:
    """Masked MSE between `sequence` (SEQ_LEN, N_FEATURES) and the autoencoder's
    reconstruction of it. `model` is an injected `onnxruntime.InferenceSession`. `mask`
    marks real rows (True) vs. padded/missing rows (False) -- padded rows never
    contribute to the error, so a short window isn't penalized for its own padding."""
    target = np.asarray(sequence, dtype=np.float32).reshape(SEQ_LEN, N_FEATURES)
    input_name = model.get_inputs()[0].name
    recon = model.run(None, {input_name: target.reshape(1, SEQ_LEN, N_FEATURES)})[0]
    recon = np.asarray(recon, dtype=np.float32).reshape(SEQ_LEN, N_FEATURES)

    weights = (
        np.ones(SEQ_LEN, dtype=np.float32) if mask is None else np.asarray(mask, dtype=np.float32)
    )
    total_weight = float(weights.sum())
    if total_weight <= 0:
        return 0.0  # no real rows to compare -- no signal, not an anomaly verdict

    per_row_mse = ((recon - target) ** 2).mean(axis=1)  # (SEQ_LEN,)
    return float((per_row_mse * weights).sum() / total_weight)


def behavior_score(
    sequence: Sequence[Sequence[float]],
    *,
    model: Any,
    calib_params: CalibrationParams,
    mask: Sequence[bool] | None = None,
) -> float:
    """[0,1] anomaly score, same polarity as `isolation_forest.behavior_score`
    (0=normal, 1=anomalous) -- the calibration layer is what makes the two
    interchangeable for Phase 15's AE-primary/IF-shadow routing."""
    err = reconstruction_error(sequence, model=model, mask=mask)
    return calibration.calibrate_ae(err, calib_params)
