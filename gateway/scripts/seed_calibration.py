"""Re-seed `calib:ae:population` into Redis from the production `lstm_autoencoder`
row's persisted metrics (Implementation.md Phase 16). `training.train_lstm_autoencoder`
already seeds this key itself as the last step of training -- this script is the
disaster-recovery / Redis-rebuild path (CLAUDE.md invariant 3: "Redis is rebuildable
from PostgreSQL... a derived cache, not a source of truth") for when Redis is flushed
or rebuilt without re-running a multi-minute training job.

Runnable standalone:  python -m scripts.seed_calibration
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import select

from app.db import SessionLocal
from app.models.governance import ModelRegistry
from app.redis_client import redis_client
from app.scoring.calibration import POPULATION_CALIBRATION_KEY

logger = logging.getLogger("cogniguard.seed_calibration")


def main() -> dict:
    with SessionLocal() as session:
        row = session.scalar(
            select(ModelRegistry)
            .where(
                ModelRegistry.model_name == "lstm_autoencoder", ModelRegistry.stage == "production"
            )
            .order_by(ModelRegistry.deployed_at.desc())
        )
    if row is None:
        raise LookupError(
            "no production lstm_autoencoder row -- run training.train_lstm_autoencoder first"
        )
    calib = (row.metrics or {}).get("calibration")
    if not calib:
        raise LookupError(
            f"production lstm_autoencoder row {row.version!r} has no calibration metrics"
        )

    payload = {
        "scale": calib["scale"],
        "threshold": calib["threshold"],
        "temperature": calib.get("temperature", 1.0),
    }
    redis_client.set(POPULATION_CALIBRATION_KEY, json.dumps(payload))
    return {"version": row.version, **payload}


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    result = main()
    for key, value in result.items():
        print(f"{key}: {value}")
