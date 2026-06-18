"""Right-to-be-forgotten cascading hard-delete (DPDP Act 2023, CLAUDE.md invariant 19,
Implementation.md Phase 9). `consent.withdraw()` only flips `User.consent_status` to
WITHDRAWN -- this job does the actual purge: raw `BehaviorSample` rows + the per-user
IF baseline Flink writes to Redis (`behavior:{id}:baseline`, the "per-user model
artifact"). `risk_scores`/`decisions`/`audit_logs` are retained as-is (they carry score/
band/decision, not raw biometric data, so there's nothing to strip). Also enforces
`retention_expires_at` purges independent of consent status. Run as
`python -m app.jobs.rtbf` (cron/K8s CronJob in prod).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models.behavior import BehaviorSample
from ..models.user import User
from ..redis_client import redis_client
from ..services.audit import write_audit_log


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _purge_user(db: DbSession, user: User) -> int:
    samples = db.scalars(select(BehaviorSample).where(BehaviorSample.user_id == user.user_id)).all()
    count = len(samples)
    for sample in samples:
        db.delete(sample)
    redis_client.delete(f"behavior:{user.user_id}:baseline")

    write_audit_log(
        db,
        actor_type="system",
        actor_id="rtbf_job",
        action="RTBF_PURGE",
        entity_type="user",
        entity_id=user.user_id,
        metadata={"samples_deleted": count},
    )
    return count


def run_rtbf(db: DbSession) -> dict[str, int]:
    withdrawn_users = db.scalars(select(User).where(User.consent_status == "WITHDRAWN")).all()
    samples_deleted = sum(_purge_user(db, user) for user in withdrawn_users)

    now = _now()
    expired = db.scalars(
        select(BehaviorSample).where(
            BehaviorSample.retention_expires_at.isnot(None),
            BehaviorSample.retention_expires_at <= now,
        )
    ).all()
    retention_purged = len(expired)
    for sample in expired:
        db.delete(sample)

    db.commit()
    return {
        "users_purged": len(withdrawn_users),
        "samples_deleted": samples_deleted,
        "retention_purged": retention_purged,
    }


if __name__ == "__main__":
    from ..db import SessionLocal

    session = SessionLocal()
    try:
        print(run_rtbf(session))
    finally:
        session.close()
