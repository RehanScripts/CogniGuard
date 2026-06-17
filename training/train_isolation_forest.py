"""Global Isolation Forest behavioral prior (Implementation.md Phase 5).

Fits the cold-start `Behavior_Score` prior on pooled CMU (typing) + HMOG (touch/motion)
behavior vectors, in the same 9-dim shape as `BehaviorFeatures` (Architecture §5.2): a
channel's irrelevant dims are zero-padded, exactly matching how `feature_reader.py`
fills `BehaviorFeatures` at serve time for a web-only or mobile-only request. Per-user
baselines (`behavior:{id}:baseline` in Redis) override this prior once a user has one
(Architecture §6.3) — this is only the fallback for new users/channels.

Runnable standalone:  python -m training.train_isolation_forest
"""

from __future__ import annotations

import datetime as dt
import logging
import os

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from app.config import settings
from training import registry, s3_io
from training.datasets import hmog

logger = logging.getLogger("cogniguard.train_isolation_forest")

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
CMU_COLUMNS = ["typing_speed", "key_latency_avg", "typing_rhythm_std", "hold_time_avg"]
HMOG_COLUMNS = ["swipe_velocity_norm", "swipe_angle_dev", "acceleration_variance"]
G6_EER_TARGET = 0.10


def _pad(df: pd.DataFrame, present: list[str]) -> pd.DataFrame:
    """Embed a single-channel feature frame into the full 9-dim BehaviorFeatures
    shape; dims the channel doesn't capture are 0.0 (matches feature_reader.py)."""
    out = pd.DataFrame(0.0, index=df.index, columns=BEHAVIOR_COLUMNS)
    for col in present:
        out[col] = df[col].to_numpy(dtype=float)
    return out


def _eer(genuine: np.ndarray, impostor: np.ndarray) -> float:
    """Equal Error Rate: the (FAR, FRR) pair closest to equal, averaged."""
    thresholds = np.unique(np.concatenate([genuine, impostor]))
    best_gap, best_rate = None, 1.0
    for t in thresholds:
        far = float(np.mean(impostor >= t))
        frr = float(np.mean(genuine < t))
        gap = abs(far - frr)
        if best_gap is None or gap < best_gap:
            best_gap, best_rate = gap, (far + frr) / 2.0
    return best_rate


def validate_g6_eer(cmu_behavior: pd.DataFrame, *, seed: int = 42) -> float:
    """G6: EER <= 10% on the CMU benchmark, Killourhy & Maxion per-subject protocol —
    first 200 reps = reference (fit a one-class model), last 200 = genuine test, 1
    sample from each other subject = impostor attempts. Uses the same reduced typing
    dims the deployed Behavior_Score actually sees (not the raw 31-dim CMU vectors),
    so this measures the EER of what ships, not of a richer offline-only model."""
    genuine_scores: list[float] = []
    impostor_scores: list[float] = []
    for subject in cmu_behavior["subject"].unique():
        s_df = cmu_behavior[cmu_behavior["subject"] == subject].sort_values(["sessionIndex", "rep"])
        train = s_df.iloc[:200][CMU_COLUMNS].to_numpy(float)
        test_genuine = s_df.iloc[200:][CMU_COLUMNS].to_numpy(float)
        if len(train) < 50 or len(test_genuine) == 0:
            continue
        model = IsolationForest(n_estimators=128, contamination="auto", random_state=42).fit(train)
        genuine_scores.extend(model.decision_function(test_genuine))

        others = cmu_behavior[cmu_behavior["subject"] != subject]
        impostor_sample = others.groupby("subject").sample(n=1, random_state=seed)
        impostor_scores.extend(model.decision_function(impostor_sample[CMU_COLUMNS].to_numpy(float)))
    return _eer(np.array(genuine_scores), np.array(impostor_scores))


def main() -> dict:
    cmu_behavior = s3_io.read_parquet("training/cmu/behavior.parquet")
    hmog_cleaned = s3_io.read_parquet("training/hmog/behavior.parquet")
    hmog_behavior = hmog.behavior_frame(hmog_cleaned).dropna(subset=HMOG_COLUMNS)

    pooled = pd.concat([_pad(cmu_behavior, CMU_COLUMNS), _pad(hmog_behavior, HMOG_COLUMNS)], ignore_index=True)

    model = IsolationForest(n_estimators=128, contamination="auto", random_state=42)
    model.fit(pooled[BEHAVIOR_COLUMNS].to_numpy(float))

    eer = validate_g6_eer(cmu_behavior)
    logger.info("G6 EER on CMU benchmark: %.4f (target <= %.2f)", eer, G6_EER_TARGET)

    version = f"isolation_forest@{dt.date.today().isoformat()}"
    artifact_uri = s3_io.write_joblib(
        model,
        f"models/isolation_forest/{version}/model.joblib",
        local_path=os.path.join(settings.model_dir, "isolation_forest", version, "model.joblib"),
    )
    metrics = {"eer": eer, "g6_target": G6_EER_TARGET, "g6_pass": eer <= G6_EER_TARGET, "n_train": len(pooled)}
    registry.register_model(
        model_name="isolation_forest",
        model_type="sklearn.IsolationForest",
        version=version,
        artifact_uri=artifact_uri,
        metrics=metrics,
    )
    return {"version": version, "artifact_uri": artifact_uri, **metrics}


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    result = main()
    for key, value in result.items():
        print(f"{key}: {value}")
