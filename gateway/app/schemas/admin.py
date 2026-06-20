"""Admin / dashboard contracts — Implementation.md Phase 2 / §4."""

from typing import Literal

from pydantic import BaseModel, Field

from .scoring import RiskBand


class PolicyUpdate(BaseModel):
    scoring_mode: Literal["stacked", "weighted"] = "stacked"
    weights: dict[str, float] = Field(default_factory=dict)
    thresholds: dict[str, float] = Field(default_factory=dict)  # low_max, medium_max, very_high_min
    action_sensitivity: dict = Field(default_factory=dict)  # risk×action matrix
    amplifiers: dict[str, float] = Field(default_factory=dict)
    stepup: dict = Field(default_factory=dict)  # assurance ladder
    cooling_off: dict = Field(default_factory=dict)
    hardening: dict = Field(default_factory=dict)
    drift: dict = Field(default_factory=dict)  # PSI/KS + outcome-precision breach thresholds


class EventOut(BaseModel):
    score_id: str
    entity_type: str
    entity_id: str | None = None
    user_id: str | None = None
    final_risk_score: float | None = None
    risk_band: RiskBand | None = None
    action: str | None = None
    model_version: str | None = None
    latency_ms: int | None = None
    scored_at: str | None = None


class UserDetailOut(BaseModel):
    user: dict
    devices: list[dict] = Field(default_factory=list)
    recent_events: list[EventOut] = Field(default_factory=list)
    quarantined_samples: int = 0


class CaseUpdate(BaseModel):
    status: (
        Literal["open", "investigating", "confirmed_fraud", "false_positive", "closed"] | None
    ) = None
    assigned_to: str | None = None
    note: str | None = None


class CaseOut(BaseModel):
    case_id: str
    user_id: str | None = None
    transaction_id: str | None = None
    alert_type: str | None = None
    severity: str | None = None
    status: str
    assigned_to: str | None = None
    created_at: str | None = None
    resolved_at: str | None = None


class ModelVersionOut(BaseModel):
    model_id: str
    version: str | None = None
    stage: str | None = None  # staging|production|archived
    model_type: str | None = None
    metrics: dict = Field(default_factory=dict)
    artifact_uri: str | None = None
    deployed_at: str | None = None


class ModelOut(BaseModel):
    model_name: str
    versions: list[ModelVersionOut] = Field(default_factory=list)


class PromoteRequest(BaseModel):
    version: str | None = None  # defaults to the latest staging row for the model


class RollbackRequest(BaseModel):
    version: str  # must be an archived version of the model


class DriftReportOut(BaseModel):
    window: dict
    columns: dict
    outcome: dict
    breaches: list[dict] = Field(default_factory=list)
    retrained_models: list[str] = Field(default_factory=list)
