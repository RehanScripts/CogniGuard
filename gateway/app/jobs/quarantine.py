"""Anti-poisoning quarantine promotion (CLAUDE.md invariant 17, Implementation.md
Phase 9): step-up-passed `BehaviorSample` rows are written `accepted=False,
quarantine_until=captured_at+7d` (`auth_flow.login`). Once that window has elapsed,
promote to `accepted=True` only if nothing in the window indicates the session was
actually fraudulent/anomalous; otherwise discard the sample so it can never reach the
Flink baseline. Run as `python -m app.jobs.quarantine` (cron/K8s CronJob in prod).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models.behavior import BehaviorSample
from ..models.governance import Case
from ..models.scoring import RiskScore
from ..models.session import LoginEvent

_BAD_BANDS = ("high", "very_high")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _clean_window(db: DbSession, sample: BehaviorSample) -> bool:
    """No fraud complaint, no subsequent high-risk event, no login block for this user
    since the sample was captured."""
    if sample.user_id is None:
        return False

    bad_case = db.scalar(
        select(Case).where(
            Case.user_id == sample.user_id,
            Case.status == "confirmed_fraud",
            Case.created_at >= sample.captured_at,
        )
    )
    if bad_case is not None:
        return False

    bad_score = db.scalar(
        select(RiskScore).where(
            RiskScore.user_id == sample.user_id,
            RiskScore.risk_band.in_(_BAD_BANDS),
            RiskScore.scored_at >= sample.captured_at,
        )
    )
    if bad_score is not None:
        return False

    bad_login = db.scalar(
        select(LoginEvent).where(
            LoginEvent.user_id == sample.user_id,
            LoginEvent.decision == "block",
            LoginEvent.created_at >= sample.captured_at,
        )
    )
    if bad_login is not None:
        return False

    return True


def run_promotion(db: DbSession) -> dict[str, int]:
    now = _now()
    candidates = db.scalars(
        select(BehaviorSample).where(
            BehaviorSample.accepted.is_(False),
            BehaviorSample.quarantine_until.isnot(None),
            BehaviorSample.quarantine_until <= now,
        )
    ).all()

    promoted = discarded = 0
    for sample in candidates:
        if _clean_window(db, sample):
            sample.accepted = True
            sample.quarantine_until = None
            promoted += 1
        else:
            db.delete(sample)
            discarded += 1

    db.commit()
    return {"promoted": promoted, "discarded": discarded}


if __name__ == "__main__":
    from ..db import SessionLocal

    session = SessionLocal()
    try:
        print(run_promotion(session))
    finally:
        session.close()
