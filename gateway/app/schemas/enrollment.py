"""Enrollment contracts (Implementation.md Phase 21).

Drives the "Security Profile Calibration N/10" banner on web + Android. Progress accrues
over the user's first ~N genuine login/app-open cycles; on the cycle that reaches
`required`, the enrollment service auto-finalizes the per-user identity baseline +
calibration (never seeded -- computed from the captured sessions).
"""

from __future__ import annotations

from pydantic import BaseModel


class EnrollmentProgress(BaseModel):
    collected: int  # genuine sessions captured so far
    required: int  # MIN_ENROLL_SESSIONS from policy
    complete: bool  # True once a finalized identity_baseline exists
    just_finalized: bool = False  # True only on the cycle that crossed `required`


class EnrollRequest(BaseModel):
    """Standalone `POST /enroll` body -- the same per-cycle capture the login path drives
    automatically, exposed so enrollment can be tested/driven in isolation."""

    username: str
    behavior_vector: list[float]  # 9 dims, BEHAVIOR_COLUMNS order
    ae_recon_error: float | None = None


class EnrollResponse(BaseModel):
    user_id: str
    progress: EnrollmentProgress
