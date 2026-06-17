"""ScoreResult (scoring service, internal) — Architecture §5.3."""

from typing import Literal

from pydantic import BaseModel, Field

RiskBand = Literal["low", "medium", "high", "very_high"]


class ReasonCode(BaseModel):
    code: str
    detail: str = ""
    sigma: float | None = None  # standardized deviation, when a deviation driver


class Amplifier(BaseModel):
    code: str  # NEW_BENEF_HIGHVAL | RAPID_FANOUT | DRAIN | COERCION_TIME
    multiplier: float
    detail: str = ""

    def as_reason(self) -> ReasonCode:
        return ReasonCode(code=self.code, detail=self.detail)


class ScoreResult(BaseModel):
    behavior_score: float  # Isolation Forest [0,1] ⇒ Behavior_Score (stacked into XGBoost)
    device_score: float = 0.0
    transaction_score: float  # XGBoost fraud probability [0,1]
    final_risk_score: float  # 0..100 (after amplifiers on the txn path)
    base_score: float = 0.0  # pre-amplifier 0..100
    risk_band: RiskBand
    model_version: str
    amplifiers: list[Amplifier] = Field(default_factory=list)
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    degraded_mode: bool = False
    latency_ms: int = 0
