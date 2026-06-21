"""CMU `DSL-StrongPasswordData.csv` adapter (Implementation.md Phase 5).

51 subjects x 400 repetitions typing the fixed password ".tie5Roanl" + Return (11
keystrokes). Columns are `H.<key>` (hold/dwell time), `DD.<a>.<b>` (down-down digraph
latency), `UD.<a>.<b>` (up-down / flight latency) — all in seconds. Reduces each row to
the 4 typing-relevant dimensions of the shared `BehaviorFeatures` vector (Architecture
§5.2) so it can be pooled with HMOG's touch/motion dimensions for the global IF prior.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from training.datasets._windowing import windows_for_series

ID_COLUMNS = ["subject", "sessionIndex", "rep"]

# Full BehaviorFeatures shape (Architecture Sec5.2) -- same 9 names/order as
# `training.train_isolation_forest.BEHAVIOR_COLUMNS`; duplicated here rather than
# imported since it's a frozen cross-channel contract, not a value that varies with
# this adapter (train_isolation_forest.py defines its own copy for the same reason).
BEHAVIOR_COLUMNS = [
    "typing_speed",
    "key_latency_avg",
    "typing_rhythm_std",
    "hold_time_avg",
    "swipe_velocity_norm",
    "swipe_angle_dev",
    "touch_pressure_avg",
    "acceleration_variance",
    "mouse_velocity_mean",
]
_PRESENT = ["typing_speed", "key_latency_avg", "typing_rhythm_std", "hold_time_avg"]


def load(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def behavior_frame(df: pd.DataFrame) -> pd.DataFrame:
    """subject/session id columns + typing_speed, key_latency_avg, typing_rhythm_std,
    hold_time_avg — the typing-relevant slice of BehaviorFeatures. Touch/motion/mouse
    dims are out of scope for a keyboard-only dataset; callers default those to 0.0."""
    h_cols = [c for c in df.columns if c.startswith("H.")]
    dd_cols = [c for c in df.columns if c.startswith("DD.")]
    ud_cols = [c for c in df.columns if c.startswith("UD.")]
    n_keys = len(h_cols)

    total_time_s = df[dd_cols].sum(axis=1) + df["H.Return"]
    out = df[ID_COLUMNS].copy()
    out["typing_speed"] = n_keys / total_time_s.replace(0, pd.NA)
    out["key_latency_avg"] = df[ud_cols].mean(axis=1)
    out["typing_rhythm_std"] = df[ud_cols].std(axis=1, ddof=0)
    out["hold_time_avg"] = df[h_cols].mean(axis=1)
    return out.fillna({"typing_speed": 0.0})


def sequence_frames(
    behavior: pd.DataFrame, *, seq_len: int = 16, stride: int = 4, min_seq: int = 4
) -> tuple[np.ndarray, np.ndarray]:
    """Ordered per-subject `(seq_len, 9)` windows in the full BehaviorFeatures shape
    (Implementation.md Phase 16) -- `behavior` is `behavior_frame()`'s output. CMU's 4
    typing dims are populated in temporal order (sorted `sessionIndex`, `rep`);
    touch/motion/mouse dims are zero, mirroring `train_isolation_forest.py`'s
    per-channel pooling so a CMU-only window is dimension-for-dimension consistent
    with a live web-channel window. Returns `(windows, masks)`: `windows` is
    `(N, seq_len, 9)` float32, `masks` is `(N, seq_len)` bool.
    """
    all_windows: list[np.ndarray] = []
    all_masks: list[np.ndarray] = []
    ordered = behavior.sort_values(["sessionIndex", "rep"])
    for _, s_df in ordered.groupby("subject"):
        padded = pd.DataFrame(0.0, index=s_df.index, columns=BEHAVIOR_COLUMNS)
        for col in _PRESENT:
            padded[col] = s_df[col].to_numpy(dtype=float)
        matrix = padded[BEHAVIOR_COLUMNS].to_numpy(dtype=np.float32)
        w, m = windows_for_series(matrix, seq_len=seq_len, stride=stride, min_seq=min_seq)
        all_windows.extend(w)
        all_masks.extend(m)
    return np.stack(all_windows), np.stack(all_masks)
