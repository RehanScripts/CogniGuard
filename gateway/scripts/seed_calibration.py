"""Seed AE model-registry rows (from a local pre-trained artifact) + `calib:ae:population`
(Implementation.md Phase 16's disaster-recovery path, extended in Phase 26 to also
self-heal a genuinely missing registry row on first boot).

`training.train_lstm_autoencoder` is the canonical writer of both the `lstm_autoencoder`/
`lstm_autoencoder_tflite` model_registry rows and `calib:ae:population` -- but it requires
TensorFlow, deliberately NOT a gateway dependency (CLAUDE.md), so it can't be run
automatically on every container start the way `train_isolation_forest`/`train_xgboost`
are in `seed_demo.py`. If a production row is missing AND a pre-trained `model.onnx`/
`model.tflite` artifact already exists under `MODEL_DIR` (from a prior offline training
run, mounted via the `./models:/models` bind), this registers it using whichever
calibration metrics that training run captured, or this module's own documented neutral
default (`calibration.default_calibration()`) if none were captured -- it never invents
new math, never trains anything itself. If no local artifact exists either (fresh
checkout, training never run), this is a no-op and AE correctly stays cold-start
(existing IF-shadow-fallback behavior, CLAUDE.md invariant 9).

Runnable standalone:  python -m scripts.seed_calibration
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models.governance import ModelRegistry
from app.redis_client import redis_client
from app.scoring import calibration
from app.scoring.calibration import POPULATION_CALIBRATION_KEY

logger = logging.getLogger("cogniguard.seed_calibration")

_ARTIFACT_FILENAMES = {
    "lstm_autoencoder": "model.onnx",
    "lstm_autoencoder_tflite": "model.tflite",
}
_MODEL_TYPES = {
    "lstm_autoencoder": "keras.LSTMAutoencoder(onnx)",
    "lstm_autoencoder_tflite": "keras.LSTMAutoencoder(tflite)",
}


def _latest_local_version(model_name: str) -> str | None:
    """Newest `{model_name}@<date>` directory under MODEL_DIR that actually has its
    artifact file present, else None. Lexicographic sort matches the date-stamped
    version string (`lstm_autoencoder@2026-06-21`) chronologically."""
    base = os.path.join(settings.model_dir, model_name)
    if not os.path.isdir(base):
        return None
    filename = _ARTIFACT_FILENAMES[model_name]
    versions = sorted(
        v for v in os.listdir(base) if os.path.isfile(os.path.join(base, v, filename))
    )
    return versions[-1] if versions else None


def _existing_production_row(model_name: str) -> ModelRegistry | None:
    with SessionLocal() as db:
        return db.scalar(
            select(ModelRegistry)
            .where(ModelRegistry.model_name == model_name, ModelRegistry.stage == "production")
            .order_by(ModelRegistry.deployed_at.desc())
        )


def _register_from_local_artifact(model_name: str) -> ModelRegistry | None:
    """Registers a production row pointing at an already-present local artifact when
    none exists in Postgres yet. Returns the production row (pre-existing or freshly
    registered), or None if neither exists."""
    existing = _existing_production_row(model_name)
    if existing is not None:
        return existing

    version = _latest_local_version(model_name)
    if version is None:
        logger.warning(
            "no production %s row and no local artifact under %s -- AE stays cold-start "
            "(IF-shadow-fallback) until training.train_lstm_autoencoder runs",
            model_name,
            os.path.join(settings.model_dir, model_name),
        )
        return None

    from training.registry import register_model

    filename = _ARTIFACT_FILENAMES[model_name]
    default_calib = dataclasses.asdict(calibration.default_calibration())
    register_model(
        model_name=model_name,
        model_type=_MODEL_TYPES[model_name],
        version=version,
        artifact_uri=f"s3://{settings.s3_bucket}/models/{model_name}/{version}/{filename}",
        metrics={
            "calibration": default_calib,
            "note": (
                "registered from a pre-trained local artifact by seed_calibration.py -- "
                "neutral default calibration, not a fresh fit"
            ),
        },
        stage="production",
    )
    logger.info("registered %s production row from local artifact, version=%s", model_name, version)
    return _existing_production_row(model_name)


def main() -> dict:
    ae_row = _register_from_local_artifact("lstm_autoencoder")
    # Mobile distribution artifact -- the gateway's Registry never loads this one
    # directly (app/scoring/registry.py only resolves "lstm_autoencoder" via ONNX), but
    # keeping its registry row in sync matters for /admin/models and Android distribution.
    _register_from_local_artifact("lstm_autoencoder_tflite")

    if ae_row is None:
        return {"status": "skipped", "reason": "no lstm_autoencoder artifact available"}

    calib = (ae_row.metrics or {}).get("calibration") or dataclasses.asdict(
        calibration.default_calibration()
    )
    payload = {
        "scale": calib["scale"],
        "threshold": calib["threshold"],
        "temperature": calib.get("temperature", 1.0),
    }
    redis_client.set(POPULATION_CALIBRATION_KEY, json.dumps(payload))
    return {"version": ae_row.version, **payload}


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    result = main()
    for key, value in result.items():
        print(f"{key}: {value}")
