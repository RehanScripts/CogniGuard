"""HMOG `hmog_features.csv` adapter (Implementation.md Phase 5).

Applies the `SAMPLE_DATA/eda_report.md` feature-selection findings: drop near-constant
columns, drop columns with no per-user separability (one-way ANOVA p > 0.05 — they
don't reliably distinguish one user's behavioral baseline from another's, which is the
property an Isolation Forest per-user model depends on), and drop one column from each
highly-collinear pair (|r| >= 0.9). NaNs are preserved (a session with too few raw
events for a stat is genuinely missing, never zero-filled — eda_report.md §2).
"""

from __future__ import annotations

import pandas as pd

ID_COLUMNS = ["subject_id", "session_id", "gesture_scenario", "task_id", "activity_count"]

# eda_report.md §7: constant (zero-variance, no signal).
_DROP_CONSTANT = ["touch_pressure_avg", "touch_pressure_std", "tap_pressure_avg"]

# eda_report.md §8: one-way ANOVA p > 0.05 — does not separate users.
_DROP_NO_SEPARABILITY = ["multitouch_ratio", "tap_count", "tap_duration_avg_ms", "tap_duration_std_ms"]

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
