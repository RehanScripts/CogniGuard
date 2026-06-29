"""Reset Rehan's (or any user's) behavioral and transaction data so the account is
clean for fresh enrollment from 10 genuine manual login sessions.

Usage (from gateway/):
    python -m scripts.reset_rehan --username rehan

What this does:
  1. Looks up the user_id by username.
  2. Clears all Redis behavioral/transaction state (profile stats, velocity, amounts,
     known devices/geos/beneficiaries, AE sequence buffers, identity baseline,
     AE calibration, embedding cache).
  3. Sets realistic 30-day spending stats (avg ₹5,000, std ₹2,000) in Redis so
     amplifiers fire correctly on a ₹50,000 new-payee transfer.
  4. Does NOT delete the Postgres user row or password — credentials are preserved.
  5. Prints a summary of what was cleared.

After running this:
  - Perform 10 genuine login sessions manually so enrollment.finalize() builds a
    real behavioral baseline.
  - A ₹50,000 transfer to a new payee will then trigger NEW_BENEF_HIGHVAL ×1.5 and
    AMOUNT_SPIKE ×1.4 (50000 / 5000 = 10×, well above the 3× threshold), producing
    a high-risk decision.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models.user import User
from app.redis_client import redis_client
from app.scoring import calibration, identity


def reset_user(username: str, *, avg_amount: float = 5000.0, std_amount: float = 2000.0) -> None:
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.customer_ref == username))
        if user is None:
            print(f"ERROR: user '{username}' not found in the database.", file=sys.stderr)
            sys.exit(1)

        uid = str(user.user_id)
        print(f"Found user: {username}  user_id={uid}")

        keys_deleted: list[str] = []

        # ── Redis key patterns for this user ──────────────────────────────────
        profile_key = f"user:{uid}:profile"
        known_devices_key = f"user:{uid}:known_devices"
        known_geos_key = f"user:{uid}:known_geos"
        known_benef_key = f"user:{uid}:known_beneficiaries"
        vel_1h = f"user:{uid}:velocity:1h"
        vel_24h = f"user:{uid}:velocity:24h"
        amount_sum = f"user:{uid}:amount_sum:24h"
        new_payees = f"user:{uid}:new_payees_recent"
        risk_baseline = f"user:{uid}:risk_baseline"
        ae_calib = calibration.user_calibration_key(uid)
        identity_baseline = identity.identity_baseline_key(uid)
        embed_cache = f"user:{uid}:embed_sim"
        enroll_buffer = f"behavior:{uid}:enroll"

        # Delete session sequence buffers (behavior:*:seq are session-scoped; we SCAN them).
        seq_keys = list(redis_client.scan_iter("behavior:*:seq"))

        # ── Delete / clear ────────────────────────────────────────────────────
        to_delete = [
            profile_key, known_devices_key, known_geos_key, known_benef_key,
            vel_1h, vel_24h, amount_sum, new_payees, risk_baseline,
            ae_calib, identity_baseline, embed_cache, enroll_buffer,
        ]

        # seq_keys are per-session, not per-user -- we only delete them if they are
        # still associated with a short-lived session (TTL <24h check omitted for safety;
        # they expire anyway). Delete ALL seq buffers only in dev/demo environments.
        to_delete += seq_keys

        deleted = 0
        for key in to_delete:
            n = redis_client.delete(key)
            if n:
                keys_deleted.append(key if isinstance(key, str) else key.decode())
                deleted += n

        # ── Write realistic spending profile ──────────────────────────────────
        # avg_amount_30d / std_amount_30d power the AMOUNT_SPIKE and NEW_BENEF_HIGHVAL
        # amplifiers.  With avg=5000 and std=2000, a ₹50,000 transfer gives:
        #   amount_zscore = (50000 - 5000) / 2000 = 22.5   (very high)
        #   AMOUNT_SPIKE fires: 50000 > 3 × 5000 = 15000  ✓
        #   NEW_BENEF_HIGHVAL fires: 50000 > 0.8 × 5000 = 4000  ✓
        redis_client.hset(
            profile_key,
            mapping={
                "avg_amount_30d": str(avg_amount),
                "std_amount_30d": str(std_amount),
            },
        )
        print(f"Set realistic spending profile → avg_amount_30d=₹{avg_amount:,.0f}, "
              f"std_amount_30d=₹{std_amount:,.0f}")

        print(f"Deleted {deleted} Redis key(s):")
        for k in keys_deleted:
            print(f"  - {k}")

        print(
            "\nRehan is now clean.  Next steps:\n"
            "  1. Register (or log in) as 'rehan' from the Android app.\n"
            "  2. Complete 10 genuine login sessions to build the enrollment baseline.\n"
            "  3. After enrollment, normal logins score Low Risk (no OTP).\n"
            "  4. A ₹50,000 transfer to a NEW payee will fire:\n"
            "       NEW_BENEF_HIGHVAL ×1.5  +  AMOUNT_SPIKE ×1.4  →  High Risk.\n"
        )
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset a user's behavioral/transaction state")
    parser.add_argument("--username", default="rehan", help="Username to reset (default: rehan)")
    parser.add_argument("--avg-amount", type=float, default=5000.0,
                        help="avg_amount_30d to seed (default: 5000)")
    parser.add_argument("--std-amount", type=float, default=2000.0,
                        help="std_amount_30d to seed (default: 2000)")
    args = parser.parse_args()
    reset_user(args.username, avg_amount=args.avg_amount, std_amount=args.std_amount)


if __name__ == "__main__":
    main()
