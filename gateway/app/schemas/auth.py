"""Auth request/response contracts — Implementation.md Phase 2 / §4."""

from typing import Literal

from pydantic import BaseModel

from .behavior import BehaviorPayload


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str
    behavior: BehaviorPayload  # signed (NFR-5), session-bound
    captcha_token: str | None = None


class StepUpVerifyRequest(BaseModel):
    challenge_id: str
    otp_or_assertion: str  # OTP code (demo) or factor assertion


class ConsentRequest(BaseModel):
    username: str
    action: Literal["GRANT", "WITHDRAW"]
    consent_version: str | None = None


class NonceResponse(BaseModel):
    nonce: str
    expires_at: str
