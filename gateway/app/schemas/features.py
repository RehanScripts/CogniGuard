"""FeatureBundle (internal model input) — Architecture §5.2.

Assembled from Redis online features + the inline payload (feature_reader, Phase 5).
Scoring helpers (behavior_vector / xgb_features) are added in Phase 6.
"""

from pydantic import BaseModel, Field

from .behavior import BehaviorPayload

# Canonical column orders the saved model artifacts were fit on (training/, Phase 5) —
# imported rather than redefined so the live feature vector can never silently drift
# from what's actually registered in model_registry.
from training.train_isolation_forest import BEHAVIOR_COLUMNS
from training.train_xgboost import FEATURE_COLUMNS


class BehaviorFeatures(BaseModel):
    typing_speed: float = 0.0
    key_latency_avg: float = 0.0
    typing_rhythm_std: float = 0.0
    hold_time_avg: float = 0.0
    swipe_velocity_norm: float = 0.0
    swipe_angle_dev: float = 0.0
    touch_pressure_avg: float = 0.0
    acceleration_variance: float = 0.0
    mouse_velocity_mean: float = 0.0


class DeviceFeatures(BaseModel):
    device_trust: float = 0.0  # 0..100
    is_new_device: bool = True
    is_rooted: bool = False


class NetworkFeatures(BaseModel):
    geo_distance_km: float = 0.0
    geo_change: bool = False
    vpn: bool = False
    asn: int | None = None


class TxnFeatures(BaseModel):
    amount: float = 0.0
    amount_zscore: float = 0.0
    velocity_1h: int = 0
    velocity_24h: int = 0
    amount_sum_24h: float = 0.0
    is_new_payee: bool = False
    beneficiary_risk: float = 0.0
    odd_time: bool = False
    high_velocity: bool = False


class ContextFeatures(BaseModel):
    hour: int = 0
    dow: int = 0
    session_age_s: float = 0.0
    pre_txn_dwell_ms: float = 0.0
    correction_rate: float = 0.0
    behavior_score: float = 0.0  # Isolation Forest output, fed into XGBoost (stacking)


class FeatureBundle(BaseModel):
    user_id: str
    behavior: BehaviorFeatures = Field(default_factory=BehaviorFeatures)
    device: DeviceFeatures = Field(default_factory=DeviceFeatures)
    network: NetworkFeatures = Field(default_factory=NetworkFeatures)
    txn: TxnFeatures = Field(default_factory=TxnFeatures)
    context: ContextFeatures = Field(default_factory=ContextFeatures)
    cold_start: bool = False  # no per-user profile/baseline yet → bias to verify

    def behavior_vector(self) -> list[float]:
        """9-dim vector in BEHAVIOR_COLUMNS order — matches the IsolationForest artifact."""
        return [getattr(self.behavior, name) for name in BEHAVIOR_COLUMNS]

    def xgb_features(self, behavior_score: float) -> dict[str, float]:
        """Dict with the live Behavior_Score substituted in for the training-time
        neutral placeholder (training/train_xgboost.py). Built from FEATURE_COLUMNS so
        a column the model expects can never silently go missing."""
        values = {
            "amount": self.txn.amount,
            "amount_zscore": self.txn.amount_zscore,
            "velocity_1h": float(self.txn.velocity_1h),
            "velocity_24h": float(self.txn.velocity_24h),
            "amount_sum_24h": self.txn.amount_sum_24h,
            "is_new_payee": float(self.txn.is_new_payee),
            "beneficiary_risk": self.txn.beneficiary_risk,
            "odd_time": float(self.txn.odd_time),
            "behavior_score": behavior_score,
        }
        return {col: values[col] for col in FEATURE_COLUMNS}


class FeatureReadContext(BaseModel):
    """Input to `feature_reader.read_bundle` — the signed BehaviorPayload plus whatever
    transaction/device/geo context the calling router (login/payment/behavior-ingest,
    Phase 7/8) already has on hand. read_bundle resolves everything else from Redis."""

    behavior: BehaviorPayload
    device_id: str | None = None
    geo_lat: float | None = None
    geo_lon: float | None = None
    amount: float = 0.0
    beneficiary_id: str | None = None
    vpn: bool = False
    asn: int | None = None
