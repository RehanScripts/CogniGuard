"""DecisionResponse (gateway → client) — Architecture §5.4."""

from typing import Literal

from pydantic import BaseModel, Field

from .enrollment import EnrollmentProgress
from .scoring import Amplifier, ReasonCode, RiskBand

Action = Literal["allow", "verify", "block"]
EntityType = Literal["login", "transaction"]
ChallengeType = Literal["OTP", "MPIN", "FINGERPRINT", "PASSKEY", "VOICE_READBACK"]
Assurance = Literal["light", "strong"]
ActionSensitivity = Literal["low", "medium", "high"]


class StepUp(BaseModel):
    challenge_type: ChallengeType
    assurance: Assurance
    challenge_id: str


class TxnControls(BaseModel):
    """Transaction-fraud layer (§10.3)."""

    cooling_until: str | None = None
    manual_amount: bool = False
    coercion_check: bool = False
    reconfirm: Literal["APP_PUSH", "EMAIL"] | None = None


class Hardening(BaseModel):
    action: Literal["DELAY", "CAPTCHA", "LOCKOUT"]
    scope: Literal["ip", "device"]
    retry_after_s: int = 0


class DecisionResponse(BaseModel):
    action: Action
    entity_type: EntityType
    risk_score: float
    risk_band: RiskBand
    required_factors: list[str] = Field(default_factory=list)
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    amplifiers: list[Amplifier] = Field(default_factory=list)
    action_sensitivity: ActionSensitivity = "low"
    step_up: StepUp | None = None
    txn_controls: TxnControls | None = None
    session_token: str | None = None
    hardening: Hardening | None = None
    integrity: Literal["OK", "INTEGRITY_REJECT"] = "OK"
    degraded_mode: bool = False
    model_version: str = ""
    # Continuous identity verification (Phase 20-22). `trust_score`/`behavior_match_score`
    # surface the identity-gated Trust Score; `enrollment` drives the calibration banner.
    trust_score: float | None = None
    behavior_match_score: float | None = None
    device_trust: float | None = None
    enrollment: EnrollmentProgress | None = None


class BehaviorIngestResponse(BaseModel):
    """POST /behavior/ingest (Architecture §6.4, Implementation.md Phase 9) -- the
    lightweight continuous-re-scoring response (`{action, reauth}` is the contract the
    client actually needs to act on; the rest is for the dashboard/debugging)."""

    action: Literal["allow", "verify"]
    reauth: bool = False
    risk_score: float
    risk_band: RiskBand
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    degraded_mode: bool = False
    model_version: str = ""
