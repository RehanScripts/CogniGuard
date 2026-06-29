"""Kafka topic payload contracts — Architecture §4.2 / PRD §17.3.

Input topics: behavior_events, device_events, login_events, transaction_events
Output topics: risk_scores, decisions
"""

from pydantic import BaseModel, Field

from .decision import Action, EntityType
from .scoring import RiskBand

# --- topic names (canonical) ---
T_BEHAVIOR = "behavior_events"
T_DEVICE = "device_events"
T_LOGIN = "login_events"
T_TRANSACTION = "transaction_events"
T_RISK_SCORES = "risk_scores"
T_DECISIONS = "decisions"

INPUT_TOPICS = [T_BEHAVIOR, T_DEVICE, T_LOGIN, T_TRANSACTION]
OUTPUT_TOPICS = [T_RISK_SCORES, T_DECISIONS]
ALL_TOPICS = INPUT_TOPICS + OUTPUT_TOPICS


class BehaviorEvent(BaseModel):  # key: user_id
    """The 9 scalar dims match `BehaviorFeatures`/`BEHAVIOR_COLUMNS` exactly (Architecture
    §4.2) so Flink's `behavior:{id}:baseline` can track the full vector the IF/AE scorers
    consume. `typing_rhythm` is the separate raw inter-key-latency vector — stored, not
    used for baseline math."""

    user_id: str = ""  # denormalized into the value for self-contained routing
    session_id: str
    typing_speed: float = 0.0
    typing_rhythm: list[float] = Field(default_factory=list)  # inter-key latency vector
    key_latency_avg: float = 0.0
    typing_rhythm_std: float = 0.0
    hold_time_avg: float = 0.0
    swipe_velocity_norm: float = 0.0
    swipe_angle_dev: float = 0.0
    touch_pressure_avg: float = 0.0
    acceleration_variance: float = 0.0
    mouse_velocity_mean: float = 0.0
    ts: str


class DeviceEvent(BaseModel):  # key: device_id
    device_id: str = ""  # denormalized into the value for self-contained routing
    device_fingerprint: str
    os: str = ""
    app_version: str = ""
    is_rooted: bool = False
    is_emulator: bool = False
    ts: str


class LoginEventMsg(BaseModel):  # key: user_id
    user_id: str = ""  # denormalized into the value for self-contained routing
    session_id: str
    device_id: str
    ip: str = ""
    asn: int | None = None
    is_vpn: bool = False
    geo_lat: float | None = None
    geo_lon: float | None = None
    ts: str


class TransactionEvent(BaseModel):  # key: user_id
    user_id: str = ""  # denormalized into the value for self-contained routing
    transaction_id: str
    amount: float
    beneficiary_id: str | None = None
    transfer_type: str = "UPI"
    is_new_payee: bool = False
    ts: str


class RiskScoreEvent(BaseModel):
    entity_type: EntityType
    entity_id: str
    behavior_score: float
    device_score: float
    transaction_score: float
    final_risk_score: float
    risk_band: RiskBand
    model_version: str
    ts: str
    # Continuous identity verification (Phase 20-22) -- powers the dashboard Trust panel.
    trust_score: float | None = None
    behavior_match_score: float | None = None
    # AE-primary/IF-shadow provenance (Phase 14/15), surfaced to the SOC feed in Phase 27
    # so judges can see the AE/IF source per event, not just the fused Behavior_Score.
    behavior_score_source: str | None = None
    # Threaded through so the SOC Live feed can link a row straight to its UserDetail
    # drill-down (`/users/{user_id}`) without a second lookup by entity_id.
    user_id: str | None = None
    # Pre-generated UUID threaded from the flow so the WS feed can open SHAP/AI directly.
    score_id: str | None = None


class DecisionEvent(BaseModel):
    entity_type: EntityType
    entity_id: str
    action: Action
    required_factors: list[str] = Field(default_factory=list)
    reason_codes: list[dict] = Field(default_factory=list)
    ts: str
    user_id: str | None = None
