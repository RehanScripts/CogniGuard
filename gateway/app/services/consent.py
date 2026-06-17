"""DPDP consent gating (NFR-9, CLAUDE.md invariant 19). Gates the raw `BehaviorSample`
Postgres write only -- not the scoring pipeline or the already-aggregated
`behavior_events` Kafka emission (those carry scalar derived features, not raw
biometric series; NFR-9 is about raw-sample minimization specifically). Withdrawal's
actual cascading hard-delete is Phase 9's `jobs/rtbf.py` job -- this just flips the flag
that job scans for.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session as DbSession

from ..models.user import User


def is_capture_allowed(user: User) -> bool:
    return not user.is_minor and user.consent_status == "GRANTED"


def grant(db: DbSession, user: User, consent_version: str | None = None) -> None:
    user.consent_status = "GRANTED"
    user.consent_timestamp = dt.datetime.now(dt.timezone.utc)
    if consent_version:
        user.consent_version = consent_version
    db.commit()


def withdraw(db: DbSession, user: User) -> None:
    user.consent_status = "WITHDRAWN"
    user.consent_timestamp = dt.datetime.now(dt.timezone.utc)
    db.commit()
