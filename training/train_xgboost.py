"""Supervised XGBoost fraud classifier (Implementation.md Phase 5).

Trains on `TXN_HISTORY_UPI_FIN`, which carries no fraud label, so the PRD §6.6 heuristic
(`is_new_payee AND amount_zscore > 2 AND odd_time` -> synthetic fraud) supplies the
target. `behavior_score` is part of the input schema (the stacked IF output,
Architecture §5.2/§9.1) but `TXN_HISTORY_UPI_FIN` is a backend transaction log with no
paired client-side telemetry, so it's set to a neutral 0.5 for every training row here —
at serve time this column carries the live IsolationForest `Behavior_Score` from
`feature_reader`; a future dataset with paired behavioral telemetry should replace this
placeholder. `INB_REQ_LOG`'s session features (Phase 5's other adapter) aren't joined in
here: the two sample extracts use disjoint user/account id namespaces, so there's no
real key to join on in this sample data.

Runnable standalone:  python -m training.train_xgboost
"""

from __future__ import annotations

import datetime as dt
import logging
import math
import os

import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from app.config import settings
from training import registry, s3_io

logger = logging.getLogger("cogniguard.train_xgboost")

FEATURE_COLUMNS = [
    "amount",
    "amount_zscore",
    "velocity_1h",
    "velocity_24h",
    "amount_sum_24h",
    "is_new_payee",
    "beneficiary_risk",
    "odd_time",
    "behavior_score",
]
NEUTRAL_BEHAVIOR_SCORE = 0.5  # no paired telemetry in TXN_HISTORY_UPI_FIN — see module docstring
MIN_POSITIVES_FOR_CALIBRATION = 6


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["is_new_payee"] = df["is_new_payee"].astype(int)
    df["odd_time"] = df["odd_time"].astype(int)
    df["behavior_score"] = NEUTRAL_BEHAVIOR_SCORE
    return df


def main() -> dict:
    df = _prepare(s3_io.read_parquet("training/txn/transactions.parquet"))
    X = df[FEATURE_COLUMNS].to_numpy(float)
    y = df["label"].to_numpy(int)
    n_pos = int(y.sum())
    logger.info("training rows=%d positives=%d (heuristic label)", len(y), n_pos)

    stratify = y if n_pos >= 2 and (len(y) - n_pos) >= 2 else None
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=stratify
    )

    base = XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.1, eval_metric="logloss", random_state=42
    )
    calibrated = n_pos >= MIN_POSITIVES_FOR_CALIBRATION
    if calibrated:
        model = CalibratedClassifierCV(base, method="sigmoid", cv=3)
        model.fit(X_train, y_train)
    else:
        logger.warning(
            "only %d positives from the heuristic label — skipping probability calibration", n_pos
        )
        model = base.fit(X_train, y_train)

    auc: float | None = None
    if len(set(y_test)) > 1:
        auc = float(roc_auc_score(y_test, model.predict_proba(X_test)[:, 1]))
    else:
        logger.warning("test split has a single class — AUC undefined")
    if auc is not None and math.isnan(auc):
        auc = None
    logger.info("held-out AUC: %s", auc)

    version = f"xgboost_txn@{dt.date.today().isoformat()}"
    artifact_uri = s3_io.write_joblib(
        model,
        f"models/xgboost_txn/{version}/model.joblib",
        local_path=os.path.join(settings.model_dir, "xgboost_txn", version, "model.joblib"),
    )
    metrics = {
        "auc": auc,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "n_positive": n_pos,
        "calibrated": calibrated,
        "feature_columns": FEATURE_COLUMNS,
    }
    registry.register_model(
        model_name="xgboost_txn",
        model_type="xgboost.XGBClassifier" + ("+CalibratedClassifierCV" if calibrated else ""),
        version=version,
        artifact_uri=artifact_uri,
        metrics=metrics,
    )
    return {"version": version, "artifact_uri": artifact_uri, "auc": auc, "n_positive": n_pos}


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    result = main()
    for key, value in result.items():
        print(f"{key}: {value}")
