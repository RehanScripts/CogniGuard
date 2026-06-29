"""Reset all data for a specific demo user by username (case-insensitive).

Usage (inside the gateway container):
    python -m scripts.reset_user --username rehan

Safe to run repeatedly. Does NOT touch:
  - Other users' data
  - Seeded demo data (genuine/impostor personas)
  - Policy, model registry, analyst accounts
  - Population-level calibration (calib:ae:population)
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid

from sqlalchemy import delete, select

from app.db import SessionLocal
from app.models.governance import AuditLog, Case
from app.models.scoring import Decision, RiskScore
from app.models.session import LoginEvent, Session as SessionModel
from app.models.transaction import Transaction
from app.models.user import User
from app.redis_client import redis_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("cogniguard.reset_user")


def _redis_keys_for_user(user_id: str, session_ids: list[str]) -> list[str]:
    uid = user_id
    keys = [
        f"user:{uid}:known_devices",
        f"user:{uid}:known_geos",
        f"user:{uid}:known_beneficiaries",
        f"user:{uid}:profile",
        f"user:{uid}:risk_baseline",
        f"behavior:{uid}:baseline",
        f"behavior:{uid}:enroll",
        f"behavior:{uid}:identity_baseline",
        f"behavior:{uid}:ae_calib",
    ]
    for sid in session_ids:
        keys.append(f"session:risk:{sid}")
    return keys


def reset_user(username: str) -> None:
    with SessionLocal() as db:
        user = db.scalar(
            select(User).where(User.customer_ref == username)
        )
        if user is None:
            # Try case-insensitive search
            user = db.scalar(
                select(User).where(User.customer_ref.ilike(username))
            )
        if user is None:
            log.warning("No user found with username %r — nothing to reset.", username)
            return

        uid: uuid.UUID = user.user_id
        uid_str = str(uid)
        log.info("Found user %r  user_id=%s", username, uid_str)

        # Collect session IDs before we delete them (needed for Redis cleanup).
        session_ids = [
            str(sid)
            for sid in db.scalars(
                select(SessionModel.session_id).where(SessionModel.user_id == uid)
            ).all()
        ]
        log.info("  Sessions to purge: %d", len(session_ids))

        # Collect transaction IDs (needed to find linked decisions).
        txn_ids = [
            str(tid)
            for tid in db.scalars(
                select(Transaction.transaction_id).where(Transaction.user_id == uid)
            ).all()
        ]
        log.info("  Transactions to purge: %d", len(txn_ids))

        # --- PostgreSQL cleanup (order matters for FK constraints) ---

        # 1. decisions: linked via entity_id (session or txn UUIDs), no direct user FK.
        entity_uuids: list[uuid.UUID] = [uuid.UUID(s) for s in session_ids + txn_ids]
        if entity_uuids:
            n_decisions = db.execute(
                delete(Decision).where(Decision.entity_id.in_(entity_uuids))
            ).rowcount
            log.info("  Deleted decisions: %d", n_decisions)

        # 2. risk_scores: user_id is SET NULL on user delete, so delete explicitly.
        n_scores = db.execute(
            delete(RiskScore).where(RiskScore.user_id == uid)
        ).rowcount
        log.info("  Deleted risk_scores: %d", n_scores)

        # 3. cases: user_id is SET NULL on user delete, so delete explicitly.
        n_cases = db.execute(
            delete(Case).where(Case.user_id == uid)
        ).rowcount
        log.info("  Deleted cases: %d", n_cases)

        # 4. audit_logs: actor_id is a string (not FK), keyed by user_id string.
        n_audit = db.execute(
            delete(AuditLog).where(AuditLog.actor_id == uid_str)
        ).rowcount
        log.info("  Deleted audit_logs: %d", n_audit)

        # 5. login_events: session_id CASCADE from sessions, but user_id is SET NULL.
        #    Delete explicitly now before the cascade happens so we get them cleanly.
        n_events = db.execute(
            delete(LoginEvent).where(LoginEvent.user_id == uid)
        ).rowcount
        log.info("  Deleted login_events: %d", n_events)

        # 6. Delete the user row — CASCADE handles:
        #    accounts, sessions, behavior_samples, user_devices,
        #    transactions, user_beneficiaries, auth_challenges (via sessions)
        db.delete(user)
        db.commit()
        log.info("  Deleted user row (+ CASCADE: accounts, sessions, behavior_samples, "
                 "user_devices, transactions, user_beneficiaries, auth_challenges)")

    # --- Redis cleanup ---
    redis_keys = _redis_keys_for_user(uid_str, session_ids)
    deleted = redis_client.delete(*redis_keys) if redis_keys else 0
    log.info("  Deleted Redis keys: %d (of %d attempted)", deleted, len(redis_keys))
    for k in redis_keys:
        log.debug("    - %s", k)

    log.info("Reset complete for user %r (%s).", username, uid_str)
    log.info("")
    log.info("You can now create a fresh account at the Sign Up screen.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset all data for a CogniGuard demo user.")
    parser.add_argument(
        "--username",
        default="rehan",
        help="customer_ref / username to wipe (default: rehan)",
    )
    args = parser.parse_args()
    reset_user(args.username)


if __name__ == "__main__":
    main()
