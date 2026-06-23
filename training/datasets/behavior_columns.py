"""Shared 9-dim `BehaviorFeatures` column order + zero-pad helper (Architecture §5.2).

Extracted out of `training/train_isolation_forest.py` (Phase 5) so the same
load-bearing column-order constant is not duplicated across the IF and LSTM
Autoencoder (Phase 16) training scripts and the dataset adapters that feed both —
`gateway/app/scoring/autoencoder.py`'s `N_FEATURES=9` comment points back at this
exact order.
"""

from __future__ import annotations

import pandas as pd

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


def pad(df: pd.DataFrame, present: list[str]) -> pd.DataFrame:
    """Embed a single-channel feature frame into the full 9-dim BehaviorFeatures
    shape; dims the channel doesn't capture are 0.0 (matches feature_reader.py)."""
    out = pd.DataFrame(0.0, index=df.index, columns=BEHAVIOR_COLUMNS)
    for col in present:
        out[col] = df[col].to_numpy(dtype=float)
    return out
