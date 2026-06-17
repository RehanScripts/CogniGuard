"""Isolation Forest -> Behavior_Score (Architecture §5.2/§9.1, Implementation.md Phase 6).

`decision_function` is sklearn's convention: higher = more normal. We flip the sign and
squash through a logistic so Behavior_Score lands in [0,1] with 0 = very normal, 1 = very
anomalous -- the polarity XGBoost/explain expect (Architecture §5.3: "Isolation Forest
[0,1] => Behavior_Score").
"""

from __future__ import annotations

import json
import math
from typing import Any, Sequence

from redis import Redis

from training.train_isolation_forest import BEHAVIOR_COLUMNS

EPS = 1e-9

# behavior:{id}:baseline (flink-jobs/sinks.py, BEHAVIOR_FEATURES) only tracks 5
# abbreviated dims, not the 9 BehaviorFeatures names -- a pre-existing Phase 4 gap, not
# something Phase 6 should fix by renaming a separate deployment unit's keys. Map the
# overlapping dims; the rest pass through unstandardized.
_BASELINE_KEY_MAP = {
    "typing_speed": "typing_speed",
    "key_latency_avg": "key_latency",
    "swipe_angle_dev": "swipe_angle",
    "touch_pressure_avg": "touch_pressure",
    "mouse_velocity_mean": "mouse_velocity",
}


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def load_baseline(user_id: str, *, redis: Redis) -> dict[str, tuple[float, float]] | None:
    """Read behavior:{id}:baseline (Flink-written JSON). Returns {feature: (mean, std)}
    for the overlapping dims, or None if absent (cold-start / new user)."""
    raw = redis.get(f"behavior:{user_id}:baseline")
    if not raw:
        return None
    acc = json.loads(raw)
    baseline = acc.get("_baseline", {})
    out: dict[str, tuple[float, float]] = {}
    for bf_name, flink_name in _BASELINE_KEY_MAP.items():
        if flink_name in baseline:
            out[bf_name] = (baseline[flink_name], baseline.get(f"{flink_name}_std", 0.0))
    return out or None


def standardize(
    vector: Sequence[float], baseline: dict[str, tuple[float, float]] | None
) -> list[float]:
    """z-score each dim that has a baseline entry; passthrough dims without one."""
    if not baseline:
        return list(vector)
    out = []
    for name, x in zip(BEHAVIOR_COLUMNS, vector):
        if name in baseline:
            mean, std = baseline[name]
            out.append((x - mean) / max(std, EPS))
        else:
            out.append(x)
    return out


def behavior_score(
    vector: Sequence[float], *, model: Any, baseline: dict[str, tuple[float, float]] | None = None
) -> float:
    """[0,1] anomaly score. `model` is a loaded sklearn IsolationForest (injected --
    callers get it from registry.get("isolation_forest").model). `baseline`, when given,
    standardizes the vector against the user's behavior:{id}:baseline first; otherwise
    the global prior (the model itself) covers cold-start (Architecture §7.6)."""
    x = standardize(vector, baseline)
    raw = float(model.decision_function([x])[0])  # higher = more normal
    return _sigmoid(-raw)
