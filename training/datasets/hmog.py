"""HMOG `hmog_features.csv` adapter (Implementation.md Phase 5).

Applies the `SAMPLE_DATA/eda_report.md` feature-selection findings: drop near-constant
columns, drop columns with no per-user separability (one-way ANOVA p > 0.05 — they
don't reliably distinguish one user's behavioral baseline from another's, which is the
property an Isolation Forest per-user model depends on), and drop one column from each
highly-collinear pair (|r| >= 0.9). NaNs are preserved (a session with too few raw
events for a stat is genuinely missing, never zero-filled — eda_report.md §2).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from training.datasets._windowing import windows_for_series

ID_COLUMNS = ["subject_id", "session_id", "gesture_scenario", "task_id", "activity_count"]

# Full BehaviorFeatures shape (Architecture Sec5.2) -- see cmu.py's BEHAVIOR_COLUMNS
# docstring for why this is duplicated rather than imported.
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
_PRESENT = ["swipe_velocity_norm", "swipe_angle_dev", "acceleration_variance"]

# eda_report.md §7: constant (zero-variance, no signal).
_DROP_CONSTANT = ["touch_pressure_avg", "touch_pressure_std", "tap_pressure_avg"]

# eda_report.md §8: one-way ANOVA p > 0.05 — does not separate users.
_DROP_NO_SEPARABILITY = [
    "multitouch_ratio",
    "tap_count",
    "tap_duration_avg_ms",
    "tap_duration_std_ms",
]

# eda_report.md §6: |r| >= 0.9 pairs — drop one side of each pair.
_DROP_COLLINEAR = [
    "gyro_sample_count",  # vs session_duration_sec (0.9992) and accel_sample_count (0.9952)
    "accel_sample_count",  # vs session_duration_sec (0.9944)
    "touch_inter_event_time_std_ms",  # vs touch_inter_event_time_avg_ms (0.9739)
    "gyro_variance",  # vs gyro_std (0.9659)
    "acceleration_std",  # vs acceleration_variance (0.9634) — BehaviorFeatures keeps acceleration_variance
    "jerk_std",  # vs jerk_mean (0.9535)
    "swipe_duration_std_ms",  # vs swipe_duration_avg_ms (0.9209)
]

DROP_COLUMNS = _DROP_CONSTANT + _DROP_NO_SEPARABILITY + _DROP_COLLINEAR


def load(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the eda_report.md cleanup. Preserves NaN — no zero-fill."""
    return df.drop(columns=[c for c in DROP_COLUMNS if c in df.columns])


def behavior_frame(cleaned: pd.DataFrame) -> pd.DataFrame:
    """subject/session id columns + swipe_velocity_norm, swipe_angle_dev,
    acceleration_variance — the touch/motion-relevant slice of `BehaviorFeatures`
    that survives the eda_report.md cleanup. `touch_pressure_avg` is dropped as
    constant (no signal); callers default that BehaviorFeatures dim to 0.0."""
    cols = [c for c in ID_COLUMNS if c in cleaned.columns]
    return cleaned[cols + ["swipe_velocity_norm", "swipe_angle_dev", "acceleration_variance"]]


def sequence_frames(
    behavior: pd.DataFrame, *, seq_len: int = 16, stride: int = 4, min_seq: int = 4
) -> tuple[np.ndarray, np.ndarray]:
    """Ordered per-subject `(seq_len, 9)` windows in the full BehaviorFeatures shape
    (Implementation.md Phase 16) -- `behavior` is `behavior_frame()`'s output
    (already `dropna`'d by the caller, matching `train_isolation_forest.py`'s
    existing usage). HMOG has no intra-subject timestamp; `session_id` is the only
    ordering signal available (same assumption `eda_report.md` already makes), so
    windows are built per `subject_id` ordered by `session_id`. Touch/motion dims are
    populated; typing/mouse dims are zero. Returns `(windows, masks)` like
    `cmu.sequence_frames()`.
    """
    all_windows: list[np.ndarray] = []
    all_masks: list[np.ndarray] = []
    ordered = behavior.sort_values(["session_id"])
    for _, s_df in ordered.groupby("subject_id"):
        padded = pd.DataFrame(0.0, index=s_df.index, columns=BEHAVIOR_COLUMNS)
        for col in _PRESENT:
            padded[col] = s_df[col].to_numpy(dtype=float)
        matrix = padded[BEHAVIOR_COLUMNS].to_numpy(dtype=np.float32)
        w, m = windows_for_series(matrix, seq_len=seq_len, stride=stride, min_seq=min_seq)
        all_windows.extend(w)
        all_masks.extend(m)
    return np.stack(all_windows), np.stack(all_masks)
