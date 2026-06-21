"""Shared (seq_len, n_features) windowing for `sequence_frames()` (cmu.py, hmog.py) --
Phase 16's LSTM Autoencoder training needs ordered per-subject windows, not just the
pooled per-row vectors Phase 5's Isolation Forest prior uses.
"""

from __future__ import annotations

import numpy as np


def windows_for_series(
    matrix: np.ndarray, *, seq_len: int, stride: int, min_seq: int
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """`matrix`: (T, n_features) ordered rows for one subject. Returns full-length
    sliding windows (mask all True) plus a handful of left-padded cold-start windows
    from the series' start (length `min_seq`..`seq_len`-1, mask marks the padded
    prefix False) -- mirrors `feature_reader.py`'s left-pad convention so the
    autoencoder sees genuinely masked input during training, the same shape a short
    live session arrives in (Implementation.md Phase 14's `MIN_SEQ` gate)."""
    t, n_features = matrix.shape
    windows: list[np.ndarray] = []
    masks: list[np.ndarray] = []

    for start in range(0, max(t - seq_len + 1, 0), stride):
        windows.append(matrix[start : start + seq_len])
        masks.append(np.ones(seq_len, dtype=bool))

    for k in range(min_seq, seq_len):
        if k > t:
            break
        window = np.zeros((seq_len, n_features), dtype=matrix.dtype)
        window[seq_len - k :] = matrix[:k]
        mask = np.zeros(seq_len, dtype=bool)
        mask[seq_len - k :] = True
        windows.append(window)
        masks.append(mask)

    return windows, masks
