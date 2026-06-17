"""Canonical Pydantic v2 contracts — Architecture §5 / §4.2."""

from .auth import (
    ConsentRequest,
    LoginRequest,
    NonceResponse,
    RegisterRequest,
    StepUpVerifyRequest,
)
from .behavior import BehaviorPayload, DeviceInfo, KeyEvent
from .decision import DecisionResponse, Hardening, StepUp, TxnControls
from .features import FeatureBundle
from .payment import PaymentScoreRequest, PaymentScoreResponse
from .scoring import Amplifier, ReasonCode, ScoreResult
from .topics import (
    BehaviorEvent,
    DecisionEvent,
    DeviceEvent,
    LoginEventMsg,
    RiskScoreEvent,
    TransactionEvent,
)

__all__ = [
    "BehaviorPayload",
    "DeviceInfo",
    "KeyEvent",
    "FeatureBundle",
    "ScoreResult",
    "ReasonCode",
    "Amplifier",
    "DecisionResponse",
    "StepUp",
    "TxnControls",
    "Hardening",
    "RegisterRequest",
    "LoginRequest",
    "StepUpVerifyRequest",
    "ConsentRequest",
    "NonceResponse",
    "PaymentScoreRequest",
    "PaymentScoreResponse",
    "BehaviorEvent",
    "DeviceEvent",
    "LoginEventMsg",
    "TransactionEvent",
    "RiskScoreEvent",
    "DecisionEvent",
]
