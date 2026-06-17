"""FeatureBundle (internal model input) — Architecture §5.2.

Assembled from Redis online features + the inline payload (feature_reader, Phase 5).
Scoring helpers (behavior_vector / xgb_features) are added in Phase 6.
"""

from pydantic import BaseModel, Field


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
