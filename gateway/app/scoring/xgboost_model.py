"""XGBoost -> fraud probability (Architecture §5.2/§9.1, Implementation.md Phase 6)."""

from __future__ import annotations

from typing import Any, Mapping

from training.train_xgboost import FEATURE_COLUMNS


def fraud_probability(features: Mapping[str, float], *, model: Any) -> float:
    """`features` (FeatureBundle.xgb_features()) -> fraud probability in [0,1]. `model`
    is a loaded XGBClassifier or CalibratedClassifierCV(XGBClassifier) (both expose
    predict_proba) -- injected so callers/tests don't need the registry or S3."""
    row = [float(features[col]) for col in FEATURE_COLUMNS]
    return float(model.predict_proba([row])[0][1])
