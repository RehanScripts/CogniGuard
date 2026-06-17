"""Payment scoring contracts (§10.3) — Implementation.md Phase 2."""

from typing import Literal

from pydantic import BaseModel

from .behavior import BehaviorPayload
from .decision import DecisionResponse

TransferType = Literal["IMPS", "NEFT", "RTGS", "UPI"]


class PaymentScoreRequest(BaseModel):
    amount: float
    beneficiary_id: str | None = None
    beneficiary_vpa: str | None = None
    transfer_type: TransferType = "UPI"
    channel: Literal["web", "mobile"] = "mobile"
    behavior: BehaviorPayload  # signed, session-bound (Bearer JWT carries the session)


class PaymentScoreResponse(DecisionResponse):
    base_score: float = 0.0  # pre-amplifier 0..100
    # entity_type is always "transaction" on this path
