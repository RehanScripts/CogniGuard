"""Seed deterministic demo personas + active policy + production models
(Implementation.md §5, PRD §3.1/§7.1). Runnable standalone:

    python -m scripts.seed_demo

Idempotent -- safe to run on every container start (`RUN_SEED_ON_START`, see
entrypoint.sh): existing rows are reused/refreshed rather than duplicated, and Redis
writes simply overwrite in place.

Only `genuine` gets a Postgres user row. The "impostor" persona (PRD §3.1, erratic
rhythm / new device / Tallinn geo / recent Mumbai prior) is purely a different signed
`BehaviorPayload` presented against the `genuine` username at login time -- it needs no
user row of its own (mirrors the existing pattern in tests/test_auth_flow.py). Its
device fingerprint is deliberately never added to `known_devices`, and Tallinn's
geohash is deliberately never added to `known_geos`, so it naturally scores as
new-device + geo-change; the "recent Mumbai prior" is `genuine`'s own seeded profile.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import random
import uuid

from sqlalchemy import select

from app.db import SessionLocal
from app.models.analyst import Analyst
from app.models.beneficiary import Beneficiary, UserBeneficiary
from app.models.governance import ModelRegistry
from app.models.user import User
from app.redis_client import redis_client
from app.schemas.auth import ConsentRequest, RegisterRequest
from app.schemas.behavior import DeviceInfo
from app.services import auth_flow
from app.services.policy import DEFAULT_POLICY, POLICY_REDIS_KEY
from app.utils import fingerprint
from app.utils.geo import geohash
from app.utils.security import hash_password

logger = logging.getLogger("cogniguard.seed_demo")

SEED = 1337
_RNG = random.Random(SEED)

GENUINE_USERNAME = "genuine"
GENUINE_PASSWORD = "Passw0rd!"
GENUINE_DEVICE_FP = "known-mumbai-device-001"
GENUINE_GEO = (19.07, 72.87)  # Mumbai

IMPOSTOR_DEVICE_FP = "impostor-tallinn-device-001"
IMPOSTOR_GEO = (59.43, 24.75)  # Tallinn -- not written anywhere; see module docstring

ADMIN_EMAIL = "admin@cogniguard.dev"
ADMIN_PASSWORD = "Passw0rd!"
ANALYST_EMAIL = "analyst@cogniguard.dev"
ANALYST_PASSWORD = "Passw0rd!"

SCAMMER_VPA = "scammer@upi"
BENEFICIARY_AGE_MINUTES = 40

AVG_AMOUNT_30D = 2000.0  # PRD §5.1 "daily-avg ₹2k"
STD_AMOUNT_30D = 500.0

# Steady "genuine" baseline for the full 9-dim BEHAVIOR_COLUMNS vector that
# isolation_forest.load_baseline reads from behavior:{id}:baseline.
_BASELINE_MEANS = {
    "typing_speed": 4.5,
    "key_latency_avg": 110.0,
    "typing_rhythm_std": 12.0,
    "hold_time_avg": 80.0,
    "swipe_velocity_norm": 0.6,
    "swipe_angle_dev": 0.0,
    "touch_pressure_avg": 0.5,
    "acceleration_variance": 0.0,  # web channel never reports this (mobile-only)
    "mouse_velocity_mean": 0.8,
}
_BASELINE_STDS = {
    "typing_speed": 0.4,
    "key_latency_avg": 15.0,
    "typing_rhythm_std": 3.0,
    "hold_time_avg": 10.0,
    "swipe_velocity_norm": 0.1,
    "swipe_angle_dev": 0.1,
    "touch_pressure_avg": 0.05,
    "acceleration_variance": 0.01,
    "mouse_velocity_mean": 0.1,
}


def _seed_policy() -> None:
    redis_client.set(POLICY_REDIS_KEY, json.dumps(DEFAULT_POLICY))
    logger.info("policy:active seeded with DEFAULT_POLICY")


def _seed_models() -> None:
    with SessionLocal() as db:
        missing = [
            name
            for name in ("isolation_forest", "xgboost_txn")
            if db.scalar(
                select(ModelRegistry).where(
                    ModelRegistry.model_name == name, ModelRegistry.stage == "production"
                )
            )
            is None
        ]
    if not missing:
        logger.info("production models already registered: isolation_forest, xgboost_txn")
        return
    logger.warning("missing production model(s) %s -- training now (non-fatal on failure)", missing)
    try:
        from scripts.load_datasets import load_all

        load_all()
        if "isolation_forest" in missing:
            from training.train_isolation_forest import main as train_isolation_forest

            train_isolation_forest()
        if "xgboost_txn" in missing:
            from training.train_xgboost import main as train_xgboost

            train_xgboost()
    except Exception:
        logger.exception(
            "model training/registration failed (non-fatal -- scoring runs degraded until fixed)"
        )


def _seed_analysts() -> None:
    """admin@cogniguard.dev (role=admin) + analyst@cogniguard.dev (role=analyst) --
    Phase 30 demo logins for the bank-dashboard SOC tool."""
    with SessionLocal() as db:
        for email, password, role in (
            (ADMIN_EMAIL, ADMIN_PASSWORD, "admin"),
            (ANALYST_EMAIL, ANALYST_PASSWORD, "analyst"),
        ):
            existing = db.scalar(select(Analyst).where(Analyst.email == email))
            if existing is None:
                db.add(Analyst(email=email, password_hash=hash_password(password), role=role))
        db.commit()
    logger.info("analysts seeded: %s (admin), %s (analyst)", ADMIN_EMAIL, ANALYST_EMAIL)


def _seed_genuine_user() -> uuid.UUID:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.customer_ref == GENUINE_USERNAME))
        if user is None:
            user = auth_flow.register(
                db, RegisterRequest(username=GENUINE_USERNAME, password=GENUINE_PASSWORD)
            )
        auth_flow.consent_action(
            db, ConsentRequest(username=GENUINE_USERNAME, action="GRANT", consent_version="v1")
        )
        # Read the id out before the session closes -- auth_flow's commits expire ORM
        # attributes, and a detached User would raise on attribute access afterwards.
        return user.user_id


def _seed_known_device_and_geo(user_id: uuid.UUID) -> uuid.UUID:
    with SessionLocal() as db:
        device_info = DeviceInfo(
            fingerprint=GENUINE_DEVICE_FP,
            ua="cogniguard-seed-demo",
            screen="1920x1080",
            timezone="Asia/Kolkata",
            language="en-IN",
            platform="web",
        )
        device = fingerprint.get_or_create_device(db, device_info)
        fingerprint.get_or_create_user_device(db, user_id, device.device_id)
        db.commit()
        device_id = device.device_id
    redis_client.sadd(f"user:{user_id}:known_devices", str(device_id))
    redis_client.sadd(f"user:{user_id}:known_geos", geohash(*GENUINE_GEO))
    return device_id


def _seed_profile_and_baseline(user_id: uuid.UUID) -> None:
    redis_client.hset(
        f"user:{user_id}:profile",
        mapping={
            "avg_amount_30d": str(AVG_AMOUNT_30D),
            "std_amount_30d": str(STD_AMOUNT_30D),
            "last_geo_lat": str(GENUINE_GEO[0]),
            "last_geo_lon": str(GENUINE_GEO[1]),
        },
    )
    baseline: dict[str, float] = {}
    for name, mean in _BASELINE_MEANS.items():
        baseline[name] = mean + _RNG.uniform(-0.01, 0.01)
        baseline[f"{name}_std"] = _BASELINE_STDS[name]
    redis_client.set(f"behavior:{user_id}:baseline", json.dumps({"_baseline": baseline}))


def _seed_beneficiary(user_id: uuid.UUID) -> uuid.UUID:
    """scammer@upi, added ~40 minutes ago. Deliberately NOT added to Redis
    known_beneficiaries -- staying "new" is the whole point of the coercion/
    NEW_BENEF_HIGHVAL amplifier demo (Implementation.md §7.1 step 3)."""
    with SessionLocal() as db:
        beneficiary = db.scalar(
            select(Beneficiary).where(Beneficiary.account_number == SCAMMER_VPA)
        )
        if beneficiary is None:
            beneficiary = Beneficiary(account_number=SCAMMER_VPA, beneficiary_type="UPI")
            db.add(beneficiary)
            db.flush()

        added_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=BENEFICIARY_AGE_MINUTES)
        link = db.scalar(
            select(UserBeneficiary).where(
                UserBeneficiary.user_id == user_id,
                UserBeneficiary.beneficiary_id == beneficiary.beneficiary_id,
            )
        )
        if link is None:
            link = UserBeneficiary(
                user_id=user_id, beneficiary_id=beneficiary.beneficiary_id, added_at=added_at
            )
            db.add(link)
        else:
            link.added_at = added_at  # keep "~40 min ago" fresh across container restarts
        db.commit()
        return beneficiary.beneficiary_id


def main() -> dict[str, str]:
    _seed_policy()
    _seed_models()
    _seed_analysts()
    user_id = _seed_genuine_user()
    device_id = _seed_known_device_and_geo(user_id)
    _seed_profile_and_baseline(user_id)
    beneficiary_id = _seed_beneficiary(user_id)
    summary = {
        "user_id": str(user_id),
        "device_id": str(device_id),
        "beneficiary_id": str(beneficiary_id),
    }
    logger.info("seed_demo complete: %s", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    for key, value in main().items():
        print(f"{key}: {value}")
